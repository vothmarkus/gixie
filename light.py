from __future__ import annotations

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GixieCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GixieCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GixieClockLight(coordinator, entry.entry_id)])


class GixieClockLight(CoordinatorEntity, LightEntity):
    _attr_name = "Gixie Clock"
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB

    def __init__(self, coordinator: GixieCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_light"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("power") == 1)

    @property
    def brightness(self):
        return self.coordinator.data.get("brightness")

    @property
    def rgb_color(self):
        rgb = self.coordinator.data.get("rgb")
        if isinstance(rgb, list) and rgb:
            first = rgb[0]
            return (
                int(first.get("red", 0)),
                int(first.get("green", 0)),
                int(first.get("blue", 0)),
            )
        return None

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_power(True)

        if "brightness" in kwargs:
            await self.coordinator.async_set_brightness(kwargs["brightness"])

        if "rgb_color" in kwargs:
            r, g, b = kwargs["rgb_color"]
            await self.coordinator.async_set_rgb(r, g, b)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_power(False)