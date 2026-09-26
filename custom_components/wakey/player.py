"""Playback for Wakey — the part that actually wakes you up.

Every service call here is defensive. An alarm that silently fails is worse
than one that logs loudly and falls back, so playback is verified after the
fact rather than assumed to have worked.
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from functools import partial

from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_IDLE,
    STATE_OFF,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ALARM_ID,
    DOMAIN,
    EVENT_ALARM_DISMISSED,
    EVENT_ALARM_FAILED,
    EVENT_ALARM_FIRED,
    EVENT_ALARM_SNOOZED,
    EVENT_PRE_ALARM,
    EXTERNAL_STOP_SETTLE_SECONDS,
    FADE_FLOOR,
    FADE_STEP_SECONDS,
    PLAYBACK_VERIFY_SECONDS,
    SERVICE_CALL_TIMEOUT,
    SIGNAL_RUNTIME_CHANGED,
    SOURCE_MUSIC_ASSISTANT,
)
from .store import AlarmEntry, WakeyStore

_LOGGER = logging.getLogger(__name__)


@dataclass
class ResumeState:
    """What the target player was playing before the alarm interrupted it.

    Only ever populated for Music Assistant queues: `get_queue` is the one
    source that reports both the playing item's URI and its elapsed position,
    and a plain media_player exposes no queue to restore into.
    """

    uri: str
    elapsed: int
    volume: float | None


@dataclass
class RingState:
    """Runtime state for an alarm that is currently ringing or snoozed."""

    alarm_id: str
    alarm: AlarmEntry
    snoozed: bool = False
    attempts: int = 0
    unsubs: list[CALLBACK_TYPE] = field(default_factory=list)
    timer_generation: int = 0
    playback_generation: int = 0
    playback_seen: bool = False
    play_requested: bool = False
    media_id: str | None = None
    # What the target was already playing when this ring started. Until the
    # player reports different media, "playing" is that stream, not the alarm.
    preexisting_media: str | None = None
    preexisting_checked: bool = False
    native_repeat: bool = False
    repeat_attempted: bool = False
    previous_repeat: str | None = None
    replay_pending: bool = False
    fade_unsub: CALLBACK_TYPE | None = None
    # Finish an in-flight play call before silencing/restoring the speaker.
    playback_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # What to put back when this ring ends. None means "nothing to restore" —
    # either the alarm has resume_previous off, or nothing was playing.
    resume: ResumeState | None = None
    # Set once the capture has been attempted, successful or not. The retry in
    # _async_verify re-enters _async_start_playback, and by then the alarm
    # itself is what is playing — capturing again would remember the alarm as
    # the thing to restore.
    resume_checked: bool = False
    # Identifies this specific ring, so a tap on a notification from a prior
    # ring of the same alarm (e.g. before a snooze re-fires it) can't act on
    # the current one. Full-length because it doubles as the authorization on
    # the notification-action path, which has no other permission check.
    token: str = field(default_factory=lambda: uuid.uuid4().hex)

    def cancel(self) -> None:
        self.timer_generation += 1
        for unsub in self.unsubs:
            unsub()
        self.unsubs.clear()


class WakeyPlayer:
    """Runs the firing sequence and tracks what is currently ringing."""

    def __init__(self, hass: HomeAssistant, store: WakeyStore) -> None:
        self.hass = hass
        self.store = store
        self.ringing: dict[str, RingState] = {}

    @property
    def any_ringing(self) -> bool:
        return any(not state.snoozed for state in self.ringing.values())

    @callback
    def _schedule(
        self, state: RingState, delay: float, action: Callable[[], Awaitable[object]]
    ) -> None:
        """Run timers on HA's event loop, only for the ring that scheduled them."""
        generation = state.timer_generation

        async def _run(_now) -> None:
            if unsub in state.unsubs:
                state.unsubs.remove(unsub)
            # Cancellation can happen after HA has already queued the callback.
            if (
                self.ringing.get(state.alarm_id) is state
                and state.timer_generation == generation
            ):
                await action()

        unsub = async_call_later(self.hass, delay, _run)
        state.unsubs.append(unsub)

    def _active(self, state: RingState) -> bool:
        return self.ringing.get(state.alarm_id) is state and not state.snoozed

    def _schedule_verify(self, state: RingState) -> None:
        self._schedule(
            state, PLAYBACK_VERIFY_SECONDS,
            partial(self._async_verify, state.alarm_id, state.playback_generation),
        )

    # --- firing ------------------------------------------------------------

    async def async_fire(self, alarm: AlarmEntry, was_missed: bool = False) -> None:
        """Start an alarm."""
        if not alarm.media_player:
            _LOGGER.error("Alarm %s has no media player configured", alarm.name)
            self._fail(alarm, "no_media_player")
            return

        # Restarting a ringing alarm cleanly replaces the old one.
        if alarm.id in self.ringing:
            await self.async_dismiss(alarm.id, reason="replaced")

        # Edits apply to the next ring. Cleanup must target the speaker and
        # settings that this occurrence actually started with.
        alarm = replace(alarm)
        state = RingState(alarm_id=alarm.id, alarm=alarm)
        self.ringing[alarm.id] = state
        self._watch_playback(state)

        self.store.async_update(alarm.id, {"last_fired": dt_util.utcnow().isoformat()})
        self.hass.bus.async_fire(
            EVENT_ALARM_FIRED,
            {ATTR_ALARM_ID: alarm.id, "name": alarm.name, "missed": was_missed},
        )

        # Notifications and slow service calls must not extend the ring window.
        if alarm.auto_dismiss_minutes:
            self._schedule(
                state, alarm.auto_dismiss_minutes * 60,
                partial(self.async_dismiss, alarm.id, reason="auto"),
            )

        await self._async_start_playback(alarm, state)
        if not self._active(state):
            return
        self._schedule_verify(state)
        await self._async_send_ring_notification(alarm, state)
        async_dispatcher_send(self.hass, SIGNAL_RUNTIME_CHANGED)

    async def async_run_pre_alarm(self, alarm: AlarmEntry) -> None:
        """Run the pre-alarm hook — lights, heating, whatever they wired up.

        Fires the event regardless of whether a script is configured, so an
        automation can trigger on it without needing a script at all.
        """
        self.hass.bus.async_fire(
            EVENT_PRE_ALARM,
            {
                ATTR_ALARM_ID: alarm.id,
                "name": alarm.name,
                "minutes_before": alarm.pre_alarm_minutes,
            },
        )
        if alarm.pre_alarm_script:
            _LOGGER.info(
                "Pre-alarm for %s: running %s", alarm.name, alarm.pre_alarm_script
            )
            # Not blocking: a sunrise script may run for the whole pre-alarm
            # window, and waiting for it would delay nothing useful.
            await self._call(
                "script", "turn_on", {ATTR_ENTITY_ID: alarm.pre_alarm_script}
            )

    async def _async_send_ring_notification(self, alarm: AlarmEntry, state: RingState) -> None:
        """Push a dismiss/snooze-actionable notification for a ringing alarm.

        The action ids carry the ring's token, so a tap on a notification from
        a previous ring of this alarm (see mobile_app_notification_action in
        __init__.py) can never act on the current one.
        """
        if not alarm.notify_targets:
            return
        data = {
            "actions": [
                {
                    "action": f"{DOMAIN}_dismiss_{alarm.id}_{state.token}",
                    "title": "Dismiss",
                },
                {
                    "action": f"{DOMAIN}_snooze_{alarm.id}_{state.token}",
                    "title": "Snooze",
                },
            ],
            "clickAction": f"/{DOMAIN}",
            "tag": f"{DOMAIN}_{alarm.id}",
            "push": {"interruption-level": "time-sensitive"},
        }
        for target in alarm.notify_targets:
            await self._call(
                "notify",
                "send_message",
                {
                    ATTR_ENTITY_ID: target,
                    "message": f"{alarm.name} is ringing",
                    "title": "Wakey",
                    "data": data,
                },
            )

    async def _async_start_playback(self, alarm: AlarmEntry, state: RingState) -> None:
        async with state.playback_lock:
            if self._active(state):
                await self._async_start_locked(alarm, state)

    async def _async_start_locked(self, alarm: AlarmEntry, state: RingState) -> None:
        state.attempts += 1
        player = alarm.media_player

        current = self.hass.states.get(player)
        if current is None:
            _LOGGER.error("Alarm %s targets unknown entity %s", alarm.name, player)
            self._fail(alarm, "unknown_entity")
            return
        if current.state == STATE_UNAVAILABLE:
            _LOGGER.warning("%s is unavailable — trying anyway", player)

        if not state.preexisting_checked:
            state.preexisting_checked = True
            if current.state == STATE_PLAYING:
                state.preexisting_media = current.attributes.get("media_content_id")

        if not state.resume_checked:
            await self._async_capture_resume(alarm, state)

        if current.state in (STATE_OFF, STATE_UNKNOWN):
            await self._call("media_player", "turn_on", {ATTR_ENTITY_ID: player})

        start_volume = FADE_FLOOR if alarm.fade_seconds > 0 else alarm.volume
        await self._call(
            "media_player",
            "volume_set",
            {ATTR_ENTITY_ID: player, "volume_level": start_volume},
        )

        if not self._active(state):
            return
        await self._async_play_source(alarm, state)

        if self._active(state) and alarm.fade_seconds > 0:
            self._start_fade(alarm, state, start_volume)

    async def _async_play_source(self, alarm: AlarmEntry, state: RingState) -> None:
        """Play without restarting the fade, ring deadline, or resume capture."""
        player = alarm.media_player
        state.playback_generation += 1
        state.playback_seen = False
        state.play_requested = True
        state.media_id = None
        current = self.hass.states.get(player)
        if alarm.repeat_playback and state.previous_repeat is None and current:
            previous = current.attributes.get("repeat")
            features = current.attributes.get("supported_features", 0)
            if features & MediaPlayerEntityFeature.REPEAT_SET and previous in ("off", "one", "all"):
                state.previous_repeat = previous

        if self._use_music_assistant(alarm):
            # media_type is deliberately omitted: the stored value may be a
            # track, album or playlist URI, and Music Assistant resolves the
            # type from the URI itself. Forcing "track" breaks the others.
            await self._call(
                "music_assistant",
                "play_media",
                {
                    ATTR_ENTITY_ID: player,
                    "media_id": alarm.source_uri,
                    # "replace" wipes the queue; "play" inserts at the current
                    # position and leaves the rest of it intact underneath, so
                    # there is something left to resume into.
                    "enqueue": "play" if state.resume is not None else "replace",
                },
            )
        else:
            await self._call(
                "media_player",
                "play_media",
                {
                    ATTR_ENTITY_ID: player,
                    "media_content_id": alarm.source_uri,
                    "media_content_type": "music",
                },
            )

        if (
            self._active(state) and state.previous_repeat is not None
            and (state.native_repeat or not state.repeat_attempted)
        ):
            state.repeat_attempted = True
            state.native_repeat = await self._call(
                "media_player", "repeat_set", {ATTR_ENTITY_ID: player, "repeat": "one"}
            )

    def _watch_playback(self, state: RingState) -> None:
        """Remember short playback and repeat only an observed completed item."""

        @callback
        def _changed(event) -> None:
            if not self._active(state) or not state.play_requested:
                return
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            if new is None:
                return
            if new.state == STATE_PLAYING:
                if self._playing_alarm(state, new):
                    state.playback_seen = True
                    if state.media_id is None:
                        state.media_id = new.attributes.get("media_content_id")
                return
            if (
                new.state in (STATE_PAUSED, STATE_OFF)
                and state.playback_seen
                and old is not None
                and old.state == STATE_PLAYING
                and old.attributes.get("media_content_id") in (None, state.media_id)
            ):
                # Wakey only pauses a ring it has already stopped tracking, so
                # this is someone else silencing the alarm (issue #3).
                self._schedule(
                    state, EXTERNAL_STOP_SETTLE_SECONDS,
                    partial(self._async_check_external_stop, state),
                )
                return
            if (
                not state.alarm.repeat_playback
                or state.native_repeat
                or state.replay_pending
                or not state.playback_seen
                or old is None
                or old.state != STATE_PLAYING
                or new.state != STATE_IDLE
                or not state.media_id
                or old.attributes.get("media_content_id") != state.media_id
                or new.attributes.get("media_content_id") not in (None, state.media_id)
                or not self._completed(old)
            ):
                return
            # A short delay allows an explicit stop/track change to settle.
            state.replay_pending = True
            self._schedule(state, 0.5, partial(self._async_replay, state))

        state.unsubs.append(async_track_state_change_event(
            self.hass, [state.alarm.media_player], _changed
        ))

    @staticmethod
    def _playing_alarm(state: RingState, current) -> bool:
        """Whether the player is playing the alarm, not what it interrupted.

        A player that was already playing stays "playing" if play_media is
        silently ignored, so state alone cannot prove the alarm sounded (issue
        #4). Without a media id to compare, fall back to trusting the state.
        """
        if current is None or current.state != STATE_PLAYING:
            return False
        if state.preexisting_media is None:
            return True
        media = current.attributes.get("media_content_id")
        return media != state.preexisting_media or media == state.alarm.source_uri

    async def _async_check_external_stop(self, state: RingState) -> None:
        current = self.hass.states.get(state.alarm.media_player)
        if not self._active(state) or current is None:
            return
        if current.state not in (STATE_PAUSED, STATE_OFF):
            return
        _LOGGER.info(
            "%s was silenced outside Wakey — treating %s as dismissed",
            state.alarm.media_player, state.alarm.name,
        )
        await self.async_dismiss(state.alarm_id, reason="external")

    @staticmethod
    def _completed(current) -> bool:
        """An idle transition alone may be a manual stop, not end of media."""
        try:
            duration = float(current.attributes.get("media_duration", 0))
            position = float(current.attributes["media_position"])
            updated = current.attributes.get("media_position_updated_at")
            if isinstance(updated, str):
                updated = dt_util.parse_datetime(updated)
            if isinstance(updated, datetime) and updated.tzinfo is not None:
                position += max(0, (dt_util.utcnow() - updated).total_seconds())
            return (
                math.isfinite(duration) and math.isfinite(position) and duration > 0
                and position >= duration - min(0.5, duration * 0.05)
            )
        except (KeyError, TypeError, ValueError):
            return False

    async def _async_replay(self, state: RingState) -> None:
        async with state.playback_lock:
            state.replay_pending = False
            current = self.hass.states.get(state.alarm.media_player)
            if not self._active(state) or current is None or current.state != STATE_IDLE:
                return
            if current.attributes.get("media_content_id") not in (None, state.media_id):
                return
            state.attempts = 1
            await self._async_play_source(state.alarm, state)
            if self._active(state):
                self._schedule_verify(state)

    async def _restore_repeat(self, alarm: AlarmEntry, state: RingState) -> None:
        previous = state.previous_repeat
        state.previous_repeat = None
        state.native_repeat = False
        if previous is None:
            return
        current = self.hass.states.get(alarm.media_player)
        # Respect a user's explicit repeat-mode change during the ring.
        if current is not None and current.attributes.get("repeat") not in (None, "one"):
            return
        await self._call(
            "media_player", "repeat_set",
            {ATTR_ENTITY_ID: alarm.media_player, "repeat": previous},
        )

    @callback
    def _use_music_assistant(self, alarm: AlarmEntry) -> bool:
        """Whether this alarm can actually ring through Music Assistant.

        The panel stores source_kind=music_assistant by default, but blindly
        calling music_assistant.play_media silently does nothing when Music
        Assistant is not installed, when the target is some other integration's
        player (its services only match its own entities — a Cast speaker just
        chirps and stays quiet), or when the browsed pick is a media-source URI
        Music Assistant cannot resolve. Any of those routes through the plain
        media_player path instead, which every player understands.
        """
        if alarm.source_kind != SOURCE_MUSIC_ASSISTANT:
            return False
        if alarm.source_uri.startswith("media-source://"):
            return False
        if not self.hass.services.has_service(SOURCE_MUSIC_ASSISTANT, "play_media"):
            _LOGGER.debug(
                "Music Assistant is not installed — playing %s via media_player",
                alarm.name,
            )
            return False
        entry = er.async_get(self.hass).async_get(alarm.media_player)
        # Only override on positive evidence: an unregistered entity (template
        # players, tests) keeps whatever the alarm says.
        if entry is not None and entry.platform != SOURCE_MUSIC_ASSISTANT:
            _LOGGER.debug(
                "%s belongs to %s, not Music Assistant — playing %s via media_player",
                alarm.media_player,
                entry.platform,
                alarm.name,
            )
            return False
        return True

    # --- resume ------------------------------------------------------------

    async def _async_capture_resume(self, alarm: AlarmEntry, state: RingState) -> None:
        """Remember what is playing, so dismissing the alarm can put it back.

        Every branch that cannot restore leaves `state.resume` as None, which
        keeps the alarm on the original "replace" path — an alarm that cannot
        be resumed from must still be an alarm that reliably plays.
        """
        state.resume_checked = True
        # Restoring goes through Music Assistant's queue, so an alarm that will
        # not ring through it has nothing it could safely put back.
        if not alarm.resume_previous or not self._use_music_assistant(alarm):
            return

        current = self.hass.states.get(alarm.media_player)
        if current is None or current.state != STATE_PLAYING:
            return
        # A queue owned by some other integration cannot be inserted into and
        # resumed the way a Music Assistant one can.
        if current.attributes.get("app_id") != "music_assistant":
            return

        response = await self._call_with_response(
            "music_assistant", "get_queue", {ATTR_ENTITY_ID: alarm.media_player}
        )
        queue = (response or {}).get(alarm.media_player)
        if not queue:
            return
        media_item = (queue.get("current_item") or {}).get("media_item") or {}
        if not (uri := media_item.get("uri")):
            return

        state.resume = ResumeState(
            uri=uri,
            elapsed=int(queue.get("elapsed_time") or 0),
            volume=current.attributes.get("volume_level"),
        )
        _LOGGER.debug(
            "%s will resume %s at %ss after %s", alarm.media_player, uri, state.resume.elapsed, alarm.name
        )

    async def _async_restore_previous(self, alarm: AlarmEntry, state: RingState) -> None:
        """Put back what the alarm interrupted.

        Re-inserting the captured URI is deliberate. The interrupted item is
        still in the queue, but it sits *behind* the inserted alarm, and
        neither media_next_track (which skips past it to the following item)
        nor media_previous_track (which only restarts the current one) can get
        back to it. Inserting a fresh copy and seeking is the one sequence
        that works through the public services.
        """
        resume = state.resume
        if resume is None:
            return
        # Cleared first: a restore must never run twice for one ring, however
        # dismiss and snooze happen to interleave.
        state.resume = None

        # Volume goes back before the audio does, so the resumed track cannot
        # come back at the alarm's volume.
        if resume.volume is not None:
            await self._call(
                "media_player",
                "volume_set",
                {ATTR_ENTITY_ID: alarm.media_player, "volume_level": resume.volume},
            )
        await self._call(
            "music_assistant",
            "play_media",
            {
                ATTR_ENTITY_ID: alarm.media_player,
                "media_id": resume.uri,
                "enqueue": "play",
            },
        )
        if resume.elapsed > 0:
            await self._call(
                "media_player",
                "media_seek",
                {ATTR_ENTITY_ID: alarm.media_player, "seek_position": resume.elapsed},
            )
        _LOGGER.info("Resumed %s on %s", resume.uri, alarm.media_player)

    # --- fade --------------------------------------------------------------

    @callback
    def _start_fade(self, alarm: AlarmEntry, state: RingState, start: float) -> None:
        if state.fade_unsub is not None:
            state.fade_unsub()
            if state.fade_unsub in state.unsubs:
                state.unsubs.remove(state.fade_unsub)
        steps = max(1, alarm.fade_seconds // FADE_STEP_SECONDS)
        increment = (alarm.volume - start) / steps
        progress = {"level": start, "done": 0}

        async def _step(_now) -> None:
            async with state.playback_lock:
                if not self._active(state) or state.fade_unsub is not unsub:
                    return
                progress["done"] += 1
                progress["level"] = min(alarm.volume, progress["level"] + increment)
                await self._call(
                    "media_player",
                    "volume_set",
                    {ATTR_ENTITY_ID: alarm.media_player, "volume_level": round(progress["level"], 3)},
                )
                if progress["done"] >= steps:
                    unsub()
                    state.fade_unsub = None
                    if unsub in state.unsubs:
                        state.unsubs.remove(unsub)

        unsub = async_track_time_interval(
            self.hass, _step, timedelta(seconds=FADE_STEP_SECONDS)
        )
        state.unsubs.append(unsub)
        state.fade_unsub = unsub

    # --- failsafe ----------------------------------------------------------

    async def _async_verify(self, alarm_id: str, generation: int | None = None) -> None:
        """Did playback actually start? If not, retry, then fall back."""
        state = self.ringing.get(alarm_id)
        if state is None or state.snoozed:
            return
        alarm = state.alarm
        if generation is not None and generation != state.playback_generation:
            return
        # A short clip may have ended before the ten-second verification.
        if state.playback_seen:
            return

        current = self.hass.states.get(alarm.media_player)
        if self._playing_alarm(state, current):
            return

        observed = current.state if current else "missing"
        if observed == STATE_PLAYING:
            observed = "previous_media"

        if state.attempts < 2:
            _LOGGER.warning(
                "%s did not start playing (state=%s) — retrying once", alarm.media_player, observed
            )
            await self._async_start_playback(alarm, state)
            if self._active(state):
                self._schedule_verify(state)
            return

        _LOGGER.error(
            "Alarm %s failed: %s never reached 'playing' (state=%s) after %d attempts",
            alarm.name,
            alarm.media_player,
            observed,
            state.attempts,
        )
        self._fail(alarm, f"playback_not_started:{observed}")

    @callback
    def _fail(self, alarm: AlarmEntry, reason: str) -> None:
        """Last resort. Make the failure impossible to miss."""
        if (state := self.ringing.pop(alarm.id, None)) is not None:
            state.cancel()
            self.hass.async_create_task(self._finish_playback(state))
            async_dispatcher_send(self.hass, SIGNAL_RUNTIME_CHANGED)
        self.hass.bus.async_fire(
            EVENT_ALARM_FAILED,
            {ATTR_ALARM_ID: alarm.id, "name": alarm.name, "reason": reason},
        )
        self.hass.async_create_task(
            self._call(
                "persistent_notification",
                "create",
                {
                    "title": "Wakey alarm failed",
                    "message": (
                        f"**{alarm.name}** was due but playback did not start on "
                        f"`{alarm.media_player}` ({reason})."
                    ),
                    "notification_id": f"{DOMAIN}_failed_{alarm.id}",
                },
            )
        )

    # --- snooze / dismiss --------------------------------------------------

    async def async_snooze(self, alarm_id: str, minutes: int | None = None) -> bool:
        state = self.ringing.get(alarm_id)
        if state is None or state.snoozed:
            return False
        alarm = state.alarm

        state.cancel()
        state.snoozed = True
        state.attempts = 0
        # Resuming for the duration of the snooze is the point: the ambient
        # audio comes back, and the next ring captures it again from scratch.
        await self._finish_playback(state)
        if self.ringing.get(alarm_id) is not state:
            return False

        delay = (minutes if minutes is not None else alarm.snooze_minutes) * 60
        self._schedule(
            state, delay, partial(self._async_wake_from_snooze, alarm_id)
        )
        self.hass.bus.async_fire(
            EVENT_ALARM_SNOOZED,
            {ATTR_ALARM_ID: alarm.id, "name": alarm.name, "minutes": delay // 60},
        )
        async_dispatcher_send(self.hass, SIGNAL_RUNTIME_CHANGED)
        _LOGGER.info("Snoozed %s for %d minutes", alarm.name, delay // 60)
        return True

    async def _async_wake_from_snooze(self, alarm_id: str) -> None:
        alarm = self.store.async_get(alarm_id)
        if alarm is None or alarm_id not in self.ringing:
            return
        await self.async_fire(alarm)

    async def async_dismiss(self, alarm_id: str, reason: str = "user") -> bool:
        state = self.ringing.pop(alarm_id, None)
        if state is None:
            return False
        state.cancel()

        alarm = state.alarm
        # Snoozing already restored/paused the speaker. Dismissing during
        # snooze must leave the resumed ambient audio alone.
        if not state.snoozed:
            await self._finish_playback(state)
        else:
            async with state.playback_lock:
                pass  # Wait for in-flight snooze cleanup before replacing this ring.
        self.hass.bus.async_fire(
            EVENT_ALARM_DISMISSED,
            {ATTR_ALARM_ID: alarm_id, "name": alarm.name, "reason": reason},
        )
        _LOGGER.info("Dismissed %s (%s)", alarm.name, reason)

        async_dispatcher_send(self.hass, SIGNAL_RUNTIME_CHANGED)
        return True

    async def async_dismiss_all(self) -> None:
        for alarm_id in list(self.ringing):
            await self.async_dismiss(alarm_id)

    async def async_snooze_all(self) -> None:
        for alarm_id in list(self.ringing):
            await self.async_snooze(alarm_id)

    async def _finish_playback(self, state: RingState) -> None:
        async with state.playback_lock:
            await self._restore_repeat(state.alarm, state)
            await self._stop_playback(state.alarm, state)

    async def _stop_playback(self, alarm: AlarmEntry, state: RingState | None = None) -> None:
        """Silence the alarm, by restoring what it interrupted where possible.

        Restoring *instead of* pausing is what avoids a gap: the resume call
        supersedes the alarm audio directly, so nothing needs silencing first.
        """
        if state is not None and state.resume is not None:
            await self._async_restore_previous(alarm, state)
            return
        current = self.hass.states.get(alarm.media_player)
        if current is None or current.state in (STATE_OFF, STATE_UNAVAILABLE):
            return
        features = current.attributes.get("supported_features", 0)
        service = "media_pause"
        if features & MediaPlayerEntityFeature.STOP and not features & MediaPlayerEntityFeature.PAUSE:
            service = "media_stop"
        if not await self._call("media_player", service, {ATTR_ENTITY_ID: alarm.media_player}):
            if service == "media_pause" and features & MediaPlayerEntityFeature.STOP:
                await self._call("media_player", "media_stop", {ATTR_ENTITY_ID: alarm.media_player})

    # --- helpers -----------------------------------------------------------

    async def _call(self, domain: str, service: str, data: dict) -> bool:
        """Call a service, logging rather than raising on failure.

        One failed step (a player that can't turn_on, say) must not abort the
        rest of the sequence. The timeout matters: a blocking call into an
        integration that has wedged would otherwise hang the whole firing
        sequence, and a silent alarm is the one outcome worth engineering
        against.
        """
        try:
            async with asyncio.timeout(SERVICE_CALL_TIMEOUT):
                await self.hass.services.async_call(domain, service, data, blocking=True)
        except TimeoutError:
            _LOGGER.warning(
                "%s.%s on %s did not return within %ss",
                domain,
                service,
                data.get(ATTR_ENTITY_ID),
                SERVICE_CALL_TIMEOUT,
            )
            return False
        except Exception as err:  # noqa: BLE001 - any failure here is non-fatal
            _LOGGER.warning("%s.%s failed (%s): %s", domain, service, data.get(ATTR_ENTITY_ID), err)
            return False
        return True

    async def _call_with_response(
        self, domain: str, service: str, data: dict
    ) -> dict | None:
        """Call a service that returns data, logging rather than raising.

        Same contract as `_call`: a failure here degrades the ring (no resume)
        rather than aborting it.
        """
        try:
            async with asyncio.timeout(SERVICE_CALL_TIMEOUT):
                return await self.hass.services.async_call(
                    domain,
                    service,
                    data,
                    blocking=True,
                    return_response=True,
                )
        except TimeoutError:
            _LOGGER.warning(
                "%s.%s on %s did not return within %ss",
                domain,
                service,
                data.get(ATTR_ENTITY_ID),
                SERVICE_CALL_TIMEOUT,
            )
        except Exception as err:  # noqa: BLE001 - any failure here is non-fatal
            _LOGGER.warning("%s.%s failed (%s): %s", domain, service, data.get(ATTR_ENTITY_ID), err)
        return None

    async def async_shutdown(self) -> None:
        for alarm_id in list(self.ringing):
            await self.async_dismiss(alarm_id, reason="unload")
