"""household_state — the resolver half of the §11 directive layer, plus
the QUIET modifier from sleep mode.

READ-ONLY: it writes nothing, calls no service, and touches no card. It
resolves state and publishes it; sensor.household_state_stage is the
surface consumers read. See const.py for the rules and the scope decisions.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.start import async_at_started

from .const import DEFAULT_SCAN_INTERVAL, PLATFORMS
from .coordinator import HouseholdStateConfigEntry, HouseholdStateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: HouseholdStateConfigEntry
) -> bool:
    scan = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    # GH #16. Every option that is not scan_interval is a source binding; the
    # coordinator resolves each against the SOURCES row's own default. Passed
    # as a snapshot rather than the live entry so a read mid-poll cannot see
    # half of a reconfigure — the update listener reloads the entry, which
    # rebuilds the coordinator with the new set.
    bindings = {k: v for k, v in entry.options.items() if k != "scan_interval"}
    coordinator = HouseholdStateCoordinator(hass, scan, bindings)

    # RULE 5. Ages load BEFORE the first refresh or every clock restarts
    # at zero on every HA restart.
    await coordinator.async_load_ages()
    await coordinator.async_config_entry_first_refresh()

    # `runtime-data`: the coordinator lives on the entry, so it is torn down
    # with the entry and no module-global outlives a failed unload.
    entry.runtime_data = coordinator

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


async def _async_reload(
    hass: HomeAssistant, entry: HouseholdStateConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: HouseholdStateConfigEntry
) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
