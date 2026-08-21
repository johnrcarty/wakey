"""WebSocket API backing the Wakey panel.

The panel reads alarms from here rather than from hass.states, so it sees the
store directly and updates live via a subscription instead of polling.

Every command is scoped to the calling user. The snapshot a connection
receives contains only the alarms that user may see, and the mutations check
ownership and the speaker allowlist before touching anything. See
permissions.py for the rules themselves.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    ATTR_ALARM_ID,
    ATTR_ALLOWED_MEDIA_PLAYERS,
    ATTR_OWNER_ID,
    ATTR_USER_ID,
    DOMAIN,
    ERR_INVALID_FORMAT,
    ERR_NOT_FOUND,
    ERR_NOT_LOADED,
    REPEAT_MODES,
    SIGNAL_ALARMS_CHANGED,
    SIGNAL_POLICY_CHANGED,
    SIGNAL_RUNTIME_CHANGED,
    SOURCE_KINDS,
)
from .permissions import (
    WakeyPermissionError,
    async_allowed_players,
    async_assert_can_modify,
    async_assert_player_allowed,
    async_orphaned_alarms,
    async_sanitize_payload,
    async_visible_alarms,
    async_visible_ringing,
)
from .scheduler import CLEAR_ADJUSTMENT
from .store import MEDIA_PLAYER_PREFIX

_LOGGER = logging.getLogger(__name__)

# Optional alarm fields shared by create and update.
_FIELDS = {
    vol.Optional("name"): str,
    vol.Optional("enabled"): bool,
    vol.Optional("time"): str,
    vol.Optional("repeat"): vol.In(REPEAT_MODES),
    vol.Optional("weekdays"): [vol.All(vol.Coerce(int), vol.Range(0, 6))],
    vol.Optional("date"): vol.Any(str, None),
    vol.Optional("media_player"): str,
    vol.Optional("source_uri"): str,
    vol.Optional("source_kind"): vol.In(SOURCE_KINDS),
    vol.Optional("volume"): vol.All(vol.Coerce(float), vol.Range(0.0, 1.0)),
    vol.Optional("fade_seconds"): vol.All(vol.Coerce(int), vol.Range(0, 3600)),
    vol.Optional("resume_previous"): cv.boolean,
    vol.Optional("snooze_minutes"): vol.All(vol.Coerce(int), vol.Range(1, 120)),
    vol.Optional("auto_dismiss_minutes"): vol.All(vol.Coerce(int), vol.Range(1, 240)),
    vol.Optional("pre_alarm_minutes"): vol.All(vol.Coerce(int), vol.Range(0, 240)),
    vol.Optional("pre_alarm_script"): vol.Any(str, None),
    vol.Optional("notify_targets"): vol.All(cv.ensure_list, [cv.entity_id]),
}


def _get_data(hass: HomeAssistant):
    return next(iter(hass.data.get(DOMAIN, {}).values()), None)


@callback
def _caller(connection) -> tuple[str | None, bool]:
    """(user_id, is_admin) for this connection.

    A connection with no user should not happen on an authenticated socket,
    but if it ever does it is treated as an anonymous non-admin, which can see
    nothing and change nothing.
    """
    user = connection.user
    if user is None:
        return None, False
    return user.id, user.is_admin


def _guard(func):
    """Turn a permission denial into a clean WebSocket error.

    Sits above websocket_command so the schema attributes still propagate,
    exactly as require_admin does.
    """

    @wraps(func)
    def with_guard(hass, connection, msg):
        try:
            func(hass, connection, msg)
        except WakeyPermissionError as err:
            connection.send_error(msg["id"], err.code, str(err))

    return with_guard


def _async_guard(func):
    """_guard for the coroutine handlers, applied below async_response."""

    @wraps(func)
    async def with_guard(hass, connection, msg):
        try:
            await func(hass, connection, msg)
        except WakeyPermissionError as err:
            connection.send_error(msg["id"], err.code, str(err))

    return with_guard


@callback
def _snapshot(hass: HomeAssistant, user_id: str | None, is_admin: bool) -> dict[str, Any]:
    """The view of Wakey belonging to one caller.

    owner_id is sent raw rather than resolved to a name: this is a sync
    callback and hass.auth.async_get_users is a coroutine. The admin view
    joins it against wakey/users/list client-side.
    """
    data = _get_data(hass)
    if data is None:
        return {
            "alarms": [],
            "ringing": [],
            "snoozed": [],
            "user_id": user_id,
            "is_admin": is_admin,
            ATTR_ALLOWED_MEDIA_PLAYERS: None if is_admin else [],
        }

    alarms = []
    for alarm in async_visible_alarms(data.store, user_id, is_admin):
        entry = alarm.to_dict()
        nxt = data.scheduler.async_next_fire(alarm)
        entry["next_fire"] = nxt.isoformat() if nxt else None
        entry["is_ringing"] = (
            alarm.id in data.player.ringing and not data.player.ringing[alarm.id].snoozed
        )
        entry["is_snoozed"] = (
            alarm.id in data.player.ringing and data.player.ringing[alarm.id].snoozed
        )
        alarms.append(entry)

    return {
        "alarms": alarms,
        "ringing": [a["id"] for a in alarms if a["is_ringing"]],
        "snoozed": [a["id"] for a in alarms if a["is_snoozed"]],
        "user_id": user_id,
        "is_admin": is_admin,
        ATTR_ALLOWED_MEDIA_PLAYERS: async_allowed_players(
            data.store, user_id, is_admin
        ),
    }


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register commands once per Home Assistant run.

    async_register_command is not safe to call twice for the same type, and a
    config-entry reload would otherwise do exactly that.
    """
    if hass.data.get(f"{DOMAIN}_ws_registered"):
        return
    hass.data[f"{DOMAIN}_ws_registered"] = True

    for handler in (
        ws_list,
        ws_subscribe,
        ws_create,
        ws_update,
        ws_delete,
        ws_snooze,
        ws_dismiss,
        ws_skip_next,
        ws_adjust_next,
        ws_trigger,
        ws_users_list,
        ws_policy_list,
        ws_policy_set,
        ws_policy_delete,
        ws_set_owner,
    ):
        websocket_api.async_register_command(hass, handler)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list"})
