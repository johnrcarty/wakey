# Changelog

## 0.5.0

### Added

- **Adjust next.** Move a single occurrence of an alarm to another time on the
  same day. It rings once at the new time and returns to its usual schedule on
  its own, so there is no second alarm to toggle between and nothing to
  remember to change back. Available from the alarm card in the panel, and as
  `wakey.adjust_next` (`clear: true` undoes it).
  - Which occurrence gets moved is resolved when the call is made, never passed
    in, so a panel left open overnight cannot move the wrong day.
  - A time that has already passed is refused; an adjustment and a pending
    **Skip next** cancel each other out.
  - The alarm's usual time on that date stays suppressed for the rest of the
    day, so a moved alarm cannot also go off at the time it moved from.
  - Missed-alarm catch-up after a restart looks for the moved time, not the
    original one.

### Fixed

- The device shown for each alarm reported `sw_version` 0.2.0 regardless of the
  version actually installed.

## 0.4.0

### Added

- **Resume previous playback** (opt-in, per alarm). If the speaker was already
  playing a Music Assistant queue — ambient noise, a sleep playlist — the alarm
  now inserts itself into that queue rather than replacing it, and dismissing or
  snoozing puts the original track back at its previous position and volume.
  Off by default; Music Assistant sources only. Anything that cannot be resumed
  from falls back to the previous replace-and-pause behaviour.

## 0.3.0

Clearing a ringing alarm no longer requires opening the panel.

### Added

- **Notify on ring.** Each alarm can name `notify.*` targets (Advanced
  section of the alarm form). When it rings, they get a push with **Dismiss**
  and **Snooze** action buttons; tapping the notification body opens the
  Wakey panel. Action ids carry a per-ring token, so a notification left
  over from an earlier ring can never act on the current one — the token is
  also what authorises the action, since only a recipient of that exact
  push can produce it.
- **Voice snooze and cancel.** Saying "snooze", "cancel", "stop the alarm",
  or "dismiss the alarm" to any Assist satellite snoozes or dismisses
  everything currently ringing. Deliberately global — not scoped to an
  alarm, satellite, or user — the same way a smart speaker's own "stop"
  works. Wakey seeds `custom_sentences/en/wakey.yaml` in your config
  directory at startup; add your own phrasings in a separate file alongside
  it, which the conversation agent merges automatically.

## 0.2.0

Wakey now knows who is using it.

### Added

- **Per-user alarms.** Every alarm belongs to the Home Assistant user who
  created it. You see your own; administrators see everyone's.
- **Speaker permissions**, deny-by-default. An administrator grants each person
  the speakers they may point an alarm at, in the new **People** screen in the
  panel. Nobody can set an alarm on a speaker they were not given.
- The same screen assigns ownership of existing alarms, with a one-click
  *Assign all to me* for the ones left unowned by the upgrade.
- `owner_id` on `wakey.create` and `wakey.update`, so an automation — which has
  no user of its own — can say who an alarm is for.

### Changed

- **Non-administrators can now create, edit and delete their own alarms.**
  Previously all mutations were admin-only.
- `wakey.trigger_now`, `skip_next`, `snooze` and `dismiss` are now permission
  checked. They were not before: Home Assistant applies no permission check to
  plain domain services, so any authenticated user could fire any alarm.
- The untargeted "snooze/dismiss whatever is ringing" now means *whatever of
  mine is ringing* for non-administrators. Administrators still reach all of it.
- `switch.<alarm>`, `time.<alarm>_time` and `button.<alarm>_test` refuse a user
  who does not own the alarm. Automations, scripts and the scheduler — which
  carry no user — are unaffected.
- Storage schema 1.0 → 1.1.

### Upgrading

Alarms that already exist become **unowned**: they keep firing exactly as
before, but only administrators can see or edit them until someone is assigned
in the panel's People screen.

Downgrading to 0.1.x is safe for your alarms but discards ownership and
permission data — the older code drops both on its next save.

## 0.1.0

First release.

### Added

- Alarms with weekday repeat or a one-off date, stored in Home Assistant's
  own storage and editable from a sidebar panel.
- **Volume fade-in** from a configurable floor up to the target volume.
- **Playback failsafe** — after firing, Wakey verifies the speaker actually
  reached `playing`, retries once, then raises a persistent notification and
  fires `wakey_alarm_failed`.
- **Skip next**, which skips a single occurrence and clears itself afterwards.
- **Pre-alarm hook** — run a script a set number of minutes ahead.
- **Missed-alarm recovery.** An alarm that came due while Home Assistant was
  down fires on startup, but only within a grace window.
- **Snooze and dismiss**, with auto-dismiss after a configurable timeout.
- Music Assistant and generic `media_player` sources.
- Entities per alarm: `switch`, editable `time`, next-fire `sensor`, test
  `button`, and a skip-next `switch` (disabled by default). Globally:
  `sensor.wakey_next_alarm` and `binary_sensor.wakey_ringing`.
- Actions for create, update, delete, snooze, dismiss, skip_next and
  trigger_now.
- Diagnostics download including computed next-fire times and pending timers.

### Notes

- DST is handled explicitly: a time inside the spring-forward gap fires at the
  transition instant rather than an hour late, and the repeated hour on
  fall-back rings exactly once. Both are unit tested.
- The panel is not admin-only. Creating and editing alarms is, but viewing the
  schedule and snoozing are not. (Superseded in 0.2.0 — see above.)
