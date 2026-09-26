"""The failsafe must tell the alarm apart from other audio and outside stops."""

from datetime import timedelta

import pytest
from homeassistant.components.media_player import MediaPlayerEntityFeature as Feature
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.wakey.const import EVENT_ALARM_DISMISSED, EVENT_ALARM_FAILED
from custom_components.wakey.player import WakeyPlayer
from custom_components.wakey.store import WakeyStore

PLAYER = "media_player.bedroom"
URI = "https://example.com/alarm.mp3"
AMBIENT = "https://example.com/rain.mp3"


@pytest.fixture
async def playback(hass):
    store = WakeyStore(hass)
    player = WakeyPlayer(hass, store)
    alarm = store.async_create({
        "name": "Test", "media_player": PLAYER, "source_uri": URI,
        "auto_dismiss_minutes": 30,
    })
    plays = []
    behaviour = {"ignore_play": False}

    async def play(call):
        plays.append(dict(call.data))
        if behaviour["ignore_play"]:
            return
        attrs = dict(hass.states.get(PLAYER).attributes)
        attrs["media_content_id"] = call.data["media_content_id"]
        hass.states.async_set(PLAYER, "playing", attrs)

    hass.services.async_register("media_player", "play_media", play)
    pauses = async_mock_service(hass, "media_player", "media_pause")
    async_mock_service(hass, "media_player", "volume_set")
    events = {"failed": [], "dismissed": []}
    hass.bus.async_listen(EVENT_ALARM_FAILED, events["failed"].append)
    hass.bus.async_listen(EVENT_ALARM_DISMISSED, events["dismissed"].append)
    hass.states.async_set(PLAYER, "idle", {"supported_features": Feature.PAUSE})
    yield player, alarm, plays, pauses, events, behaviour
    await player.async_shutdown()


async def advance(hass, freezer, seconds):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


def set_state(hass, state, **attrs):
    current = hass.states.get(PLAYER)
    hass.states.async_set(PLAYER, state, {**current.attributes, **attrs})


# --- issue #4: pre-existing audio ------------------------------------------


async def test_preexisting_audio_does_not_satisfy_failsafe(hass, freezer, playback):
    player, alarm, plays, _, events, behaviour = playback
    set_state(hass, "playing", media_content_id=AMBIENT)
    behaviour["ignore_play"] = True
    await player.async_fire(alarm)
    await advance(hass, freezer, 11)
    assert len(plays) == 2  # Retried despite the player reporting "playing".
    await advance(hass, freezer, 11)
    assert len(events["failed"]) == 1
    assert events["failed"][0].data["reason"] == "playback_not_started:previous_media"
    assert alarm.id not in player.ringing


async def test_alarm_replacing_preexisting_audio_passes(hass, freezer, playback):
    player, alarm, plays, _, events, _ = playback
    set_state(hass, "playing", media_content_id=AMBIENT)
    await player.async_fire(alarm)
    await advance(hass, freezer, 25)
    assert len(plays) == 1
    assert not events["failed"]
    assert alarm.id in player.ringing


async def test_preexisting_audio_without_media_id_keeps_old_behaviour(hass, freezer, playback):
    player, alarm, plays, _, events, behaviour = playback
    set_state(hass, "playing")
    behaviour["ignore_play"] = True
    await player.async_fire(alarm)
    await advance(hass, freezer, 25)
    assert len(plays) == 1
    assert not events["failed"]


# --- issue #3: silenced outside Wakey --------------------------------------


@pytest.mark.parametrize("silenced", ["paused", "off"])
async def test_outside_stop_dismisses_instead_of_retrying(hass, freezer, playback, silenced):
    player, alarm, plays, _, events, _ = playback
    await player.async_fire(alarm)
    await hass.async_block_till_done()
    set_state(hass, silenced)  # e.g. a bare "stop" routed to HassMediaPause.
    await hass.async_block_till_done()
    await advance(hass, freezer, 3)
    assert alarm.id not in player.ringing
    assert events["dismissed"][0].data["reason"] == "external"
    await advance(hass, freezer, 25)
    assert len(plays) == 1
    assert not events["failed"]


async def test_momentary_pause_is_not_a_dismiss(hass, freezer, playback):
    player, alarm, _, _, events, _ = playback
    await player.async_fire(alarm)
    await hass.async_block_till_done()
    set_state(hass, "paused")
    await hass.async_block_till_done()
    set_state(hass, "playing")
    await advance(hass, freezer, 3)
    assert alarm.id in player.ringing
    assert not events["dismissed"]


async def test_pausing_preexisting_audio_before_alarm_starts_is_ignored(hass, freezer, playback):
    player, alarm, plays, _, events, behaviour = playback
    set_state(hass, "playing", media_content_id=AMBIENT)
    behaviour["ignore_play"] = True
    await player.async_fire(alarm)
    set_state(hass, "paused")
    await advance(hass, freezer, 3)
    assert alarm.id in player.ringing
    assert not events["dismissed"]


async def test_wakey_own_dismiss_is_not_reported_as_external(hass, freezer, playback):
    player, alarm, _, pauses, events, _ = playback
    await player.async_fire(alarm)
    await hass.async_block_till_done()
    await player.async_dismiss(alarm.id)
    set_state(hass, "paused")
    await advance(hass, freezer, 3)
    assert [e.data["reason"] for e in events["dismissed"]] == ["user"]
    assert len(pauses) == 1
