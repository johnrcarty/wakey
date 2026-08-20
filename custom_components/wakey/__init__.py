"""The Wakey integration — an alarm clock for Home Assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.auth import EVENT_USER_REMOVED
from homeassistant.auth.models import User
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
    UnknownUser,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    ATTR_ALARM_ID,
    ATTR_OWNER_ID,
    DOMAIN,
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
    PLATFORMS,
    REPEAT_MODES,
    SIGNAL_ALARM_REMOVED,
    SOURCE_KINDS,
)
from .intent import async_remove_intents, async_setup_intents
from .panel import async_register_panel, async_unregister_panel
from .permissions import (
    AlarmNotVisible,
    WakeyPermissionError,
    async_assert_can_modify,
    async_assert_player_allowed,
    async_sanitize_payload,
    async_visible_ringing,
)
from .player import WakeyPlayer
from .scheduler import WakeyScheduler
from .store import WakeyStore
from .websocket import async_register as async_register_websocket

_LOGGER = logging.getLogger(__name__)

SERVICE_CREATE = "create"
SERVICE_UPDATE = "update"
SERVICE_DELETE = "delete"
SERVICE_SNOOZE = "snooze"
SERVICE_DISMISS = "dismiss"
SERVICE_SKIP_NEXT = "skip_next"
SERVICE_TRIGGER_NOW = "trigger_now"

# Fields shared by create and update. Everything except the identity of the
# alarm is optional so update can be a partial patch.
_ALARM_FIELDS = {
    vol.Optional("name"): cv.string,
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("time"): cv.string,
    vol.Optional("repeat"): vol.In(REPEAT_MODES),
    vol.Optional("weekdays"): vol.All(cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(0, 6))]),
    vol.Optional("date"): cv.string,
    vol.Optional("media_player"): cv.entity_id,
    vol.Optional("source_uri"): cv.string,
    vol.Optional("source_kind"): vol.In(SOURCE_KINDS),
    vol.Optional("volume"): vol.All(vol.Coerce(float), vol.Range(0.0, 1.0)),
    vol.Optional("fade_seconds"): vol.All(vol.Coerce(int), vol.Range(0, 3600)),
    vol.Optional("resume_previous"): cv.boolean,
    vol.Optional("snooze_minutes"): vol.All(vol.Coerce(int), vol.Range(1, 120)),
    vol.Optional("auto_dismiss_minutes"): vol.All(vol.Coerce(int), vol.Range(1, 240)),
    vol.Optional("pre_alarm_minutes"): vol.All(vol.Coerce(int), vol.Range(0, 240)),
    vol.Optional("pre_alarm_script"): vol.Any(cv.entity_id, None),
    vol.Optional("notify_targets"): vol.All(cv.ensure_list, [cv.entity_id]),
    # Lets an automation, which has no user of its own, say who an alarm
    # belongs to. Ignored when a non-admin makes the call.
    vol.Optional(ATTR_OWNER_ID): vol.Any(cv.string, None),
}

CREATE_SCHEMA = vol.Schema(
    {
        **_ALARM_FIELDS,
        vol.Required("time"): cv.string,
        vol.Required("media_player"): cv.entity_id,
        vol.Required("source_uri"): cv.string,
    }
)
UPDATE_SCHEMA = vol.Schema({**_ALARM_FIELDS, vol.Required(ATTR_ALARM_ID): cv.string})
TARGET_SCHEMA = vol.Schema({vol.Required(ATTR_ALARM_ID): cv.string})
SNOOZE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ALARM_ID): cv.string,
        vol.Optional("minutes"): vol.All(vol.Coerce(int), vol.Range(1, 120)),
    }
)
DISMISS_SCHEMA = vol.Schema({vol.Optional(ATTR_ALARM_ID): cv.string})
SKIP_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ALARM_ID): cv.string, vol.Optional("skip", default=True): cv.boolean}
)


@dataclass
class WakeyData:
    """Everything the integration needs at runtime."""

    store: WakeyStore
    scheduler: WakeyScheduler
    player: WakeyPlayer


def _get_data(hass: HomeAssistant) -> WakeyData | None:
    """Wakey is single-instance, so there is only ever one of these."""
    entries = hass.data.get(DOMAIN, {})
    return next(iter(entries.values()), None)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wakey from a config entry."""
    store = WakeyStore(hass)
    await store.async_load()

    player = WakeyPlayer(hass, store)
    scheduler = WakeyScheduler(
        hass, store, player.async_fire, player.async_run_pre_alarm
    )

    data = WakeyData(store=store, scheduler=scheduler, player=player)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await scheduler.async_start()

    # Deleting an alarm removes its device, which takes its entities with it.
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ALARM_REMOVED, _make_device_cleanup(hass))
    )
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_USER_REMOVED, _make_user_cleanup(hass))
    )
    entry.async_on_unload(
        hass.bus.async_listen(
            EVENT_MOBILE_APP_NOTIFICATION_ACTION,
            _make_notification_action_handler(hass),
        )
    )

    _async_register_services(hass)
    async_register_websocket(hass)
    await async_register_panel(hass)
    await async_setup_intents(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False

    data: WakeyData = hass.data[DOMAIN].pop(entry.entry_id)
    data.scheduler.async_stop()
    data.player.async_shutdown()
    await data.store.async_save_now()
    async_unregister_panel(hass)
    async_remove_intents(hass)

    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
        for service in (
            SERVICE_CREATE,
            SERVICE_UPDATE,
            SERVICE_DELETE,
            SERVICE_SNOOZE,
            SERVICE_DISMISS,
            SERVICE_SKIP_NEXT,
            SERVICE_TRIGGER_NOW,
        ):
            hass.services.async_remove(DOMAIN, service)

    return True


@callback
def _make_device_cleanup(hass: HomeAssistant):
    @callback
    def _cleanup(alarm_id: str) -> None:
        registry = dr.async_get(hass)
        device = registry.async_get_device(identifiers={(DOMAIN, alarm_id)})
        if device is not None:
            registry.async_remove_device(device.id)

    return _cleanup


@callback
def _make_user_cleanup(hass: HomeAssistant):
    """Drop a deleted user's speaker policy and flag what they left behind.

    Their alarms are deliberately not deleted — someone else in the house may
    still be relying on one — but they become unowned, so only an admin can
    see them. Say which, or they will simply be forgotten.
    """

    @callback
    def _cleanup(event: Event) -> None:
        if (data := _get_data(hass)) is None:
            return
        user_id = event.data.get("user_id")
        if user_id is None:
            return
        data.store.async_delete_policy(user_id)
        orphaned = data.store.async_for_owner(user_id)
        for alarm in orphaned:
            data.store.async_update(alarm.id, {ATTR_OWNER_ID: None})
        if orphaned:
            _LOGGER.warning(
                "Home Assistant user %s was removed, leaving %d Wakey alarm(s) "
                "with no owner (%s). They still fire, but only administrators "
                "can see them",
                user_id,
                len(orphaned),
                ", ".join(a.name for a in orphaned),
            )

    return _cleanup


def _parse_notification_action(action: str) -> tuple[str, str, str] | None:
    """Parse a Wakey notification action id into (kind, alarm_id, token).

    Action ids look like "wakey_dismiss_<alarm_id>_<token>" or
    "wakey_snooze_<alarm_id>_<token>" (see player.py's
    _async_send_ring_notification). Anything else is not ours to handle. Token
    is split off with rpartition rather than a fixed separator count, since
    alarm ids are themselves plain hex and never contain an underscore.
    """
    for kind, prefix in (
        ("dismiss", f"{DOMAIN}_dismiss_"),
        ("snooze", f"{DOMAIN}_snooze_"),
    ):
        if action.startswith(prefix):
            alarm_id, _, token = action[len(prefix) :].rpartition("_")
            if alarm_id and token:
                return kind, alarm_id, token
    return None


def _make_notification_action_handler(hass: HomeAssistant):
    """Route a tapped notification action back to dismiss/snooze.

    No ownership check: the action id itself is the authorisation. It is
    opaque and scoped to one specific ring (via the token), so only someone
    who actually received that push could have produced it.
    """

    async def _handle(event: Event) -> None:
        if (parsed := _parse_notification_action(event.data.get("action", ""))) is None:
            return
        if (data := _get_data(hass)) is None:
            return
        kind, alarm_id, token = parsed
        state = data.player.ringing.get(alarm_id)
        if state is None or state.token != token:
            _LOGGER.debug(
                "Ignoring stale or unknown Wakey notification action for alarm %s",
                alarm_id,
            )
            return
        if kind == "dismiss":
            await data.player.async_dismiss(alarm_id, reason="notification")
        else:
            await data.player.async_snooze(alarm_id)

    return _handle


async def _async_caller(hass: HomeAssistant, call: ServiceCall) -> tuple[str | None, bool]:
    """Who is making this service call, and are they an administrator?

    context.user_id is None for automations, scripts fired by a trigger, and
    the scheduler. Those are treated as system calls and are unrestricted —
    the alternative would break every existing automation on upgrade, and an
    automation has no user whose permissions could sensibly be applied.

    Worth knowing: Home Assistant applies no permission check of its own to
    plain domain services (only entity-targeted ones), so before this every
    Wakey service was callable by any authenticated user.
    """
    user_id = call.context.user_id
    if user_id is None:
        return None, True
    user: User | None = await hass.auth.async_get_user(user_id)
    if user is None:
        raise UnknownUser(context=call.context)
    return user_id, user.is_admin


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain services. Idempotent."""
    if hass.services.has_service(DOMAIN, SERVICE_CREATE):
        return

    def _denied(call: ServiceCall, err: WakeyPermissionError) -> HomeAssistantError:
        """Turn a permission denial into the right kind of service error.

        An alarm the caller may not see is reported as simply missing — same
        message a genuinely deleted alarm gets — so a non-admin cannot probe
        for other people's alarm ids. Being refused a speaker is a real
        authorisation failure and says so.
        """
        if isinstance(err, AlarmNotVisible):
            return ServiceValidationError(str(err))
        return Unauthorized(context=call.context, permission=str(err))

    async def _create(call: ServiceCall) -> None:
        if (data := _get_data(hass)) is None:
            return
        user_id, is_admin = await _async_caller(hass, call)
        payload = async_sanitize_payload(dict(call.data), is_admin)
        try:
            async_assert_player_allowed(
                data.store, user_id, is_admin, payload.get("media_player") or ""
            )
        except WakeyPermissionError as err:
            raise _denied(call, err) from err

        if not is_admin:
            payload[ATTR_OWNER_ID] = user_id
        else:
            # A system call with no owner_id leaves the alarm unowned rather
            # than guessing. An admin acting in person owns what they create.
            payload.setdefault(ATTR_OWNER_ID, user_id)

        alarm = data.store.async_create(payload)
        _LOGGER.info("Created alarm %s (%s)", alarm.name, alarm.id)

    async def _update(call: ServiceCall) -> None:
        if (data := _get_data(hass)) is None:
            return
        user_id, is_admin = await _async_caller(hass, call)
        changes = dict(call.data)
        alarm_id = changes.pop(ATTR_ALARM_ID)
        try:
            alarm = async_assert_can_modify(data.store, alarm_id, user_id, is_admin)
            changes = async_sanitize_payload(changes, is_admin)
            new_player = changes.get("media_player")
            if new_player is not None and new_player != alarm.media_player:
                async_assert_player_allowed(data.store, user_id, is_admin, new_player)
        except WakeyPermissionError as err:
            raise _denied(call, err) from err
        data.store.async_update(alarm_id, changes)

    async def _delete(call: ServiceCall) -> None:
        if (data := _get_data(hass)) is None:
            return
        user_id, is_admin = await _async_caller(hass, call)
        alarm_id = call.data[ATTR_ALARM_ID]
        try:
            async_assert_can_modify(data.store, alarm_id, user_id, is_admin)
        except WakeyPermissionError as err:
            raise _denied(call, err) from err
        await data.player.async_dismiss(alarm_id, reason="deleted")
        if not data.store.async_delete(alarm_id):
            raise ServiceValidationError(f"No alarm with id {alarm_id}")

    async def _snooze(call: ServiceCall) -> None:
        if (data := _get_data(hass)) is None:
            return
        user_id, is_admin = await _async_caller(hass, call)
        minutes = call.data.get("minutes")
        if (alarm_id := call.data.get(ATTR_ALARM_ID)) is not None:
            try:
                async_assert_can_modify(data.store, alarm_id, user_id, is_admin)
            except WakeyPermissionError as err:
                raise _denied(call, err) from err
            await data.player.async_snooze(alarm_id, minutes)
            return
        # No target: snooze whatever of the caller's is currently going off.
        for ringing_id in async_visible_ringing(
            data.store, data.player, user_id, is_admin
        ):
            await data.player.async_snooze(ringing_id, minutes)

    async def _dismiss(call: ServiceCall) -> None:
        if (data := _get_data(hass)) is None:
            return
        user_id, is_admin = await _async_caller(hass, call)
        if (alarm_id := call.data.get(ATTR_ALARM_ID)) is not None:
            try:
                async_assert_can_modify(data.store, alarm_id, user_id, is_admin)
            except WakeyPermissionError as err:
                raise _denied(call, err) from err
            await data.player.async_dismiss(alarm_id)
            return
        for ringing_id in async_visible_ringing(
            data.store, data.player, user_id, is_admin
        ):
            await data.player.async_dismiss(ringing_id)

    async def _skip_next(call: ServiceCall) -> None:
        if (data := _get_data(hass)) is None:
            return
        user_id, is_admin = await _async_caller(hass, call)
        alarm_id = call.data[ATTR_ALARM_ID]
        try:
            async_assert_can_modify(data.store, alarm_id, user_id, is_admin)
        except WakeyPermissionError as err:
            raise _denied(call, err) from err
        data.store.async_update(alarm_id, {"skip_next": call.data["skip"]})

    async def _trigger_now(call: ServiceCall) -> None:
        if (data := _get_data(hass)) is None:
            return
        user_id, is_admin = await _async_caller(hass, call)
        alarm_id = call.data[ATTR_ALARM_ID]
        try:
            alarm = async_assert_can_modify(data.store, alarm_id, user_id, is_admin)
        except WakeyPermissionError as err:
            raise _denied(call, err) from err
        await data.player.async_fire(alarm)

    for service, handler, schema in (
        (SERVICE_CREATE, _create, CREATE_SCHEMA),
        (SERVICE_UPDATE, _update, UPDATE_SCHEMA),
        (SERVICE_DELETE, _delete, TARGET_SCHEMA),
        (SERVICE_SNOOZE, _snooze, SNOOZE_SCHEMA),
        (SERVICE_DISMISS, _dismiss, DISMISS_SCHEMA),
        (SERVICE_SKIP_NEXT, _skip_next, SKIP_SCHEMA),
        (SERVICE_TRIGGER_NOW, _trigger_now, TARGET_SCHEMA),
    ):
        hass.services.async_register(DOMAIN, service, handler, schema=schema)