@callback
def ws_list(hass, connection, msg) -> None:
    user_id, is_admin = _caller(connection)
    connection.send_result(msg["id"], _snapshot(hass, user_id, is_admin))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@callback
def ws_subscribe(hass, connection, msg) -> None:
    user_id, is_admin = _caller(connection)

    @callback
    def _forward(*_args) -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], _snapshot(hass, user_id, is_admin))
        )

    unsubs = [
        async_dispatcher_connect(hass, SIGNAL_ALARMS_CHANGED, _forward),
        async_dispatcher_connect(hass, SIGNAL_RUNTIME_CHANGED, _forward),
        # An admin changing an allowlist has to reach the affected panel
        # immediately, or the speaker picker keeps offering stale options.
        async_dispatcher_connect(hass, SIGNAL_POLICY_CHANGED, _forward),
    ]

    @callback
    def _unsubscribe() -> None:
        for unsub in unsubs:
            unsub()

    connection.subscriptions[msg["id"]] = _unsubscribe
    connection.send_result(msg["id"])
    # Send the current state immediately so the panel needs one round trip,
    # not two, and cannot miss an update in between.
    _forward()


@_guard
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/create", vol.Optional(ATTR_OWNER_ID): vol.Any(str, None), **_FIELDS}
)
@callback
def ws_create(hass, connection, msg) -> None:
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    user_id, is_admin = _caller(connection)

    payload = {k: v for k, v in msg.items() if k not in ("id", "type")}
    payload = async_sanitize_payload(payload, is_admin)
    async_assert_player_allowed(
        data.store, user_id, is_admin, payload.get("media_player") or ""
    )
    # An admin adding an alarm is adding it for themselves unless they said
    # otherwise; everyone else owns what they create, full stop.
    payload[ATTR_OWNER_ID] = payload.get(ATTR_OWNER_ID, user_id) if is_admin else user_id

    alarm = data.store.async_create(payload)
    connection.send_result(msg["id"], {"alarm_id": alarm.id})


