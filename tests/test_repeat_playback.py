"""Repeat uses player capabilities or actual completion, with bounded lifetime."""

import asyncio
from datetime import timedelta

import pytest
from homeassistant.components.media_player import MediaPlayerEntityFeature as Feature
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_mock_service

from custom_components.wakey.const import EVENT_ALARM_FAILED
from custom_components.wakey.player import WakeyPlayer
from custom_components.wakey.store import WakeyStore

PLAYER = "media_player.bedroom"
URI = "https://example.com/alarm.mp3"


@pytest.fixture
async def playback(hass):
    store = WakeyStore(hass)
    player = WakeyPlayer(hass, store)
    alarm = store.async_create({
        "media_player": PLAYER, "source_uri": URI, "repeat_playback": True,
        "auto_dismiss_minutes": 1, "snooze_minutes": 1,
    })
    calls = []
    hass.states.async_set(PLAYER, "idle", {
        "supported_features": Feature.PAUSE | Feature.STOP, "repeat": "off",
    })

    async def play(call):
        calls.append(("play", dict(call.data)))
        attrs = dict(hass.states.get(PLAYER).attributes)
        attrs.update({
            "media_content_id": call.data.get("media_id", call.data.get("media_content_id")),
            "media_duration": 3, "media_position": 0,
            "media_position_updated_at": dt_util.utcnow(),
        })
        hass.states.async_set(PLAYER, "playing", attrs)

    async def repeat(call):
        calls.append(("repeat", call.data["repeat"]))
        current = hass.states.get(PLAYER)
        hass.states.async_set(PLAYER, current.state, {**current.attributes, "repeat": call.data["repeat"]})

    async def pause(call):
        calls.append(("pause", dict(call.data)))
        hass.states.async_set(PLAYER, "paused", dict(hass.states.get(PLAYER).attributes))

    hass.services.async_register("media_player", "play_media", play)
    hass.services.async_register("media_player", "repeat_set", repeat)
    hass.services.async_register("media_player", "media_pause", pause)
    hass.services.async_register("media_player", "media_stop", pause)
    async_mock_service(hass, "media_player", "volume_set")
    yield player, alarm, calls
    await player.async_shutdown()


async def advance(hass, freezer, seconds):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def complete(hass, freezer):
    await advance(hass, freezer, 3)
    hass.states.async_set(PLAYER, "idle", dict(hass.states.get(PLAYER).attributes))
    await hass.async_block_till_done()
    await advance(hass, freezer, 1)


def plays(calls):
    return [data for name, data in calls if name == "play"]


async def test_completed_clip_repeats_without_restarting_fade_or_deadline(hass, freezer, playback):
    player, alarm, calls = playback
    alarm.fade_seconds = 20
    await player.async_fire(alarm)
    await hass.async_block_till_done()
    fade = player.ringing[alarm.id].fade_unsub
    await complete(hass, freezer)
    await complete(hass, freezer)
    assert len(plays(calls)) == 3
    assert player.ringing[alarm.id].fade_unsub is fade
    await advance(hass, freezer, 53)
    assert alarm.id not in player.ringing
    assert calls[-1][0] == "pause"


@pytest.mark.parametrize("ending", ["snooze", "dismiss", "unload"])
async def test_cleanup_cancels_pending_replay(hass, freezer, playback, ending):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    await advance(hass, freezer, 3)
    hass.states.async_set(PLAYER, "idle", dict(hass.states.get(PLAYER).attributes))
    await hass.async_block_till_done()
    if ending == "snooze":
        await player.async_snooze(alarm.id)
    elif ending == "dismiss":
        await player.async_dismiss(alarm.id)
    else:
        await player.async_shutdown()
    await advance(hass, freezer, 10)
    assert len(plays(calls)) == 1


async def test_short_clip_without_repeat_does_not_fail_verification(hass, freezer, playback):
    player, alarm, calls = playback
    alarm.repeat_playback = False
    failures = []
    hass.bus.async_listen(EVENT_ALARM_FAILED, failures.append)
    await player.async_fire(alarm)
    await complete(hass, freezer)
    await advance(hass, freezer, 20)
    assert len(plays(calls)) == 1
    assert not failures


@pytest.mark.parametrize("ending", ["paused", "off", "unavailable", "idle"])
async def test_early_stop_is_not_replayed(hass, freezer, playback, ending):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    await advance(hass, freezer, 1)
    hass.states.async_set(PLAYER, ending, dict(hass.states.get(PLAYER).attributes))
    await hass.async_block_till_done()
    await advance(hass, freezer, 20)
    assert len(plays(calls)) == 1


