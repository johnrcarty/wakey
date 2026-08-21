"""Permission checks on the services and the per-alarm entities.

Both are ways around the panel. Home Assistant applies no permission check of
its own to plain domain services, and the per-alarm entities show up on every
household member's auto-generated dashboard, so neither is covered by the
WebSocket gating.
"""

import pytest
from homeassistant.auth import EVENT_USER_REMOVED
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wakey.const import DOMAIN

KIDS_ROOM = "media_player.kids_room"
BEDROOM = "media_player.bedroom"

ALARM = {
    "name": "Weekday",
    "time": "06:30",
    "media_player": BEDROOM,
    "source_uri": "library://track/6018",
}


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    config_entry = MockConfigEntry(domain=DOMAIN, data={}, title="Wakey")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def _store(hass):
    return next(iter(hass.data[DOMAIN].values())).store


# --- services --------------------------------------------------------------


async def test_automation_calls_are_unrestricted_and_leave_the_alarm_unowned(
    hass, entry
) -> None:
    """An automation has no user, so there are no permissions to apply."""
    await hass.services.async_call(DOMAIN, "create", ALARM, blocking=True)
    await hass.async_block_till_done()

    alarms = _store(hass).async_all()
    assert len(alarms) == 1
    assert alarms[0].owner_id is None


async def test_service_create_accepts_notify_targets(hass, entry) -> None:
    await hass.services.async_call(
        DOMAIN, "create", {**ALARM, "notify_targets": ["notify.phone"]}, blocking=True
    )
    await hass.async_block_till_done()

    assert _store(hass).async_all()[0].notify_targets == ["notify.phone"]


async def test_an_automation_can_name_the_owner(hass, entry, kid_user) -> None:
    await hass.services.async_call(
        DOMAIN, "create", {**ALARM, "owner_id": kid_user.id}, blocking=True
    )
    await hass.async_block_till_done()

    assert _store(hass).async_all()[0].owner_id == kid_user.id


async def test_service_create_enforces_the_allowlist(hass, entry, kid_user) -> None:
    _store(hass).async_set_policy(kid_user.id, [KIDS_ROOM])
    context = Context(user_id=kid_user.id)

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, "create", ALARM, blocking=True, context=context
        )

    assert _store(hass).async_all() == []


async def test_service_create_stamps_the_calling_user(hass, entry, kid_user) -> None:
    _store(hass).async_set_policy(kid_user.id, [KIDS_ROOM])

    await hass.services.async_call(
        DOMAIN,
        "create",
        {**ALARM, "media_player": KIDS_ROOM},
        blocking=True,
        context=Context(user_id=kid_user.id),
    )
    await hass.async_block_till_done()

    assert _store(hass).async_all()[0].owner_id == kid_user.id


@pytest.mark.parametrize(
    ("service", "extra"),
    [
        ("update", {"time": "03:00"}),
        ("delete", {}),
        ("trigger_now", {}),
        ("skip_next", {}),
        ("adjust_next", {"time": "03:00"}),
    ],
)
async def test_services_refuse_another_users_alarm(
    hass, entry, kid_user, other_user, service, extra
) -> None:
    """trigger_now on someone else's speaker was wide open before this."""
    theirs = _store(hass).async_create({**ALARM, "owner_id": other_user.id})

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            service,
            {"alarm_id": theirs.id, **extra},
            blocking=True,
            context=Context(user_id=kid_user.id),
        )

    assert _store(hass).async_get(theirs.id).time == ALARM["time"]


async def test_trigger_now_still_works_for_an_automation(hass, entry, other_user) -> None:
    alarm = _store(hass).async_create({**ALARM, "owner_id": other_user.id})

    await hass.services.async_call(
        DOMAIN, "trigger_now", {"alarm_id": alarm.id}, blocking=True
    )
    await hass.async_block_till_done()

    data = next(iter(hass.data[DOMAIN].values()))
    assert alarm.id in data.player.ringing


