from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DST_OPTIONS, MODE_MAP, MODE_LABEL_TO_VALUE
from .coordinator import GixieCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    coordinator: GixieCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            GixieModeSelect(coordinator, entry.entry_id),
            GixieTimeFormatSelect(coordinator, entry.entry_id),
            GixieDstSelect(coordinator, entry.entry_id),
        ]
    )


class GixieModeSelect(CoordinatorEntity, SelectEntity):
    _attr_name = "Gixie Mode"
    _attr_options = list(MODE_MAP.values())

    def __init__(self, coordinator: GixieCoordinator, entry_id: str):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_mode"

    @property
    def current_option(self):
        v = self.coordinator.data.get("mode")
        if v is None:
            return None
        return MODE_MAP.get(int(v))

    async def async_select_option(self, option: str):
        await self.coordinator.async_set_mode(MODE_LABEL_TO_VALUE[option])


class GixieTimeFormatSelect(CoordinatorEntity, SelectEntity):
    _attr_name = "Gixie Time Format"
    _attr_options = ["12h", "24h"]

    def __init__(self, coordinator: GixieCoordinator, entry_id: str):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_time_format"

    @property
    def current_option(self):
        v = self.coordinator.data.get("time_format")
        if v is None:
            return None
        # 0 = 12h, 1 = 24h
        return "12h" if int(v) == 0 else "24h"

    async def async_select_option(self, option: str):
        # 0 = 12h, 1 = 24h
        await self.coordinator.async_set_time_format(0 if option == "12h" else 1)


class GixieDstSelect(CoordinatorEntity, SelectEntity):
    _attr_name = "Gixie DST"
    _attr_options = DST_OPTIONS

    def __init__(self, coordinator: GixieCoordinator, entry_id: str):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_dst"

    @property
    def current_option(self):
        return self.coordinator.data.get("dst_mode")

    async def async_select_option(self, option: str):
        await self.coordinator.async_set_dst_mode(option)
