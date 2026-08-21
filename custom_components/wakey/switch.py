"""Enable/disable switch for each Wakey alarm."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_ALARM_REGISTERED
from .entity import WakeyAlarmEntity
from .store import AlarmEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]

    @callback
    def _add(alarm: AlarmEntry) -> None:
        async_add_entities(
            [WakeyAlarmSwitch(data, alarm.id), WakeySkipNextSwitch(data, alarm.id)]
        )

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ALARM_REGISTERED, _add)
    )

    entities: list[SwitchEntity] = []
    for alarm in data.store.async_all():
        entities.append(WakeyAlarmSwitch(data, alarm.id))
        entities.append(WakeySkipNextSwitch(data, alarm.id))
    async_add_entities(entities)


class WakeyAlarmSwitch(WakeyAlarmEntity, SwitchEntity):
    """Whether this alarm is armed."""

    _attr_name = None  # takes the device (alarm) name
    _attr_icon = "mdi:alarm"

    def __init__(self, data, alarm_id: str) -> None:
        super().__init__(data, alarm_id)
        self._attr_unique_id = f"{alarm_id}_enabled"

    @property
    def is_on(self) -> bool:
        alarm = self.alarm
        return bool(alarm and alarm.enabled)

    @property
    def extra_state_attributes(self) -> dict:
        alarm = self.alarm
        if alarm is None:
            return {}
        return {
            "time": alarm.time,
            "repeat": alarm.repeat,
            "weekdays": alarm.weekdays,
            "date": alarm.date,
            "skip_next": alarm.skip_next,
            "override_for": alarm.override_for,
            "override_time": alarm.override_time,
            "media_player": alarm.media_player,
            "volume": alarm.volume,
            "ringing": self._alarm_id in self._data.player.ringing,
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self.async_assert_may_control()
        self._data.store.async_update(self._alarm_id, {"enabled": True})

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_assert_may_control()
        self._data.store.async_update(self._alarm_id, {"enabled": False})
        await self._data.player.async_dismiss(self._alarm_id, reason="disabled")


class WakeySkipNextSwitch(WakeyAlarmEntity, SwitchEntity):
    """Skip just the next occurrence.

    A separate entity rather than only a panel button so it works by voice —
    "turn on skip next for the weekday alarm" — and from automations. The flag
    clears itself once the skipped occurrence has passed.
    """

    _attr_name = "Skip next"
    _attr_icon = "mdi:debug-step-over"
    _attr_entity_registry_enabled_default = False

    def __init__(self, data, alarm_id: str) -> None:
        super().__init__(data, alarm_id)
        self._attr_unique_id = f"{alarm_id}_skip_next"

    @property
    def is_on(self) -> bool:
        alarm = self.alarm
        return bool(alarm and alarm.skip_next)

    async def async_turn_on(self, **kwargs) -> None:
        await self.async_assert_may_control()
        self._data.store.async_update(self._alarm_id, {"skip_next": True})

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_assert_may_control()
        self._data.store.async_update(self._alarm_id, {"skip_next": False})
