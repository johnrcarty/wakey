"""Per-user ownership and the speaker allowlist.

The case these tests exist for: a household member should be able to run
their own alarms without being able to see, change, or fire anyone else's —
and without being able to point an alarm at a speaker they were not given.
"""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wakey.const import DOMAIN

KIDS_ROOM = "media_player.kids_room"
BEDROOM = "media_player.bedroom"

ALARM = {
    "name": "Weekday",
    "time": "06:30",
    "media_player": BEDROOM,
    "source_uri": "library://track/6018",
    "weekdays": [0, 1, 2, 3, 4],
}


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    config_entry = MockConfigEntry(domain=DOMAIN, data={}, title="Wakey")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def _store(hass):
    return next(iter(hass.data[DOMAIN].values())).store


def _make_alarm(hass, owner_id, **overrides):
    return _store(hass).async_create({**ALARM, "owner_id": owner_id, **overrides})


def _grant(hass, user_id, players):
    _store(hass).async_set_policy(user_id, players)


# --- visibility ------------------------------------------------------------


async def test_non_admin_sees_only_own_alarms(
    hass, entry, hass_ws_client, kid_token, kid_user, other_user
) -> None:
    mine = _make_alarm(hass, kid_user.id, name="Mine")
    _make_alarm(hass, other_user.id, name="Theirs")
    _make_alarm(hass, None, name="Legacy")

    client = await hass_ws_client(hass, kid_token)
    await client.send_json_auto_id({"type": "wakey/list"})
    result = (await client.receive_json())["result"]

    assert [a["id"] for a in result["alarms"]] == [mine.id]
    assert result["is_admin"] is False
    assert result["user_id"] == kid_user.id


async def test_admin_sees_every_alarm_including_unowned(
    hass, entry, hass_ws_client, kid_user, other_user
) -> None:
    _make_alarm(hass, kid_user.id, name="Kid")
    _make_alarm(hass, other_user.id, name="Other")
    _make_alarm(hass, None, name="Legacy")

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/list"})
    result = (await client.receive_json())["result"]

    assert len(result["alarms"]) == 3
    assert result["is_admin"] is True
    # Admins are unrestricted, which is a different thing from "allowed none".
    assert result["allowed_media_players"] is None


async def test_snapshot_carries_the_callers_allowed_players(
    hass, entry, hass_ws_client, kid_token, kid_user
) -> None:
    _grant(hass, kid_user.id, [KIDS_ROOM])

    client = await hass_ws_client(hass, kid_token)
    await client.send_json_auto_id({"type": "wakey/list"})
    result = (await client.receive_json())["result"]

    assert result["allowed_media_players"] == [KIDS_ROOM]


async def test_subscribe_delivers_a_separate_view_per_connection(
    hass, entry, hass_ws_client, kid_token, kid_user, other_user
) -> None:
    """The dispatcher signal is global; the snapshots must not be."""
    admin_client = await hass_ws_client(hass)
    kid_client = await hass_ws_client(hass, kid_token)

    for client in (admin_client, kid_client):
        await client.send_json_auto_id({"type": "wakey/subscribe"})
        assert (await client.receive_json())["success"]
        assert (await client.receive_json())["event"]["alarms"] == []

    _make_alarm(hass, other_user.id, name="Someone else's")
    await hass.async_block_till_done()

    assert len((await admin_client.receive_json())["event"]["alarms"]) == 1
    assert (await kid_client.receive_json())["event"]["alarms"] == []


async def test_policy_change_is_pushed_to_subscribers(
    hass, entry, hass_ws_client, kid_token, kid_user
) -> None:
    client = await hass_ws_client(hass, kid_token)
    await client.send_json_auto_id({"type": "wakey/subscribe"})
    assert (await client.receive_json())["success"]
    assert (await client.receive_json())["event"]["allowed_media_players"] == []

    _grant(hass, kid_user.id, [KIDS_ROOM])
    await hass.async_block_till_done()

    pushed = await client.receive_json()
    assert pushed["event"]["allowed_media_players"] == [KIDS_ROOM]


