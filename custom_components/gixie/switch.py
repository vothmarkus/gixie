from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GixieCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    coordinator: GixieCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GixiePowerSwitch(coordinator, entry.entry_id)])


class GixiePowerSwitch(CoordinatorEntity, SwitchEntity):
    _attr_name = "Gixie Power"

    def __init__(self, coordinator: GixieCoordinator, entry_id: str):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_power"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("power") == 1)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_power(False)
