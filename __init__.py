"""household_state — the resolver half of the §11 directive layer, plus
the QUIET modifier from sleep mode.

READ-ONLY: it writes nothing, calls no service, and touches no card. It
resolves state and publishes it; sensor.household_state_stage is the
surface consumers read. See const.py for the rules and the scope decisions.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.start import async_at_started

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import HouseholdStateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    scan = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    coordinator = HouseholdStateCoordinator(hass, scan)

    # RULE 5. Ages load BEFORE the first refresh or every clock restarts
    # at zero on every HA restart.
    await coordinator.async_load_ages()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Source-condition logging stays silent until HA reaches RUNNING. Every
    # source here is another integration's entity, and the registry restores
    # an entity row well before its owner publishes a state -- so the polls
    # during boot see a house with no doors and no sources, and said so, once
    # per membership change, for the length of the boot. The READINGS are
    # untouched; only the log is gated. See coordinator.async_arm_logging.
    entry.async_on_unload(async_at_started(hass, coordinator.async_arm_logging))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
