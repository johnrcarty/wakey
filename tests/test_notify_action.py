"""Push notification on ring, and dismissing/snoozing from its action buttons."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.wakey import _parse_notification_action
from custom_components.wakey.const import DOMAIN

ALARM = {
    "name": "Weekday",
    "time": "06:30",
    "media_player": "media_player.bedroom",
    "source_uri": "library://track/6018",
}


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set(ALARM["media_player"], "playing")
    config_entry = MockConfigEntry(domain=DOMAIN, data={}, title="Wakey")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def _data(hass):
    return next(iter(hass.data[DOMAIN].values()))


# --- action id parsing -------------------------------------------------------


def test_parse_notification_action_dismiss():
    assert _parse_notification_action("wakey_dismiss_abc123_tok0") == (
        "dismiss",
        "abc123",
        "tok0",
    )


def test_parse_notification_action_snooze():
    assert _parse_notification_action("wakey_snooze_abc123_tok0") == (
        "snooze",
        "abc123",
        "tok0",
    )


@pytest.mark.parametrize(
    "action",
    ["not_ours", "wakey_dismiss_", "wakey_dismiss_abc123", "mobile_app_something"],
)
def test_parse_notification_action_rejects_malformed(action):
    assert _parse_notification_action(action) is None


# --- sending the notification ------------------------------------------------


async def test_fire_sends_notification_when_targets_configured(hass, entry) -> None:
    calls = async_mock_service(hass, "notify", "send_message")
    data = _data(hass)
    alarm = data.store.async_create({**ALARM, "notify_targets": ["notify.phone"]})

    await data.player.async_fire(alarm)

    assert len(calls) == 1
    assert calls[0].data["entity_id"] == "notify.phone"
    actions = calls[0].data["data"]["actions"]
    action_ids = {a["action"] for a in actions}
    token = data.player.ringing[alarm.id].token
    assert action_ids == {
        f"{DOMAIN}_dismiss_{alarm.id}_{token}",
        f"{DOMAIN}_snooze_{alarm.id}_{token}",
    }


async def test_fire_sends_no_notification_without_targets(hass, entry) -> None:
    calls = async_mock_service(hass, "notify", "send_message")
    data = _data(hass)
    alarm = data.store.async_create(ALARM)

    await data.player.async_fire(alarm)

    assert calls == []


# --- handling the tap --------------------------------------------------------


async def test_dismiss_action_dismisses_the_alarm(hass, entry) -> None:
    data = _data(hass)
    alarm = data.store.async_create({**ALARM, "notify_targets": ["notify.phone"]})
    await data.player.async_fire(alarm)
    token = data.player.ringing[alarm.id].token

    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": f"{DOMAIN}_dismiss_{alarm.id}_{token}"}
    )
    await hass.async_block_till_done()

    assert alarm.id not in data.player.ringing


async def test_snooze_action_snoozes_the_alarm(hass, entry) -> None:
    data = _data(hass)
    alarm = data.store.async_create({**ALARM, "notify_targets": ["notify.phone"]})
    await data.player.async_fire(alarm)
    token = data.player.ringing[alarm.id].token

    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": f"{DOMAIN}_snooze_{alarm.id}_{token}"}
    )
    await hass.async_block_till_done()

    assert data.player.ringing[alarm.id].snoozed is True


async def test_stale_token_action_is_ignored(hass, entry) -> None:
    """A tap on a notification from a previous ring must not touch the current one."""
    data = _data(hass)
    alarm = data.store.async_create({**ALARM, "notify_targets": ["notify.phone"]})

    await data.player.async_fire(alarm)
    stale_token = data.player.ringing[alarm.id].token
    await data.player.async_fire(alarm)  # replaces the RingState with a new token
    current_token = data.player.ringing[alarm.id].token
    assert stale_token != current_token

    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"{DOMAIN}_dismiss_{alarm.id}_{stale_token}"},
    )
    await hass.async_block_till_done()

    assert alarm.id in data.player.ringing
    assert data.player.ringing[alarm.id].token == current_token