@_guard
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/update",
        vol.Required(ATTR_ALARM_ID): str,
        vol.Optional(ATTR_OWNER_ID): vol.Any(str, None),
        **_FIELDS,
    }
)
@callback
def ws_update(hass, connection, msg) -> None:
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    user_id, is_admin = _caller(connection)
    alarm = async_assert_can_modify(data.store, msg[ATTR_ALARM_ID], user_id, is_admin)

    payload = {k: v for k, v in msg.items() if k not in ("id", "type", ATTR_ALARM_ID)}
    payload = async_sanitize_payload(payload, is_admin)

    # Only check the speaker when it is actually changing. The panel sends the
    # whole alarm on every save, so validating unconditionally would mean that
    # revoking a speaker locked its owner out of even renaming the alarm.
    new_player = payload.get("media_player")
    if new_player is not None and new_player != alarm.media_player:
        async_assert_player_allowed(data.store, user_id, is_admin, new_player)

    data.store.async_update(msg[ATTR_ALARM_ID], payload)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/delete", vol.Required(ATTR_ALARM_ID): str}
)
@websocket_api.async_response
@_async_guard
async def ws_delete(hass, connection, msg) -> None:
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    user_id, is_admin = _caller(connection)
    async_assert_can_modify(data.store, msg[ATTR_ALARM_ID], user_id, is_admin)

    await data.player.async_dismiss(msg[ATTR_ALARM_ID], reason="deleted")
    if not data.store.async_delete(msg[ATTR_ALARM_ID]):
        connection.send_error(msg["id"], ERR_NOT_FOUND, "No such alarm")
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/snooze",
        vol.Optional(ATTR_ALARM_ID): str,
        vol.Optional("minutes"): vol.All(vol.Coerce(int), vol.Range(1, 120)),
    }
)
@websocket_api.async_response
@_async_guard
async def ws_snooze(hass, connection, msg) -> None:
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    user_id, is_admin = _caller(connection)
    minutes = msg.get("minutes")

    if (alarm_id := msg.get(ATTR_ALARM_ID)) is not None:
        async_assert_can_modify(data.store, alarm_id, user_id, is_admin)
        await data.player.async_snooze(alarm_id, minutes)
    else:
        # The bare form means "silence whatever of mine is going off".
        for ringing_id in async_visible_ringing(
            data.store, data.player, user_id, is_admin
        ):
            await data.player.async_snooze(ringing_id, minutes)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/dismiss", vol.Optional(ATTR_ALARM_ID): str}
)
@websocket_api.async_response
@_async_guard
async def ws_dismiss(hass, connection, msg) -> None:
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    user_id, is_admin = _caller(connection)

    if (alarm_id := msg.get(ATTR_ALARM_ID)) is not None:
        async_assert_can_modify(data.store, alarm_id, user_id, is_admin)
        await data.player.async_dismiss(alarm_id)
    else:
        for ringing_id in async_visible_ringing(
            data.store, data.player, user_id, is_admin
        ):
            await data.player.async_dismiss(ringing_id)
    connection.send_result(msg["id"])


@_guard
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/skip_next",
        vol.Required(ATTR_ALARM_ID): str,
        vol.Optional("skip", default=True): bool,
    }
)
@callback
def ws_skip_next(hass, connection, msg) -> None:
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    user_id, is_admin = _caller(connection)
    async_assert_can_modify(data.store, msg[ATTR_ALARM_ID], user_id, is_admin)

    data.store.async_update(msg[ATTR_ALARM_ID], {"skip_next": msg["skip"]})
    connection.send_result(msg["id"])


@_guard
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/adjust_next",
        vol.Required(ATTR_ALARM_ID): str,
        vol.Optional("time"): str,
        vol.Optional("clear", default=False): bool,
    }
)
@callback
def ws_adjust_next(hass, connection, msg) -> None:
    """Move just the next occurrence of an alarm, or put it back.

    The occurrence is never named by the caller: the scheduler resolves it, so
    a panel that has been open since yesterday cannot move the wrong day.
    """
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    user_id, is_admin = _caller(connection)
    alarm = async_assert_can_modify(data.store, msg[ATTR_ALARM_ID], user_id, is_admin)

    if msg["clear"]:
        data.store.async_update(alarm.id, dict(CLEAR_ADJUSTMENT))
        connection.send_result(msg["id"])
        return

    if (time_str := msg.get("time")) is None:
        connection.send_error(
            msg["id"], ERR_INVALID_FORMAT, "No time to move the alarm to"
        )
        return

    try:
        patch = data.scheduler.async_plan_adjustment(alarm, time_str)
    except ValueError as err:
        connection.send_error(msg["id"], ERR_INVALID_FORMAT, str(err))
        return

    data.store.async_update(alarm.id, patch)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/trigger", vol.Required(ATTR_ALARM_ID): str}
)
@websocket_api.async_response
@_async_guard
async def ws_trigger(hass, connection, msg) -> None:
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    user_id, is_admin = _caller(connection)
    alarm = async_assert_can_modify(data.store, msg[ATTR_ALARM_ID], user_id, is_admin)

    await data.player.async_fire(alarm)
    connection.send_result(msg["id"])


