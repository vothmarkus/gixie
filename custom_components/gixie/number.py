from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DST_AUTO
from .coordinator import GixieCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    coordinator: GixieCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GixieBaseTimezoneNumber(coordinator, entry.entry_id)])


class GixieBaseTimezoneNumber(CoordinatorEntity, NumberEntity):
    _attr_name = "Gixie Base Timezone"
    _attr_native_min_value = -12
    _attr_native_max_value = 12
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "h"
    _attr_mode = "box"

    def __init__(self, coordinator: GixieCoordinator, entry_id: str):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_base_timezone"

    @property
    def native_value(self):
        return self.coordinator.data.get("base_tz_offset")

    @property
    def extra_state_attributes(self):
        if self.coordinator.data.get("dst_mode") == "auto":
            return {"controlled_by": "system timezone (DST auto)"}
        return None

    async def async_set_native_value(self, value: float):
        if self.coordinator.data.get("dst_mode") == "auto":
            return  # ignore changes in auto mode
        await self.coordinator.async_set_base_timezone(int(value))
