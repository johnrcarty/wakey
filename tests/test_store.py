"""Storage behaviour."""

from unittest.mock import patch

from custom_components.wakey.store import (
    AlarmEntry,
    WakeyStore,
    coerce,
    coerce_notify_targets,
    coerce_players,
)


async def test_create_assigns_id_and_persists(hass):
    store = WakeyStore(hass)
    await store.async_load()

    alarm = store.async_create({"name": "Wake up", "time": "6:5", "media_player": "media_player.x"})

    assert alarm.id
    assert alarm.name == "Wake up"
    assert alarm.time == "06:05"  # normalised
    assert store.async_get(alarm.id) is alarm
    assert len(store.async_all()) == 1


async def test_update_changes_value(hass):
    store = WakeyStore(hass)
    await store.async_load()
    alarm = store.async_create({"time": "07:00"})

    store.async_update(alarm.id, {"time": "08:15"})

    assert store.async_get(alarm.id).time == "08:15"


async def test_noop_update_does_not_dispatch(hass):
    """Guards the time-entity feedback loop.

    The time entity writes back on every change signal. If a write with an
    unchanged value still dispatched, entity and store would ping-pong.
    """
    store = WakeyStore(hass)
    await store.async_load()
    alarm = store.async_create({"time": "07:00"})

    with patch("custom_components.wakey.store.async_dispatcher_send") as dispatch:
        store.async_update(alarm.id, {"time": "07:00"})
        assert dispatch.call_count == 0

        store.async_update(alarm.id, {"time": "07:30"})
        assert dispatch.call_count == 1


async def test_update_unknown_alarm_returns_none(hass):
    store = WakeyStore(hass)
    await store.async_load()
    assert store.async_update("nope", {"time": "07:00"}) is None


async def test_delete(hass):
    store = WakeyStore(hass)
    await store.async_load()
    alarm = store.async_create({})

    assert store.async_delete(alarm.id) is True
    assert store.async_get(alarm.id) is None
    assert store.async_delete(alarm.id) is False


async def test_reload_from_disk_round_trips(hass):
    store = WakeyStore(hass)
    await store.async_load()
    alarm = store.async_create({
        "name": "Weekday", "time": "06:30", "weekdays": [0, 2, 4], "repeat_playback": True,
    })
    await store.async_save_now()

    reloaded = WakeyStore(hass)
    await reloaded.async_load()

    assert len(reloaded.async_all()) == 1
    assert reloaded.async_get(alarm.id).name == "Weekday"
    assert reloaded.async_get(alarm.id).weekdays == [0, 2, 4]
    assert reloaded.async_get(alarm.id).repeat_playback is True


def test_older_alarms_do_not_enable_audio_repeat():
    assert AlarmEntry.from_dict({"id": "old"}).repeat_playback is False


# --- coerce ----------------------------------------------------------------


def test_coerce_clamps_volume():
    """A bug that sets volume 1.0 on a bedroom speaker at 06:30 is memorable."""
    assert coerce({"volume": 5})["volume"] == 1.0
    assert coerce({"volume": -3})["volume"] == 0.0
    assert coerce({"volume": "loud"})["volume"] == 0.7


def test_coerce_rejects_bad_enums():
    assert coerce({"repeat": "hourly"})["repeat"] == "weekly"
    assert coerce({"source_kind": "gramophone"})["source_kind"] == "music_assistant"


def test_coerce_dedupes_and_bounds_weekdays():
    assert coerce({"weekdays": [1, 1, 3, 9, -2]})["weekdays"] == [1, 3]


def test_coerce_drops_unparseable_time():
    assert "time" not in coerce({"time": "quarter past"})


def test_from_dict_ignores_unknown_keys():
    alarm = AlarmEntry.from_dict({"id": "a", "name": "x", "bogus": 1})
    assert alarm.id == "a"
    assert not hasattr(alarm, "bogus")


def test_coerce_normalises_owner_id():
    assert coerce({"owner_id": "  abc  "})["owner_id"] == "abc"
    assert coerce({"owner_id": ""})["owner_id"] is None
    assert coerce({"owner_id": None})["owner_id"] is None


def test_coerce_players_keeps_only_speakers():
    assert coerce_players(
        ["media_player.b", "light.kitchen", "media_player.a", "media_player.a"]
    ) == ["media_player.a", "media_player.b"]
    assert coerce_players(None) == []
    assert coerce_players("media_player.a") == []


def test_coerce_notify_targets_keeps_only_notify_entities():
    assert coerce_notify_targets(
        ["notify.b", "light.kitchen", "notify.a", "notify.a"]
    ) == ["notify.a", "notify.b"]
    assert coerce_notify_targets(None) == []
    assert coerce_notify_targets("notify.a") == []


def test_coerce_wires_notify_targets_through():
    assert coerce({"notify_targets": ["notify.b", "notify.a", "light.x"]})[
        "notify_targets"
    ] == ["notify.a", "notify.b"]


def test_alarm_entry_default_notify_targets_is_empty():
    assert AlarmEntry.from_dict({"id": "a"}).notify_targets == []


async def test_policies_are_stored_alongside_alarms(hass):
    store = WakeyStore(hass)
    await store.async_load()
    store.async_create({"name": "A", "time": "07:00"})
    store.async_set_policy("user-1", ["media_player.den", "light.x"])

    saved = store._data_to_save()

    assert saved["policies"] == {
        "user-1": {"user_id": "user-1", "allowed_media_players": ["media_player.den"]}
    }
    assert saved["alarms"][0]["owner_id"] is None


async def test_delete_policy_reports_whether_there_was_one(hass):
    store = WakeyStore(hass)
    await store.async_load()

    assert store.async_delete_policy("nobody") is False
    store.async_set_policy("user-1", [])
    assert store.async_delete_policy("user-1") is True
    assert store.async_get_policy("user-1") is None


async def test_for_owner_separates_users_and_legacy_alarms(hass):
    store = WakeyStore(hass)
    await store.async_load()
    mine = store.async_create({"name": "Mine", "time": "07:00", "owner_id": "user-1"})
    legacy = store.async_create({"name": "Legacy", "time": "08:00"})

    assert [a.id for a in store.async_for_owner("user-1")] == [mine.id]
    assert [a.id for a in store.async_for_owner(None)] == [legacy.id]
