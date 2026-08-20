"""Resuming what the alarm interrupted (opt-in, Music Assistant sources only).

The behaviour under test is deliberately conservative: anything that cannot
be restored must fall back to the original "replace the queue" path, because
an alarm that fails to ring is a worse outcome than one that stops the music.
"""

import pytest
from homeassistant.core import HomeAssistant, SupportsResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.wakey.const import DOMAIN

PLAYER = "media_player.bedroom"
ALARM = {
    "name": "Weekday",
    "time": "06:30",
    "media_player": PLAYER,
    "source_uri": "library://track/6018",
    "resume_previous": True,
}

# Shape mirrors a real music_assistant.get_queue response.
QUEUE = {
    PLAYER: {
        "queue_id": "wiim_uuid:FF98",
        "elapsed_time": 19,
        "current_index": 0,
        "current_item": {
            "queue_item_id": "abc123",
            "media_item": {"media_type": "track", "uri": "library://track/6058"},
        },
    }
}


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    config_entry = MockConfigEntry(domain=DOMAIN, data={}, title="Wakey")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def _data(hass):
    return next(iter(hass.data[DOMAIN].values()))


def _playing(hass, app_id: str = "music_assistant", volume: float = 0.42) -> None:
    hass.states.async_set(
        PLAYER, "playing", {"app_id": app_id, "volume_level": volume}
    )


def _mock_services(hass, queue=QUEUE, subsequent=None):
    """Stand in for the media stack, returning a canned queue snapshot.

    `subsequent` is returned from the second get_queue call onward, which is
    what a real player would report once the alarm has taken the queue over.
    Without it a re-capture is indistinguishable from the first one.
    """
    calls = {
        "play_media": async_mock_service(hass, "music_assistant", "play_media"),
        "volume_set": async_mock_service(hass, "media_player", "volume_set"),
        "media_seek": async_mock_service(hass, "media_player", "media_seek"),
        "media_pause": async_mock_service(hass, "media_player", "media_pause"),
        "turn_on": async_mock_service(hass, "media_player", "turn_on"),
    }
    seen = {"n": 0}

    async def _get_queue(call):
        seen["n"] += 1
        if seen["n"] > 1 and subsequent is not None:
            return subsequent
        return queue

    hass.services.async_register(
        "music_assistant",
        "get_queue",
        _get_queue,
        supports_response=SupportsResponse.ONLY,
    )
    return calls


async def test_capture_switches_enqueue_to_play(hass, entry) -> None:
    """The queue must survive the alarm, or there is nothing to resume into."""
    _playing(hass)
    calls = _mock_services(hass)
    data = _data(hass)

    await data.player.async_fire(data.store.async_create(ALARM))
    await hass.async_block_till_done()

    assert calls["play_media"][0].data["enqueue"] == "play"


async def test_dismiss_restores_track_position_and_volume(hass, entry) -> None:
    _playing(hass, volume=0.42)
    calls = _mock_services(hass)
    data = _data(hass)
    alarm = data.store.async_create(ALARM)

    await data.player.async_fire(alarm)
    await hass.async_block_till_done()
    await data.player.async_dismiss(alarm.id)
    await hass.async_block_till_done()

    # Volume goes back before the audio, so the resumed track cannot return at
    # the alarm's volume.
    assert calls["volume_set"][-1].data["volume_level"] == 0.42
    assert calls["play_media"][-1].data["media_id"] == "library://track/6058"
    assert calls["play_media"][-1].data["enqueue"] == "play"
    assert calls["media_seek"][-1].data["seek_position"] == 19
    # Restoring supersedes the alarm audio directly; pausing first would only
    # add a gap.
    assert not calls["media_pause"]


async def test_snooze_restores_then_next_ring_recaptures(hass, entry) -> None:
    """Ambient audio should come back for the length of the snooze."""
    _playing(hass)
    calls = _mock_services(hass)
    data = _data(hass)
    alarm = data.store.async_create(ALARM)

    await data.player.async_fire(alarm)
    await hass.async_block_till_done()
    await data.player.async_snooze(alarm.id)
    await hass.async_block_till_done()

    assert calls["play_media"][-1].data["media_id"] == "library://track/6058"
    assert data.player.ringing[alarm.id].resume is None


async def test_retry_does_not_recapture_the_alarm_itself(hass, entry) -> None:
    """The verify retry re-enters playback; capturing again would remember the
    alarm as the thing to restore."""
    _playing(hass)
    # By the retry the alarm itself is what the queue reports as playing.
    _mock_services(
        hass,
        subsequent={
            PLAYER: {
                "elapsed_time": 3,
                "current_item": {"media_item": {"uri": ALARM["source_uri"]}},
            }
        },
    )
    data = _data(hass)
    alarm = data.store.async_create(ALARM)

    await data.player.async_fire(alarm)
    await hass.async_block_till_done()
    state = data.player.ringing[alarm.id]

    # Second pass, as the failsafe would do it.
    await data.player._async_start_playback(alarm, state)
    await hass.async_block_till_done()

    assert state.resume.uri == "library://track/6058"


async def test_opt_out_keeps_replace_and_pause(hass, entry) -> None:
    _playing(hass)
    calls = _mock_services(hass)
    data = _data(hass)
    alarm = data.store.async_create({**ALARM, "resume_previous": False})

    await data.player.async_fire(alarm)
    await hass.async_block_till_done()
    await data.player.async_dismiss(alarm.id)
    await hass.async_block_till_done()

    assert calls["play_media"][0].data["enqueue"] == "replace"
    assert calls["media_pause"]
    assert not calls["media_seek"]


async def test_non_music_assistant_queue_is_not_resumed(hass, entry) -> None:
    """Another integration's queue cannot be inserted into and resumed."""
    _playing(hass, app_id="spotify")
    calls = _mock_services(hass)
    data = _data(hass)
    alarm = data.store.async_create(ALARM)

    await data.player.async_fire(alarm)
    await hass.async_block_till_done()

    assert calls["play_media"][0].data["enqueue"] == "replace"
    assert data.player.ringing[alarm.id].resume is None


async def test_idle_player_has_nothing_to_resume(hass, entry) -> None:
    hass.states.async_set(PLAYER, "idle", {"app_id": "music_assistant"})
    calls = _mock_services(hass)
    data = _data(hass)
    alarm = data.store.async_create(ALARM)

    await data.player.async_fire(alarm)
    await hass.async_block_till_done()

    assert calls["play_media"][0].data["enqueue"] == "replace"
    assert data.player.ringing[alarm.id].resume is None


async def test_unusable_queue_response_falls_back_to_replace(hass, entry) -> None:
    """A queue with no resolvable URI must not break the alarm."""
    _playing(hass)
    calls = _mock_services(hass, queue={PLAYER: {"elapsed_time": 5, "current_item": None}})
    data = _data(hass)
    alarm = data.store.async_create(ALARM)

    await data.player.async_fire(alarm)
    await hass.async_block_till_done()

    assert calls["play_media"][0].data["enqueue"] == "replace"
