"""Constants for the Wakey integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "wakey"
NAME = "Wakey"
VERSION = "0.5.0"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

# --- Panel -----------------------------------------------------------------
# Paths mirror Alarmo's layout, which is a known-good arrangement on HA 2026.7:
# the JS is served from inside the integration folder via a registered static
# path, and panel_custom points the sidebar at it.
CUSTOM_COMPONENTS = "custom_components"
INTEGRATION_FOLDER = DOMAIN
PANEL_FOLDER = "frontend"
PANEL_FILENAME = "dist/wakey-panel.js"
PANEL_URL = f"/api/panel_custom/{DOMAIN}"
PANEL_NAME = "wakey-panel"
PANEL_TITLE = NAME
PANEL_ICON = "mdi:alarm"

# --- Dispatcher signals ----------------------------------------------------
# Registration signals carry a single AlarmEntry and are consumed by the entity
# platforms to add entities for alarms created at runtime.
SIGNAL_ALARM_REGISTERED = f"{DOMAIN}_alarm_registered"
SIGNAL_ALARM_REMOVED = f"{DOMAIN}_alarm_removed"
# Fired whenever anything about an alarm changes; entities and the panel
# subscription both listen so they re-read from the store.
SIGNAL_ALARMS_CHANGED = f"{DOMAIN}_alarms_changed"
# Fired when the ringing/snoozed runtime state changes.
SIGNAL_RUNTIME_CHANGED = f"{DOMAIN}_runtime_changed"
# Fired when a user's speaker permissions change. Deliberately separate from
# SIGNAL_ALARMS_CHANGED: no alarm changed, so no entity needs to write state —
# only subscribed panels need to re-render with the new allowlist.
SIGNAL_POLICY_CHANGED = f"{DOMAIN}_policy_changed"

# --- Events ----------------------------------------------------------------
EVENT_PRE_ALARM = f"{DOMAIN}_pre_alarm"
EVENT_ALARM_FIRED = f"{DOMAIN}_alarm_fired"
EVENT_ALARM_FAILED = f"{DOMAIN}_alarm_failed"
EVENT_ALARM_DISMISSED = f"{DOMAIN}_alarm_dismissed"
EVENT_ALARM_SNOOZED = f"{DOMAIN}_alarm_snoozed"

# Fired by the Home Assistant companion app when a notification action button
# is tapped. Not ours to define — this is the app's own event name.
EVENT_MOBILE_APP_NOTIFICATION_ACTION = "mobile_app_notification_action"

# --- Alarm fields ----------------------------------------------------------
ATTR_ALARM_ID = "alarm_id"
ATTR_NAME = "name"
ATTR_ENABLED = "enabled"
ATTR_TIME = "time"
ATTR_REPEAT = "repeat"
ATTR_WEEKDAYS = "weekdays"
ATTR_DATE = "date"
ATTR_SKIP_NEXT = "skip_next"
# One-time adjustment. ATTR_OVERRIDE_FOR is the local date of the occurrence
# that was moved, ATTR_OVERRIDE_TIME the wall clock it rings at instead.
ATTR_OVERRIDE_FOR = "override_for"
ATTR_OVERRIDE_TIME = "override_time"
ATTR_MEDIA_PLAYER = "media_player"
ATTR_SOURCE_URI = "source_uri"
ATTR_SOURCE_KIND = "source_kind"
ATTR_VOLUME = "volume"
ATTR_FADE_SECONDS = "fade_seconds"
ATTR_SNOOZE_MINUTES = "snooze_minutes"
ATTR_AUTO_DISMISS_MINUTES = "auto_dismiss_minutes"
ATTR_PRE_ALARM_MINUTES = "pre_alarm_minutes"
ATTR_PRE_ALARM_SCRIPT = "pre_alarm_script"
ATTR_LAST_FIRED = "last_fired"
# The Home Assistant user id that owns an alarm. None means unowned: alarms
# that predate multi-user support, or ones created by an automation with no
# user context. Unowned alarms are visible to administrators only.
ATTR_OWNER_ID = "owner_id"

# --- Permissions -----------------------------------------------------------
ATTR_USER_ID = "user_id"
ATTR_ALLOWED_MEDIA_PLAYERS = "allowed_media_players"

# WebSocket error codes. Cross-owner access reports not_found rather than
# unauthorized so a non-admin cannot probe for other people's alarm ids.
ERR_NOT_FOUND = "not_found"
ERR_NOT_LOADED = "not_loaded"
ERR_PLAYER_NOT_ALLOWED = "player_not_allowed"
ERR_INVALID_FORMAT = "invalid_format"

# --- Enumerations ----------------------------------------------------------
REPEAT_ONCE = "once"
REPEAT_WEEKLY = "weekly"
REPEAT_MODES = [REPEAT_ONCE, REPEAT_WEEKLY]

SOURCE_MUSIC_ASSISTANT = "music_assistant"
SOURCE_MEDIA_PLAYER = "media_player"
SOURCE_KINDS = [SOURCE_MUSIC_ASSISTANT, SOURCE_MEDIA_PLAYER]

# --- Defaults --------------------------------------------------------------
DEFAULT_VOLUME = 0.7
DEFAULT_FADE_SECONDS = 0
DEFAULT_SNOOZE_MINUTES = 9
DEFAULT_AUTO_DISMISS_MINUTES = 30
# 0 disables the pre-alarm hook entirely.
DEFAULT_PRE_ALARM_MINUTES = 0

# How long after a missed firing time Wakey will still fire on startup. Beyond
# this the occurrence is logged and skipped — waking someone an hour late is
# worse than not waking them.
MISSED_ALARM_GRACE = 15 * 60  # seconds

# How long to wait for the media player to actually reach "playing" before
# treating the alarm as failed and running the fallback.
PLAYBACK_VERIFY_SECONDS = 10

# Cap on any single blocking service call during the firing sequence. Without
# it, one wedged integration could hang the alarm indefinitely.
SERVICE_CALL_TIMEOUT = 15

# Volume the fade ramp starts from.
FADE_FLOOR = 0.05
# Seconds between fade steps.
FADE_STEP_SECONDS = 2
