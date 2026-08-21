"""Moving one occurrence of an alarm, then having it put itself back.

The point of the feature is that nobody has to remember to change the alarm
back, so most of what is worth testing is the putting-back.
"""

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wakey.const import DOMAIN

# Thursday 2026-08-20, 18:00 in New York. The next weekday occurrence of the
# 07:00 alarm below is therefore Friday the 21st.
NOW = "2026-08-20 22:00:00+00:00"
TOMORROW = "2026-08-21"

ALARM = {
    "name": "Weekday",
    "time": "07:00",
    "media_player": "media_player.bedroom",
    "source_uri": "library://track/6018",
    "weekdays": [0, 1, 2, 3, 4],
}


@pytest.fixture
async def entry(hass: HomeAssistant, freezer) -> MockConfigEntry:
    await hass.config.async_set_time_zone("America/New_York")
    freezer.move_to(NOW)
    config_entry = MockConfigEntry(domain=DOMAIN, data={}, title="Wakey")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _create(hass, **overrides) -> str:
    await hass.services.async_call(DOMAIN, "create", {**ALARM, **overrides}, blocking=True)
    await hass.async_block_till_done()
    return next(iter(hass.data[DOMAIN].values())).store.async_all()[0].id


def _alarm(hass, alarm_id):
    return next(iter(hass.data[DOMAIN].values())).store.async_get(alarm_id)


