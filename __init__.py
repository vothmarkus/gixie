from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, DOMAIN
from .coordinator import GixieClient, GixieCoordinator, GixieSettings

PLATFORMS = ["light", "switch", "number", "select"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data[CONF_HOST]

    settings = GixieSettings(host=host)
    client = GixieClient(settings=settings)
    coordinator = GixieCoordinator(hass, client, entry.entry_id)

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