# --- creating --------------------------------------------------------------


async def test_create_stamps_the_caller_as_owner(
    hass, entry, hass_ws_client, kid_token, kid_user
) -> None:
    _grant(hass, kid_user.id, [KIDS_ROOM])
    client = await hass_ws_client(hass, kid_token)

    await client.send_json_auto_id(
        {"type": "wakey/create", **ALARM, "media_player": KIDS_ROOM}
    )
    alarm_id = (await client.receive_json())["result"]["alarm_id"]

    assert _store(hass).async_get(alarm_id).owner_id == kid_user.id


async def test_create_on_a_disallowed_speaker_is_refused(
    hass, entry, hass_ws_client, kid_token, kid_user
) -> None:
    """The prank: an alarm in someone else's bedroom."""
    _grant(hass, kid_user.id, [KIDS_ROOM])
    client = await hass_ws_client(hass, kid_token)

    await client.send_json_auto_id({"type": "wakey/create", **ALARM})  # BEDROOM
    msg = await client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "player_not_allowed"
    assert _store(hass).async_all() == []


async def test_non_admin_cannot_assign_an_alarm_to_someone_else(
    hass, entry, hass_ws_client, kid_token, kid_user, other_user
) -> None:
    _grant(hass, kid_user.id, [KIDS_ROOM])
    client = await hass_ws_client(hass, kid_token)

    await client.send_json_auto_id(
        {
            "type": "wakey/create",
            **ALARM,
            "media_player": KIDS_ROOM,
            "owner_id": other_user.id,
        }
    )
    alarm_id = (await client.receive_json())["result"]["alarm_id"]

    assert _store(hass).async_get(alarm_id).owner_id == kid_user.id


async def test_admin_create_defaults_to_owning_it_themselves(
    hass, entry, hass_ws_client, hass_admin_user
) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/create", **ALARM})
    alarm_id = (await client.receive_json())["result"]["alarm_id"]

    assert _store(hass).async_get(alarm_id).owner_id == hass_admin_user.id


async def test_admin_may_create_on_behalf_of_someone(
    hass, entry, hass_ws_client, kid_user
) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "wakey/create", **ALARM, "owner_id": kid_user.id}
    )
    alarm_id = (await client.receive_json())["result"]["alarm_id"]

    assert _store(hass).async_get(alarm_id).owner_id == kid_user.id


# --- touching other people's alarms ----------------------------------------


@pytest.mark.parametrize(
    ("command", "extra"),
    [
        ("wakey/update", {"time": "03:00"}),
        ("wakey/delete", {}),
        ("wakey/trigger", {}),
        ("wakey/skip_next", {}),
        ("wakey/snooze", {}),
        ("wakey/dismiss", {}),
    ],
)
async def test_non_admin_cannot_touch_another_users_alarm(
    hass, entry, hass_ws_client, kid_token, other_user, command, extra
) -> None:
    """Reported as not_found so alarm ids cannot be probed for."""
    theirs = _make_alarm(hass, other_user.id)
    client = await hass_ws_client(hass, kid_token)

    await client.send_json_auto_id({"type": command, "alarm_id": theirs.id, **extra})
    msg = await client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"
    assert _store(hass).async_get(theirs.id).time == ALARM["time"]


async def test_non_admin_cannot_touch_an_unowned_alarm(
    hass, entry, hass_ws_client, kid_token
) -> None:
    legacy = _make_alarm(hass, None)
    client = await hass_ws_client(hass, kid_token)

    await client.send_json_auto_id({"type": "wakey/trigger", "alarm_id": legacy.id})
    msg = await client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_non_admin_can_fully_manage_their_own_alarm(
    hass, entry, hass_ws_client, kid_token, kid_user
) -> None:
    _grant(hass, kid_user.id, [KIDS_ROOM])
    mine = _make_alarm(hass, kid_user.id, media_player=KIDS_ROOM)
    client = await hass_ws_client(hass, kid_token)

    await client.send_json_auto_id(
        {"type": "wakey/update", "alarm_id": mine.id, "time": "05:45"}
    )
    assert (await client.receive_json())["success"]
    assert _store(hass).async_get(mine.id).time == "05:45"

    await client.send_json_auto_id({"type": "wakey/skip_next", "alarm_id": mine.id})
    assert (await client.receive_json())["success"]
    assert _store(hass).async_get(mine.id).skip_next is True

    await client.send_json_auto_id({"type": "wakey/delete", "alarm_id": mine.id})
    assert (await client.receive_json())["success"]
    assert _store(hass).async_get(mine.id) is None


