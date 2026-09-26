"""WebSocket API used by the panel."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wakey.const import DOMAIN

ALARM = {
    "name": "Weekday",
    "time": "06:30",
    "media_player": "media_player.bedroom",
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


async def test_list_empty(hass, entry, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/list"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["alarms"] == []


async def test_create_then_list(hass, entry, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/create", **ALARM})
    msg = await client.receive_json()
    assert msg["success"]
    alarm_id = msg["result"]["alarm_id"]

    await client.send_json_auto_id({"type": "wakey/list"})
    msg = await client.receive_json()
    alarms = msg["result"]["alarms"]
    assert len(alarms) == 1
    assert alarms[0]["id"] == alarm_id
    assert alarms[0]["name"] == "Weekday"
    # The panel relies on these derived fields existing.
    assert "next_fire" in alarms[0]
    assert alarms[0]["is_ringing"] is False


async def test_subscribe_pushes_initial_and_updates(hass, entry, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/subscribe"})

    assert (await client.receive_json())["success"]

    # Initial snapshot arrives without needing a second round trip.
    first = await client.receive_json()
    assert first["type"] == "event"
    assert first["event"]["alarms"] == []

    await hass.services.async_call(DOMAIN, "create", ALARM, blocking=True)
    await hass.async_block_till_done()

    pushed = await client.receive_json()
    assert pushed["type"] == "event"
    assert len(pushed["event"]["alarms"]) == 1


async def test_update_and_delete(hass, entry, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/create", **ALARM})
    alarm_id = (await client.receive_json())["result"]["alarm_id"]

    await client.send_json_auto_id(
        {"type": "wakey/update", "alarm_id": alarm_id, "time": "05:45"}
    )
    assert (await client.receive_json())["success"]

    data = hass.data[DOMAIN][entry.entry_id]
    assert data.store.async_get(alarm_id).time == "05:45"

    await client.send_json_auto_id({"type": "wakey/delete", "alarm_id": alarm_id})
    assert (await client.receive_json())["success"]
    assert data.store.async_get(alarm_id) is None


async def test_delete_reports_not_found_if_alarm_vanished_mid_dismiss(
    hass, entry, hass_ws_client
) -> None:
    """ws_delete awaits async_dismiss() before deleting from the store. If the
    alarm is gone by the time that await returns (e.g. deleted by another
    client in the meantime), the handler must not report success."""
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/create", **ALARM})
    alarm_id = (await client.receive_json())["result"]["alarm_id"]

    data = hass.data[DOMAIN][entry.entry_id]
    real_dismiss = data.player.async_dismiss

    async def _dismiss_and_vanish(*args, **kwargs):
        result = await real_dismiss(*args, **kwargs)
        data.store.async_delete(alarm_id)
        return result

    data.player.async_dismiss = _dismiss_and_vanish

    await client.send_json_auto_id({"type": "wakey/delete", "alarm_id": alarm_id})
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_create_and_update_notify_targets(hass, entry, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "wakey/create", **ALARM, "notify_targets": ["notify.phone"]}
    )
    msg = await client.receive_json()
    assert msg["success"]
    alarm_id = msg["result"]["alarm_id"]

    data = hass.data[DOMAIN][entry.entry_id]
    assert data.store.async_get(alarm_id).notify_targets == ["notify.phone"]

    await client.send_json_auto_id(
        {
            "type": "wakey/update",
            "alarm_id": alarm_id,
            "notify_targets": ["notify.phone", "notify.tablet"],
        }
    )
    assert (await client.receive_json())["success"]
    assert data.store.async_get(alarm_id).notify_targets == [
        "notify.phone",
        "notify.tablet",
    ]

    # A bare string is promoted to a one-element list, matching the service
    # schema, rather than being rejected (or iterated as characters).
    await client.send_json_auto_id(
        {"type": "wakey/update", "alarm_id": alarm_id, "notify_targets": "notify.phone"}
    )
    assert (await client.receive_json())["success"]
    assert data.store.async_get(alarm_id).notify_targets == ["notify.phone"]


async def test_update_unknown_alarm_errors(hass, entry, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/update", "alarm_id": "nope", "time": "05:45"})
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_repeat_playback_round_trips_across_both_apis(hass, entry, hass_ws_client):
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/create", **ALARM, "repeat_playback": True})
    result = await client.receive_json()
    assert result["success"]
    alarm_id = result["result"]["alarm_id"]
    await client.send_json_auto_id({"type": "wakey/list"})
    assert (await client.receive_json())["result"]["alarms"][0]["repeat_playback"] is True
    await client.send_json_auto_id({
        "type": "wakey/update", "alarm_id": alarm_id, "repeat_playback": False,
    })
    assert (await client.receive_json())["success"]
    data = hass.data[DOMAIN][entry.entry_id]
    assert data.store.async_get(alarm_id).repeat_playback is False
    await hass.services.async_call(DOMAIN, "update", {
        "alarm_id": alarm_id, "repeat_playback": True,
    }, blocking=True)
    assert data.store.async_get(alarm_id).repeat_playback is True
    await hass.services.async_call(DOMAIN, "create", {
        **ALARM, "name": "Created by action", "repeat_playback": True,
    }, blocking=True)
    assert all(a.repeat_playback for a in data.store.async_all())


async def test_non_admin_with_no_policy_cannot_create(
    hass, entry, hass_ws_client, hass_read_only_access_token
) -> None:
    """Speakers are deny-by-default: no grant, no alarm."""
    client = await hass_ws_client(hass, hass_read_only_access_token)

    await client.send_json_auto_id({"type": "wakey/create", **ALARM})
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "player_not_allowed"

    # Reading is still fine — they just have nothing of their own to see.
    await client.send_json_auto_id({"type": "wakey/list"})
    msg = await client.receive_json()
    assert msg["success"]
    assert msg["result"]["alarms"] == []


async def test_skip_next_toggle(hass, entry, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "wakey/create", **ALARM})
    alarm_id = (await client.receive_json())["result"]["alarm_id"]

    await client.send_json_auto_id({"type": "wakey/skip_next", "alarm_id": alarm_id})
    assert (await client.receive_json())["success"]

    data = hass.data[DOMAIN][entry.entry_id]
    assert data.store.async_get(alarm_id).skip_next is True
