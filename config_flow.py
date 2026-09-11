"""Config flow. Single entry — there is one household."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    BINDABLE,
    BINDABLE_TEXT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    bind_key,
)


class HouseholdStateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Household State", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HouseholdStateOptionsFlow()


class HouseholdStateOptionsFlow(config_entries.OptionsFlow):
    """Poll interval, plus which entity supplies each source (GH #16).

    ONE STEP, DELIBERATELY. A multi-step options flow must merge every step
    over entry.options because async_create_entry(data=...) REPLACES them
    wholesale — TOOLS.md records that trap, and it is invisible until a second
    step is added. A single step cannot hit it: what this form returns IS the
    complete option set. If this ever grows a second step, every step has to
    merge, and the test that pins the binding round-trip is the one that will
    catch a step that forgets.
    """

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = {
            vol.Optional(
                "scan_interval",
                default=options.get("scan_interval", DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300))
        }

        # Bindings are OPTIONAL and default to whatever is already set. An
        # unset binding falls through to the SOURCES row's own default in the
        # coordinator, so leaving the whole form alone changes nothing.
        for source_key, field, _domain, label in BINDABLE:
            key = bind_key(source_key, field)
            schema[vol.Optional(key, description={"suggested_value": options.get(key)})] = str
        for source_key, field, label in BINDABLE_TEXT:
            key = bind_key(source_key, field)
            schema[vol.Optional(key, description={"suggested_value": options.get(key)})] = str

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