async def test_a_deleted_user_is_refused(hass, entry) -> None:
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "create",
            ALARM,
            blocking=True,
            context=Context(user_id="ghost-user"),
        )


async def test_removing_a_user_unassigns_their_alarms(hass, entry, kid_user) -> None:
    """Alarms of a removed user must fall back to unowned, or 'assign all to
    me' in the People tab can never reclaim them — it only matches a falsy
    owner_id, and a removed user's id is neither empty nor reachable again."""
    alarm = _store(hass).async_create({**ALARM, "owner_id": kid_user.id})

    hass.bus.async_fire(EVENT_USER_REMOVED, {"user_id": kid_user.id})
    await hass.async_block_till_done()

    assert _store(hass).async_get(alarm.id).owner_id is None


async def test_delete_service_errors_if_alarm_vanished_mid_dismiss(hass, entry) -> None:
    """Service _delete awaits async_dismiss() before deleting from the store.
    If the alarm is gone by the time that await returns, the service must not
    silently succeed without having deleted anything."""
    alarm = _store(hass).async_create(ALARM)
    data = next(iter(hass.data[DOMAIN].values()))
    real_dismiss = data.player.async_dismiss

    async def _dismiss_and_vanish(*args, **kwargs):
        result = await real_dismiss(*args, **kwargs)
        data.store.async_delete(alarm.id)
        return result

    data.player.async_dismiss = _dismiss_and_vanish

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "delete", {"alarm_id": alarm.id}, blocking=True
        )


# --- entities --------------------------------------------------------------


def _entity_id(hass, alarm, suffix=""):
    """The registry id for one of an alarm's entities."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    unique_id = f"{alarm.id}{suffix}"
    for entry in registry.entities.values():
        if entry.platform == DOMAIN and entry.unique_id == unique_id:
            return entry.entity_id
    raise AssertionError(f"no entity with unique_id {unique_id}")


async def test_test_button_refuses_another_users_alarm(
    hass, entry, kid_user, other_user
) -> None:
    """The dashboard route to the same prank: press Test on dad's alarm."""
    theirs = _store(hass).async_create({**ALARM, "owner_id": other_user.id})
    await hass.async_block_till_done()
    button = _entity_id(hass, theirs, "_test")

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": button},
            blocking=True,
            context=Context(user_id=kid_user.id),
        )

    data = next(iter(hass.data[DOMAIN].values()))
    assert data.player.ringing == {}


async def test_alarm_switch_refuses_another_users_alarm(
    hass, entry, kid_user, other_user
) -> None:
    theirs = _store(hass).async_create({**ALARM, "owner_id": other_user.id})
    await hass.async_block_till_done()

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": _entity_id(hass, theirs, "_enabled")},
            blocking=True,
            context=Context(user_id=kid_user.id),
        )

    assert _store(hass).async_get(theirs.id).enabled is True


async def test_alarm_time_refuses_another_users_alarm(
    hass, entry, kid_user, other_user
) -> None:
    theirs = _store(hass).async_create({**ALARM, "owner_id": other_user.id})
    await hass.async_block_till_done()

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "time",
            "set_value",
            {"entity_id": _entity_id(hass, theirs, "_time"), "time": "03:00:00"},
            blocking=True,
            context=Context(user_id=kid_user.id),
        )

    assert _store(hass).async_get(theirs.id).time == ALARM["time"]


async def test_the_owner_can_operate_their_own_entities(hass, entry, kid_user) -> None:
    mine = _store(hass).async_create({**ALARM, "owner_id": kid_user.id})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": _entity_id(hass, mine, "_enabled")},
        blocking=True,
        context=Context(user_id=kid_user.id),
    )

    assert _store(hass).async_get(mine.id).enabled is False


async def test_entities_still_work_for_automations(hass, entry, other_user) -> None:
    """A context with no user is the scheduler or an automation. Allow it."""
    alarm = _store(hass).async_create({**ALARM, "owner_id": other_user.id})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": _entity_id(hass, alarm, "_enabled")}, blocking=True
    )

    assert _store(hass).async_get(alarm.id).enabled is False
