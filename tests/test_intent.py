"""Global voice snooze/cancel: not scoped to any alarm, satellite, or user."""

import pytest
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import intent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wakey.const import DOMAIN
from custom_components.wakey.intent import INTENT_DISMISS, INTENT_SNOOZE

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


async def _handle(hass, intent_type: str) -> None:
    obj = intent.Intent(
        hass,
        platform=DOMAIN,
        intent_type=intent_type,
        slots={},
        text_input=None,
        context=Context(),
        language="en",
    )
    handler = next(h for h in intent.async_get(hass) if h.intent_type == intent_type)
    await handler.async_handle(obj)


async def test_setup_registers_both_intents(hass, entry) -> None:
    registered = {h.intent_type for h in intent.async_get(hass)}
    assert {INTENT_SNOOZE, INTENT_DISMISS} <= registered


async def test_snooze_intent_snoozes_every_ringing_alarm(hass, entry) -> None:
    data = _data(hass)
    a = data.store.async_create({**ALARM, "owner_id": "kid"})
    b = data.store.async_create({**ALARM, "owner_id": "other"})
    await data.player.async_fire(a)
    await data.player.async_fire(b)

    await _handle(hass, INTENT_SNOOZE)

    assert data.player.ringing[a.id].snoozed is True
    assert data.player.ringing[b.id].snoozed is True


async def test_dismiss_intent_dismisses_every_ringing_alarm(hass, entry) -> None:
    data = _data(hass)
    a = data.store.async_create({**ALARM, "owner_id": "kid"})
    b = data.store.async_create({**ALARM, "owner_id": "other"})
    await data.player.async_fire(a)
    await data.player.async_fire(b)

    await _handle(hass, INTENT_DISMISS)

    assert data.player.ringing == {}


async def test_intent_with_nothing_ringing_is_a_noop(hass, entry) -> None:
    await _handle(hass, INTENT_SNOOZE)
    await _handle(hass, INTENT_DISMISS)
    assert _data(hass).player.ringing == {}