async def test_missing_duration_does_not_guess_when_to_replay(hass, freezer, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    attrs = dict(hass.states.get(PLAYER).attributes)
    attrs.pop("media_duration")
    hass.states.async_set(PLAYER, "playing", attrs)
    await complete(hass, freezer)
    assert len(plays(calls)) == 1


async def test_new_media_is_not_replaced_by_pending_repeat(hass, freezer, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    await advance(hass, freezer, 3)
    attrs = dict(hass.states.get(PLAYER).attributes)
    hass.states.async_set(PLAYER, "idle", attrs)
    await hass.async_block_till_done()
    hass.states.async_set(PLAYER, "playing", {**attrs, "media_content_id": "new-song"})
    await advance(hass, freezer, 2)
    assert len(plays(calls)) == 1


@pytest.mark.parametrize("ending", ["snooze", "dismiss", "auto", "unload"])
async def test_native_repeat_restores_previous_mode(hass, freezer, playback, ending):
    player, alarm, calls = playback
    hass.states.async_set(PLAYER, "idle", {
        "supported_features": Feature.PAUSE | Feature.REPEAT_SET, "repeat": "all",
    })
    await player.async_fire(alarm)
    await complete(hass, freezer)
    assert len(plays(calls)) == 1  # The speaker owns looping.
    assert ("repeat", "one") in calls
    if ending == "snooze":
        await player.async_snooze(alarm.id)
    elif ending == "dismiss":
        await player.async_dismiss(alarm.id)
    elif ending == "auto":
        await advance(hass, freezer, 60)
    else:
        await player.async_shutdown()
    assert ("repeat", "all") in calls
    assert hass.states.get(PLAYER).attributes["repeat"] == "all"


async def test_explicit_repeat_mode_change_is_preserved(hass, playback):
    player, alarm, calls = playback
    hass.states.async_set(PLAYER, "idle", {
        "supported_features": Feature.REPEAT_SET, "repeat": "all",
    })
    await player.async_fire(alarm)
    current = hass.states.get(PLAYER)
    hass.states.async_set(PLAYER, "playing", {**current.attributes, "repeat": "off"})
    await player.async_dismiss(alarm.id)
    assert ("repeat", "all") not in calls


async def test_rejected_native_repeat_uses_completion_fallback(hass, freezer, playback):
    player, alarm, calls = playback
    hass.states.async_set(PLAYER, "idle", {
        "supported_features": Feature.REPEAT_SET, "repeat": "off",
    })

    async def unsupported(call):
        raise RuntimeError("Repeat is unsupported for this source")

    hass.services.async_register("media_player", "repeat_set", unsupported)
    await player.async_fire(alarm)
    await complete(hass, freezer)
    assert len(plays(calls)) == 2


async def test_music_assistant_repeat_preserves_resume_snapshot(hass, freezer, playback):
    from homeassistant.core import SupportsResponse

    player, alarm, calls = playback
    alarm.resume_previous = True
    hass.states.async_set(PLAYER, "playing", {
        "app_id": "music_assistant", "media_content_id": "ambient", "volume_level": 0.2,
    })
    queues = []

    async def queue(call):
        queues.append(call)
        return {PLAYER: {
            "elapsed_time": 19, "current_item": {"media_item": {"uri": "ambient"}},
        }}

    async def play(call):
        calls.append(("play", dict(call.data)))
        hass.states.async_set(PLAYER, "playing", {
            "app_id": "music_assistant", "media_content_id": call.data["media_id"],
            "media_duration": 3, "media_position": 0,
            "media_position_updated_at": dt_util.utcnow(),
        })

    hass.services.async_register("music_assistant", "get_queue", queue, supports_response=SupportsResponse.ONLY)
    hass.services.async_register("music_assistant", "play_media", play)
    seeks = async_mock_service(hass, "media_player", "media_seek")
    await player.async_fire(alarm)
    await complete(hass, freezer)
    assert len(queues) == 1
    assert [call["enqueue"] for call in plays(calls)] == ["play", "play"]
    await player.async_snooze(alarm.id)
    assert plays(calls)[-1]["media_id"] == "ambient"
    assert seeks[-1].data["seek_position"] == 19
    await player.async_dismiss(alarm.id)
    assert calls[-1][0] == "play"  # Dismissing snooze must not pause restored audio.


async def test_snooze_refires_and_repeats_again(hass, freezer, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    await player.async_snooze(alarm.id)
    await advance(hass, freezer, 61)
    await complete(hass, freezer)
    assert len(plays(calls)) == 3
    assert not player.ringing[alarm.id].snoozed


async def test_edit_during_ring_does_not_redirect_cleanup(hass, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    player.store.async_update(alarm.id, {"media_player": "media_player.other"})
    await player.async_dismiss(alarm.id)
    assert calls[-1][1]["entity_id"] == PLAYER


async def test_stop_only_speaker_is_silenced(hass, playback):
    player, alarm, calls = playback
    hass.states.async_set(PLAYER, "idle", {"supported_features": Feature.STOP})
    stops = async_mock_service(hass, "media_player", "media_stop")
    await player.async_fire(alarm)
    await player.async_dismiss(alarm.id)
    assert len(stops) == 1


async def test_failed_replay_is_bounded_and_clears_ringing(hass, freezer, playback):
    player, alarm, calls = playback
    failures = []
    hass.bus.async_listen(EVENT_ALARM_FAILED, failures.append)
    await player.async_fire(alarm)
    failed_calls = async_mock_service(hass, "media_player", "play_media")
    await complete(hass, freezer)
    await advance(hass, freezer, 11)
    await advance(hass, freezer, 11)
    assert len(failed_calls) == 2
    assert len(failures) == 1
    assert not player.ringing
    await advance(hass, freezer, 60)
    assert len(failed_calls) == 2


async def test_dismiss_waits_for_inflight_replay_then_silences_it(hass, freezer, playback):
    player, alarm, calls = playback
    await player.async_fire(alarm)
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_play(call):
        entered.set()
        await release.wait()
        calls.append(("play", dict(call.data)))
        hass.states.async_set(PLAYER, "playing", {"media_content_id": URI})

    hass.services.async_register("media_player", "play_media", delayed_play)
    await advance(hass, freezer, 3)
    hass.states.async_set(PLAYER, "idle", dict(hass.states.get(PLAYER).attributes))
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await asyncio.wait_for(entered.wait(), 2)
    dismiss = hass.async_create_task(player.async_dismiss(alarm.id))
    await asyncio.sleep(0)
    release.set()
    await dismiss
    await hass.async_block_till_done()
    assert calls[-1][0] == "pause"
    assert hass.states.get(PLAYER).state == "paused"
    assert not player.ringing