async def test_non_admin_cannot_move_an_alarm_to_a_disallowed_speaker(
    hass, entry, hass_ws_client, kid_token, kid_user
) -> None:
    _grant(hass, kid_user.id, [KIDS_ROOM])
    mine = _make_alarm(hass, kid_user.id, media_player=KIDS_ROOM)
    client = await hass_ws_client(hass, kid_token)

    await client.send_json_auto_id(
        {"type": "wakey/update", "alarm_id": mine.id, "media_player": BEDROOM}
    )
    msg = await client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "player_not_allowed"
    assert _store(hass).async_get(mine.id).media_player == KIDS_ROOM


async def test_owner_can_still_edit_an_alarm_whose_speaker_was_revoked(
    hass, entry, hass_ws_client, kid_token, kid_user
) -> None:
    """Revoking a speaker must not lock its owner out of the alarm entirely.

    The panel sends the whole alarm on every save, so validating the speaker
    unconditionally would make even a rename impossible.
    """
    _grant(hass, kid_user.id, [KIDS_ROOM])
    mine = _make_alarm(hass, kid_user.id, media_player=KIDS_ROOM)
    _grant(hass, kid_user.id, [])  # revoked

    client = await hass_ws_client(hass, kid_token)
    await client.send_json_auto_id(
        {
            "type": "wakey/update",
            "alarm_id": mine.id,
            "name": "Renamed",
            "media_player": KIDS_ROOM,
        }
    )
    assert (await client.receive_json())["success"]
    assert _store(hass).async_get(mine.id).name == "Renamed"


async def test_bare_dismiss_only_reaches_your_own_alarms(
    hass, entry, hass_ws_client, kid_token, kid_user, other_user
) -> None:
    mine = _make_alarm(hass, kid_user.id, name="Mine")
    theirs = _make_alarm(hass, other_user.id, name="Theirs")

    hass.states.async_set(mine.media_player, "playing")
    hass.states.async_set(theirs.media_player, "playing")
    data = next(iter(hass.data[DOMAIN].values()))
    await data.player.async_fire(mine)
    await data.player.async_fire(theirs)
    assert set(data.player.ringing) == {mine.id, theirs.id}

    client = await hass_ws_client(hass, kid_token)
    await client.send_json_auto_id({"type": "wakey/dismiss"})
    assert (await client.receive_json())["success"]

    assert set(data.player.ringing) == {theirs.id}


async def test_admin_bare_dismiss_still_reaches_everything(
    hass, entry, hass_ws_client, kid_user, other_user
) -> None:
    data = next(iter(hass.data[DOMAIN].values()))
    await data.player.async_fire(_make_alarm(hass, kid_user.id, name="A"))
    await data.player.async_fire(_make_alarm(hass, other_user.id, name="B"))

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/dismiss"})
    assert (await client.receive_json())["success"]

    assert data.player.ringing == {}


async def test_admin_bypasses_the_allowlist_entirely(
    hass, entry, hass_ws_client
) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/create", **ALARM})
    assert (await client.receive_json())["success"]


def test_allowed_players_never_falls_open_without_a_user() -> None:
    """A caller with no identity is denied, not waved through."""
    from custom_components.wakey.permissions import async_allowed_players

    class _EmptyStore:
        def async_get_policy(self, user_id):
            return None

    store = _EmptyStore()
    assert async_allowed_players(store, None, True) is None  # system / admin
    assert async_allowed_players(store, None, False) == []  # anonymous: nothing
