"""Playback for Wakey — the part that actually wakes you up.

Every service call here is defensive. An alarm that silently fails is worse
than one that logs loudly and falls back, so playback is verified after the
fact rather than assumed to have worked.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_OFF,
    STATE_PLAYING,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ALARM_ID,
    DOMAIN,
    EVENT_ALARM_DISMISSED,
    EVENT_ALARM_FAILED,
    EVENT_ALARM_FIRED,
    EVENT_ALARM_SNOOZED,
    EVENT_PRE_ALARM,
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
    snoozed: bool = False
    attempts: int = 0
    unsubs: list[CALLBACK_TYPE] = field(default_factory=list)
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

    # --- firing ------------------------------------------------------------

    async def async_fire(self, alarm: AlarmEntry, was_missed: bool = False) -> None:
        """Start an alarm."""
        if not alarm.media_player:
            _LOGGER.error("Alarm %s has no media player configured", alarm.name)
            self._fail(alarm, "no_media_player")
            return

        # Restarting a ringing alarm cleanly replaces the old one.
        if (existing := self.ringing.pop(alarm.id, None)) is not None:
            existing.cancel()

        state = RingState(alarm_id=alarm.id)
        self.ringing[alarm.id] = state

        self.store.async_update(alarm.id, {"last_fired": dt_util.utcnow().isoformat()})
        self.hass.bus.async_fire(
            EVENT_ALARM_FIRED,
            {ATTR_ALARM_ID: alarm.id, "name": alarm.name, "missed": was_missed},
        )

        await self._async_start_playback(alarm, state)
        await self._async_send_ring_notification(alarm, state)

        # Failsafe: come back and check it actually started.
        state.unsubs.append(
            async_call_later(
                self.hass,
                PLAYBACK_VERIFY_SECONDS,
                lambda _now: self.hass.async_create_task(self._async_verify(alarm.id)),
            )
        )

        if alarm.auto_dismiss_minutes:
            state.unsubs.append(
                async_call_later(
                    self.hass,
                    alarm.auto_dismiss_minutes * 60,
                    lambda _now: self.hass.async_create_task(
                        self.async_dismiss(alarm.id, reason="auto")
                    ),
                )
            )

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
        state.attempts += 1
        player = alarm.media_player

        current = self.hass.states.get(player)
        if current is None:
            _LOGGER.error("Alarm %s targets unknown entity %s", alarm.name, player)
            self._fail(alarm, "unknown_entity")
            return
        if current.state == STATE_UNAVAILABLE:
            _LOGGER.warning("%s is unavailable — trying anyway", player)

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

        if alarm.source_kind == SOURCE_MUSIC_ASSISTANT:
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

        if alarm.fade_seconds > 0:
            self._start_fade(alarm, state, start_volume)

    # --- resume ------------------------------------------------------------

    async def _async_capture_resume(self, alarm: AlarmEntry, state: RingState) -> None:
        """Remember what is playing, so dismissing the alarm can put it back.

        Every branch that cannot restore leaves `state.resume` as None, which
        keeps the alarm on the original "replace" path — an alarm that cannot
        be resumed from must still be an alarm that reliably plays.
        """
        state.resume_checked = True
        if not alarm.resume_previous or alarm.source_kind != SOURCE_MUSIC_ASSISTANT:
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
        steps = max(1, alarm.fade_seconds // FADE_STEP_SECONDS)
        increment = (alarm.volume - start) / steps
        progress = {"level": start, "done": 0}

        async def _step(_now) -> None:
            progress["done"] += 1
            progress["level"] = min(alarm.volume, progress["level"] + increment)
            await self._call(
                "media_player",
                "volume_set",
                {ATTR_ENTITY_ID: alarm.media_player, "volume_level": round(progress["level"], 3)},
            )
            if progress["done"] >= steps:
                unsub()

        unsub = async_track_time_interval(
            self.hass, _step, timedelta(seconds=FADE_STEP_SECONDS)
        )
        state.unsubs.append(unsub)

    # --- failsafe ----------------------------------------------------------

    async def _async_verify(self, alarm_id: str) -> None:
        """Did playback actually start? If not, retry, then fall back."""
        state = self.ringing.get(alarm_id)
        alarm = self.store.async_get(alarm_id)
        if state is None or alarm is None or state.snoozed:
            return

        current = self.hass.states.get(alarm.media_player)
        if current is not None and current.state == STATE_PLAYING:
            return

        observed = current.state if current else "missing"

        if state.attempts < 2:
            _LOGGER.warning(
                "%s did not start playing (state=%s) — retrying once", alarm.media_player, observed
            )
            await self._async_start_playback(alarm, state)
            state.unsubs.append(
                async_call_later(
                    self.hass,
                    PLAYBACK_VERIFY_SECONDS,
                    lambda _now: self.hass.async_create_task(self._async_verify(alarm_id)),
                )
            )
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
        alarm = self.store.async_get(alarm_id)
        state = self.ringing.get(alarm_id)
        if alarm is None or state is None:
            return False

        state.cancel()
        state.snoozed = True
        state.attempts = 0
        # Resuming for the duration of the snooze is the point: the ambient
        # audio comes back, and the next ring captures it again from scratch.
        await self._stop_playback(alarm, state)

        delay = (minutes if minutes is not None else alarm.snooze_minutes) * 60
        state.unsubs.append(
            async_call_later(
                self.hass,
                delay,
                lambda _now: self.hass.async_create_task(self._async_wake_from_snooze(alarm_id)),
            )
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

        if (alarm := self.store.async_get(alarm_id)) is not None:
            await self._stop_playback(alarm, state)
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
        await self._call("media_player", "media_pause", {ATTR_ENTITY_ID: alarm.media_player})

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

    @callback
    def async_shutdown(self) -> None:
        for state in self.ringing.values():
            state.cancel()
        self.ringing.clear()
