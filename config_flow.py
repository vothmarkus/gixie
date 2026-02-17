from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_HOST, DOMAIN


class GixieConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is None:
            schema = vol.Schema({vol.Required(CONF_HOST): str})
            return self.async_show_form(step_id="user", data_schema=schema)

        # Simple: allow multiple instances; unique_id can be host-based
        host = user_input[CONF_HOST].strip()
        await self.async_set_unique_id(f"gixie_{host}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=f"Gixie {host}", data={CONF_HOST: host})