async def _adjust(hass, alarm_id, **data):
    await hass.services.async_call(
        DOMAIN, "adjust_next", {"alarm_id": alarm_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def test_service_moves_the_next_occurrence(hass, entry) -> None:
    alarm_id = await _create(hass)
    await _adjust(hass, alarm_id, time="05:30")

    alarm = _alarm(hass, alarm_id)
    assert alarm.override_for == TOMORROW
    assert alarm.override_time == "05:30"
    assert alarm.time == "07:00"  # the alarm itself is untouched

    scheduler = next(iter(hass.data[DOMAIN].values())).scheduler
    nxt = scheduler.async_next_fire(alarm).astimezone(dt_util.DEFAULT_TIME_ZONE)
    assert (nxt.date().isoformat(), nxt.hour, nxt.minute) == (TOMORROW, 5, 30)


async def test_adjusting_twice_moves_the_same_occurrence(hass, entry) -> None:
    """Not the one after it — otherwise a change of mind books two alarms."""
    alarm_id = await _create(hass)
    await _adjust(hass, alarm_id, time="05:30")
    await _adjust(hass, alarm_id, time="06:15")

    alarm = _alarm(hass, alarm_id)
    assert (alarm.override_for, alarm.override_time) == (TOMORROW, "06:15")


async def test_clear_puts_the_usual_time_back(hass, entry) -> None:
    alarm_id = await _create(hass)
    await _adjust(hass, alarm_id, time="05:30")
    await _adjust(hass, alarm_id, clear=True)

    alarm = _alarm(hass, alarm_id)
    assert alarm.override_for is None
    assert alarm.override_time is None


async def test_a_time_that_has_already_gone_by_is_refused(hass, entry) -> None:
    """The occurrence is tonight; 05:30 this morning is not a thing to move it to."""
    alarm_id = await _create(hass, time="23:00")
    with pytest.raises(ServiceValidationError):
        await _adjust(hass, alarm_id, time="05:30")
    assert _alarm(hass, alarm_id).override_time is None


async def test_a_time_that_is_not_a_time_is_refused(hass, entry) -> None:
    alarm_id = await _create(hass)
    with pytest.raises(ServiceValidationError):
        await _adjust(hass, alarm_id, time="half past five")


async def test_adjusting_a_switched_off_alarm_is_refused(hass, entry) -> None:
    alarm_id = await _create(hass, enabled=False)
    with pytest.raises(ServiceValidationError):
        await _adjust(hass, alarm_id, time="05:30")


async def test_adjusting_clears_a_pending_skip(hass, entry) -> None:
    """Two one-shot flags racing to be consumed is the bug this prevents."""
    alarm_id = await _create(hass)
    await hass.services.async_call(
        DOMAIN, "skip_next", {"alarm_id": alarm_id, "skip": True}, blocking=True
    )
    await _adjust(hass, alarm_id, time="05:30")
    assert _alarm(hass, alarm_id).skip_next is False


async def test_skipping_clears_a_pending_adjustment(hass, entry) -> None:
    alarm_id = await _create(hass)
    await _adjust(hass, alarm_id, time="05:30")
    await hass.services.async_call(
        DOMAIN, "skip_next", {"alarm_id": alarm_id, "skip": True}, blocking=True
    )
    await hass.async_block_till_done()

    alarm = _alarm(hass, alarm_id)
    assert alarm.skip_next is True
    assert alarm.override_for is None


async def test_it_does_not_also_ring_at_the_usual_time(hass, entry, freezer) -> None:
    """The bug this feature is one line away from: two alarms in one morning.

    Moved to 05:30, it must not then go off again at 07:00 — which is what
    happens if the adjustment is torn up the moment it rings, because the
    occurrence it replaced is still ahead on the same day.
    """
    alarm_id = await _create(hass)
    await _adjust(hass, alarm_id, time="05:30")

    data = next(iter(hass.data[DOMAIN].values()))
    # The scheduler holds the fire callback bound from construction, so this
    # is the seam — patching the player itself would not be seen.
    data.scheduler._fire = AsyncMock()

    freezer.move_to("2026-08-21 09:30:00+00:00")  # 05:30 EDT
    await data.scheduler._async_handle_timer(alarm_id)
    await hass.async_block_till_done()

    assert data.scheduler._fire.await_count == 1
    nxt = data.scheduler.async_next_fire(_alarm(hass, alarm_id))
    nxt = nxt.astimezone(dt_util.DEFAULT_TIME_ZONE)
    assert (nxt.date().isoformat(), nxt.hour, nxt.minute) == ("2026-08-24", 7, 0)


async def test_the_alarm_reverts_by_itself_the_next_day(hass, entry, freezer) -> None:
    """The whole point: nobody has to remember to put it back."""
    alarm_id = await _create(hass)
    await _adjust(hass, alarm_id, time="05:30")

    data = next(iter(hass.data[DOMAIN].values()))
    freezer.move_to("2026-08-22 22:00:00+00:00")  # the Saturday after
    data.scheduler.async_reschedule_all()
    await hass.async_block_till_done()

    alarm = _alarm(hass, alarm_id)
    assert alarm.override_for is None
    assert alarm.override_time is None
    nxt = data.scheduler.async_next_fire(alarm).astimezone(dt_util.DEFAULT_TIME_ZONE)
    assert (nxt.date().isoformat(), nxt.hour, nxt.minute) == ("2026-08-24", 7, 0)
    # Clearing bails out of the scheduling pass it interrupted and lets the
    # store's own dispatch finish the job. If that ever stops being true the
    # alarm quietly loses its timer.
    assert alarm_id in data.scheduler._timers


async def test_a_moved_occurrence_missed_by_a_restart_still_rings(
    hass, entry, freezer
) -> None:
    """Down at 05:30, back at 05:35: catch-up has to know where it moved to."""
    alarm_id = await _create(hass)
    await _adjust(hass, alarm_id, time="05:30")

    data = next(iter(hass.data[DOMAIN].values()))
    data.scheduler._fire = AsyncMock()
    freezer.move_to("2026-08-21 09:35:00+00:00")  # 05:35 EDT, five minutes late
    await data.scheduler._async_catch_up()
    await hass.async_block_till_done()

    assert data.scheduler._fire.await_count == 1
    assert data.scheduler._fire.await_args.args[1] is True  # flagged as missed

    # And having rung late, it still does not ring again at 07:00.
    nxt = data.scheduler.async_next_fire(_alarm(hass, alarm_id))
    assert nxt.astimezone(dt_util.DEFAULT_TIME_ZONE).date().isoformat() == "2026-08-24"


async def test_switch_attributes_expose_the_adjustment(hass, entry) -> None:
    alarm_id = await _create(hass)
    await _adjust(hass, alarm_id, time="05:30")

    state = hass.states.get("switch.weekday")
    assert state.attributes["override_for"] == TOMORROW
    assert state.attributes["override_time"] == "05:30"


async def test_websocket_adjusts_and_clears(hass, entry, hass_ws_client) -> None:
    alarm_id = await _create(hass)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": "wakey/adjust_next", "alarm_id": alarm_id, "time": "05:30"}
    )
    assert (await client.receive_json())["success"]

    await client.send_json_auto_id({"type": "wakey/list"})
    alarm = (await client.receive_json())["result"]["alarms"][0]
    assert alarm["override_time"] == "05:30"
    assert alarm["next_fire"].startswith(TOMORROW)

    await client.send_json_auto_id(
        {"type": "wakey/adjust_next", "alarm_id": alarm_id, "clear": True}
    )
    assert (await client.receive_json())["success"]
    assert _alarm(hass, alarm_id).override_for is None


async def test_websocket_reports_a_bad_time_instead_of_failing_silently(
    hass, entry, hass_ws_client
) -> None:
    alarm_id = await _create(hass, time="23:00")
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": "wakey/adjust_next", "alarm_id": alarm_id, "time": "05:30"}
    )
    msg = await client.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"