# --- Administration --------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/users/list"})
@websocket_api.async_response
async def ws_users_list(hass, connection, msg) -> None:
    """The people who could own an alarm.

    System-generated accounts (Supervisor, the Home Assistant Content user and
    friends) are filtered out — they would only clutter the permission matrix.
    """
    users = [
        {
            "id": user.id,
            "name": user.name or "",
            "is_admin": user.is_admin,
            "is_owner": user.is_owner,
        }
        for user in await hass.auth.async_get_users()
        if not user.system_generated and user.is_active
    ]
    users.sort(key=lambda u: (not u["is_owner"], u["name"].lower()))
    connection.send_result(msg["id"], {"users": users})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/policy/list"})
@callback
def ws_policy_list(hass, connection, msg) -> None:
    """Every stored allowlist. Users with no record are simply absent."""
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    connection.send_result(
        msg["id"],
        {"policies": {p.user_id: p.to_dict() for p in data.store.async_all_policies()}},
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/policy/set",
        vol.Required(ATTR_USER_ID): str,
        vol.Required(ATTR_ALLOWED_MEDIA_PLAYERS): [cv.entity_id],
    }
)
@websocket_api.async_response
async def ws_policy_set(hass, connection, msg) -> None:
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return

    user_id = msg[ATTR_USER_ID]
    if await hass.auth.async_get_user(user_id) is None:
        connection.send_error(msg["id"], ERR_NOT_FOUND, "No such user")
        return

    players = msg[ATTR_ALLOWED_MEDIA_PLAYERS]
    # The store filters these too, but silently. Report it here so an
    # administrator who fat-fingers a domain finds out.
    if any(not p.startswith(MEDIA_PLAYER_PREFIX) for p in players):
        connection.send_error(
            msg["id"], ERR_INVALID_FORMAT, "Only media_player entities can be allowed"
        )
        return

    policy = data.store.async_set_policy(user_id, players)
    # Alarms this user already owns that the new allowlist no longer covers.
    # Reported, never auto-disabled — silently switching off someone's alarm
    # clock is a worse outcome than an inconsistent policy.
    orphaned = [
        {"id": a.id, "name": a.name, "media_player": a.media_player}
        for a in async_orphaned_alarms(data.store, user_id, policy.allowed_media_players)
    ]
    connection.send_result(
        msg["id"], {"policy": policy.to_dict(), "orphaned_alarms": orphaned}
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/policy/delete", vol.Required(ATTR_USER_ID): str}
)
@callback
def ws_policy_delete(hass, connection, msg) -> None:
    """Drop a record, reverting that user to deny-by-default."""
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return
    data.store.async_delete_policy(msg[ATTR_USER_ID])
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_owner",
        vol.Required(ATTR_ALARM_ID): str,
        vol.Required(ATTR_OWNER_ID): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_set_owner(hass, connection, msg) -> None:
    """Hand an alarm to someone. null unassigns it.

    Kept as its own admin-only command rather than a field on wakey/update:
    an admin-only field inside a schema shared with a non-admin path is the
    shape of mistake that turns into a privilege escalation later.
    """
    data = _get_data(hass)
    if data is None:
        connection.send_error(msg["id"], ERR_NOT_LOADED, "Wakey is not set up")
        return

    owner_id = msg[ATTR_OWNER_ID]
    if owner_id is not None and await hass.auth.async_get_user(owner_id) is None:
        connection.send_error(msg["id"], ERR_NOT_FOUND, "No such user")
        return

    if data.store.async_update(msg[ATTR_ALARM_ID], {ATTR_OWNER_ID: owner_id}) is None:
        connection.send_error(msg["id"], ERR_NOT_FOUND, "No such alarm")
        return
    connection.send_result(msg["id"])
