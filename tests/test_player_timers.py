"""Exercise real HA timer callbacks, including their thread dispatch."""

from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.wakey.const import EVENT_ALARM_DISMISSED, EVENT_ALARM_FAILED
from custom_components.wakey.player import WakeyPlayer
from custom_components.wakey.store import WakeyStore

PLAYER = "media_player.bedroom"


@pytest.fixture
async def playback(hass):
    store = WakeyStore(hass)
    player = WakeyPlayer(hass, store)
    calls = {name: async_mock_service(hass, "media_player", name) for name in (
        "play_media", "media_pause", "media_stop", "volume_set",
    )}
    hass.states.async_set(PLAYER, "playing")
    alarm = store.async_create({
        "name": "Test", "media_player": PLAYER, "source_uri": "https://example.com/alarm.mp3",
        "snooze_minutes": 9, "auto_dismiss_minutes": 30,
    })
    yield player, alarm, calls
    await player.async_shutdown()


async def advance(hass, freezer, seconds):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_snooze_timer_restarts_playback(hass, freezer, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    await player.async_snooze(alarm.id)
    await advance(hass, freezer, 9 * 60 - 1)
    assert len(calls["play_media"]) == 1
    assert player.ringing[alarm.id].snoozed
    await advance(hass, freezer, 2)
    assert len(calls["play_media"]) == 2
    assert not player.ringing[alarm.id].snoozed


async def test_auto_dismiss_timer_stops_playback(hass, freezer, playback):
    player, alarm, calls = playback
    events = []
    hass.bus.async_listen(EVENT_ALARM_DISMISSED, events.append)
    await player.async_fire(alarm)
    await advance(hass, freezer, 30 * 60 - 1)
    assert alarm.id in player.ringing
    await advance(hass, freezer, 2)
    assert alarm.id not in player.ringing
    assert len(calls["media_pause"]) == 1
    assert events[0].data["reason"] == "auto"


async def test_dismiss_cancels_pending_snooze(hass, freezer, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    await player.async_snooze(alarm.id)
    await player.async_dismiss(alarm.id)
    await advance(hass, freezer, 10 * 60)
    assert len(calls["play_media"]) == 1
    assert not player.ringing


async def test_failsafe_timer_retries(hass, freezer, playback):
    player, alarm, calls = playback
    events = []
    hass.bus.async_listen(EVENT_ALARM_FAILED, events.append)
    hass.states.async_set(PLAYER, "idle")
    await player.async_fire(alarm)
    await advance(hass, freezer, 11)
    assert len(calls["play_media"]) == 2
    await advance(hass, freezer, 11)
    assert len(calls["play_media"]) == 2
    assert len(events) == 1


async def test_snooze_starts_a_fresh_auto_dismiss_window(hass, freezer, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    await advance(hass, freezer, 20 * 60)
    await player.async_snooze(alarm.id)
    await advance(hass, freezer, 9 * 60 + 1)
    assert len(calls["play_media"]) == 2
    await advance(hass, freezer, 2 * 60)
    assert alarm.id in player.ringing
    await advance(hass, freezer, 28 * 60 + 1)
    assert alarm.id not in player.ringing


async def test_shutdown_cancels_pending_snooze(hass, freezer, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    await player.async_snooze(alarm.id)
    await player.async_shutdown()
    await advance(hass, freezer, 10 * 60)
    assert len(calls["play_media"]) == 1


async def test_retrigger_cancels_previous_auto_dismiss(hass, freezer, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    await advance(hass, freezer, 20 * 60)
    await player.async_fire(alarm)
    await advance(hass, freezer, 11 * 60)
    assert alarm.id in player.ringing
    assert len(calls["media_pause"]) == 1  # Stops the ring being replaced.
    await advance(hass, freezer, 20 * 60)
    assert alarm.id not in player.ringing
