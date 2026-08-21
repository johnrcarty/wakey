# Wakey

An alarm clock for Home Assistant.

Home Assistant can do almost anything on a schedule, but it has never had an
alarm clock — the thing you actually rely on to wake you up, with a snooze
button, weekday repeat, and the confidence that it will go off. Wakey adds one,
with its own page in the sidebar.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=johnrcarty&repository=wakey&category=integration)

## How this was built

Wakey was written with [Claude Code](https://claude.com/claude-code). Scope,
architecture and design decisions were directed by the repository owner; Claude
wrote essentially all of the code, tests and documentation.

That is stated plainly because you should know what you are installing. What it
means in practice:

- There is a real test suite covering the parts that are easy to get wrong —
  both DST transitions, alarms missed while Home Assistant was down, storage
  round-trips, and WebSocket permissions.
- It runs in production on the author's own Home Assistant, on the speaker in
  their own bedroom.
- It has **not** had wide real-world use yet. If you are relying on it to get up
  for something that matters, fire it once with the Test button first, and keep
  a second alarm until you trust it.

Bug reports are very welcome.

## What makes it different

- **Volume fade-in.** Ramp from a whisper up to your target volume over a
  configurable window, instead of being detonated awake at full blast. The ramp
  backs off if you reach for the volume yourself.
- **A failsafe.** After firing, Wakey checks the speaker actually reached
  `playing`. If it didn't, it retries, then raises a notification and fires a
  `wakey_alarm_failed` event you can hang your own escalation off. An alarm that
  fails silently is worse than no alarm.
- **Skip next.** Off tomorrow? Skip one occurrence without disarming the alarm
  and forgetting to turn it back on. The flag clears itself afterwards.
- **Adjust next.** Need to be up an hour earlier tomorrow, or get a lie-in?
  Move just the next occurrence. It rings once at the new time and goes back to
  its usual schedule on its own — no second alarm to toggle between, nothing to
  remember to change back.
- **A pre-alarm hook.** Run a script a set number of minutes before — sunrise
  lights, heating, a kettle.
- **Survives a restart.** If Home Assistant was down when an alarm was due, it
  fires on startup — but only inside a grace window, because being woken an hour
  late is worse than not being woken.
- **Correct across DST.** The nonexistent hour on spring-forward fires at the
  transition rather than an hour late; the repeated hour on fall-back rings once.
  This is unit tested, not hoped for.
- **Native entities.** Every alarm is a device with its own switch, editable
  time, and next-fire sensor, so alarms work with normal automations,
  dashboards and voice — not just inside Wakey.
- **One list each.** Alarms belong to the person who made them. Everyone gets
  their own list, and an admin decides which speakers each person may use — so
  nobody can set a 3am alarm on someone else's bedroom speaker.

## Requirements

- Home Assistant 2026.3 or newer
- Optional: [Music Assistant](https://music-assistant.io/) for library playback

## Installation

Not yet in the default HACS index. Add it as a custom repository:

1. HACS → ⋮ → Custom repositories
2. Repository `johnrcarty/wakey`, category **Integration**
3. Install, restart Home Assistant
4. Settings → Devices & Services → Add Integration → **Wakey**

**Wakey** then appears in your sidebar.

## Using it

Add an alarm from the panel: set a time, pick the days, choose a speaker, and
browse for a track. The media browser opens straight into your Music Assistant
library.

`source_uri` accepts a Music Assistant URI (`library://track/6018`), a media
content ID, or plain search text that Music Assistant resolves.

Everything is also available as actions, which is handy for automations:

```yaml
action: wakey.create
data:
  name: Weekday
  time: "06:30"
  repeat: weekly
  weekdays: [0, 1, 2, 3, 4]     # Mon=0 … Sun=6
  media_player: media_player.bedroom
  source_kind: music_assistant
  source_uri: library://track/6018
  volume: 0.7
  fade_seconds: 60
  pre_alarm_minutes: 15
  pre_alarm_script: script.sunrise_lights
  resume_previous: true
```

### Moving one occurrence

**Adjust next** on an alarm card moves the next occurrence only, to another
time on the same day. The card shows what it will do (`Tomorrow at 05:30`), and
**Back to 07:00** in the same dialog undoes it. Once that day is over the alarm
is back to normal by itself.

```yaml
action: wakey.adjust_next
data:
  alarm_id: 8f1c2b3a4d5e6f7a8b9c0d1e2f3a4b5c
  time: "05:30"
```

You never say *which* occurrence: it is always the next one this alarm would
ring, worked out when the action runs, so adjusting twice moves the same
morning again rather than booking the one after it. Pass `clear: true` instead
of a time to restore the usual time. A time that has already gone by is
refused rather than quietly landing on the wrong day, and setting an
adjustment cancels a pending **Skip next** (and vice versa) — an occurrence is
either moved or skipped, never both.

For a different *day*, make a second alarm — this deliberately does not move an
alarm off its own date.

### Resuming what the alarm interrupted

If you fall asleep to ambient noise or a playlist on the same speaker the alarm
targets, **Resume previous playback** (Advanced section of the alarm form, or
`resume_previous: true`) puts it back when the alarm is dismissed or snoozed —
same track, same position, same volume. Snoozing resumes it for the length of
the snooze.

By default this is off, and an alarm replaces whatever was playing.

It works for **Music Assistant sources only**, and only when the speaker was
already playing a Music Assistant queue. That is not an arbitrary restriction:
`music_assistant.get_queue` is the only thing that reports both what is playing
and how far into it you are, and a plain `media_player` has no queue to insert
the alarm into without destroying it. Anything Wakey cannot resume from falls
back to the normal behaviour — an alarm that reliably rings matters more than
one that tidies up after itself.

One trade-off worth knowing: resuming re-inserts the interrupted track rather
than rewinding to it, so each ring leaves two spent items behind the play head
in the Music Assistant queue. They never play again, and anything that starts a
queue afresh clears them.

## Users and permissions

Every alarm belongs to the Home Assistant user who created it. You see your own
alarms and nobody else's; administrators see everyone's.

Speakers are **deny-by-default**. A new household member can open Wakey but has
nowhere to point an alarm until an administrator grants them one. Go to
**Wakey → People** and pick the speakers each person may use. Administrators are
never restricted.

The same screen shows who owns what, and lets you hand an alarm to someone else.

**After upgrading from 0.1.x**, alarms that already existed have no owner, so
only administrators can see them. The People screen offers a one-click *Assign
all to me* to fix that. They keep firing either way.

### What this does and does not protect against

It stops someone setting, editing, firing or silencing an alarm that isn't
theirs, from the panel, from the actions, or from the alarm's own entities.

It does **not** hide alarms completely. Home Assistant gives every non-read-only
user read access to every entity state, so another household member can still
*see* that `switch.dads_alarm` exists and what time it is set to — they just
can't touch it. Nor does the speaker allowlist restrict the speaker itself: it
governs Wakey alarms, not `media_player.play_media`. Someone determined can
still play music on any speaker directly, exactly as they always could.

## Actions

| Action | Purpose |
|---|---|
| `wakey.create` | Add an alarm |
| `wakey.update` | Patch fields on an alarm (`alarm_id` plus what changed) |
| `wakey.delete` | Remove an alarm and its entities |
| `wakey.snooze` | Silence a ringing alarm; omit `alarm_id` for whatever is ringing |
| `wakey.dismiss` | Stop until the next occurrence |
| `wakey.skip_next` | Skip one occurrence, then resume |
| `wakey.adjust_next` | Move the next occurrence to another time that day (`clear: true` to undo) |
| `wakey.trigger_now` | Fire immediately — use this to test a speaker and source |

## Entities

**Per alarm** (each alarm is its own device):

| Entity | Purpose |
|---|---|
| `switch.<name>` | Armed or not |
| `time.<name>_time` | The alarm time, editable anywhere in HA |
| `sensor.<name>_next` | Next fire, `device_class: timestamp` |
| `button.<name>_test` | Fire it now |
| `switch.<name>_skip_next` | Skip one occurrence (disabled by default) |

**Global:**

| Entity | Purpose |
|---|---|
| `sensor.wakey_next_alarm` | Soonest alarm across all of them |
| `binary_sensor.wakey_ringing` | On while something is actually sounding |

## Events

Hang your own automations off these — each carries `alarm_id` and `name`:

| Event | When |
|---|---|
| `wakey_pre_alarm` | The pre-alarm lead time is reached |
| `wakey_alarm_fired` | An alarm starts (`missed: true` if it was a catch-up) |
| `wakey_alarm_snoozed` | Snoozed, with `minutes` |
| `wakey_alarm_dismissed` | Dismissed, with `reason` |
| `wakey_alarm_failed` | Playback never started, with `reason` |

```yaml
triggers:
  - trigger: event
    event_type: wakey_alarm_failed
actions:
  - action: notify.mobile_app_phone
    data:
      message: "Alarm {{ trigger.event.data.name }} failed to play!"
```

## Development

```bash
uv venv --python 3.14 .venv          # HA 2026.7+ requires Python 3.14+
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest -q

cd frontend && npm ci && npm run build   # writes the committed panel bundle
```

Deploy to a live instance over SSH:

```bash
./scripts/deploy.sh my-ha-host
ssh my-ha-host 'ha core restart'     # Python changes need a restart
./scripts/logs.sh my-ha-host
```

`homeassistant.reload_config_entry` re-runs setup with the *old* code — there is
no supported hot reload for custom-component Python. Restart.

The panel bundle in `custom_components/wakey/frontend/dist/` is committed
deliberately: HACS ships repo contents verbatim and never runs a build step.

## Licence

MIT
