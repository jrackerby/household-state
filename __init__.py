"""household_state — the resolver half of the household directive layer, plus
the QUIET modifier from sleep mode and any custom macro states the options
flow defines.

READ-ONLY: it writes nothing, calls no service, and touches no card. It
resolves state and publishes it; sensor.household_state_stage is the
surface consumers read. See const.py for the rules and the scope decisions.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.start import async_at_started

from .const import (
    DEFAULT_SCAN_INTERVAL,
    MACRO_UNIQUE_ID_PREFIX,
    NON_BINDING_OPTIONS,
    PLATFORMS,
    macro_unique_id,
    macros_from_options,
)
from .coordinator import HouseholdStateConfigEntry, HouseholdStateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: HouseholdStateConfigEntry
) -> bool:
    scan = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    # #16. Every option that is not in NON_BINDING_OPTIONS is a source
    # binding; the coordinator resolves each against the SOURCES row's own
    # default. A non-binding option that forgets to declare itself there is
    # handed to the coordinator as a binding for a source named after itself,
    # which resolves to nothing and says nothing. Passed
    # as a snapshot rather than the live entry so a read mid-poll cannot see
    # half of a reconfigure — the update listener reloads the entry, which
    # rebuilds the coordinator with the new set.
    bindings = {
        k: v for k, v in entry.options.items() if k not in NON_BINDING_OPTIONS
    }
    macros = macros_from_options(entry.options)
    coordinator = HouseholdStateCoordinator(hass, scan, bindings, macros)

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

    # Before the platforms are set up, not after: an entity added and then
    # removed in the same pass would flicker through every surface subscribed
    # to the registry.
    _prune_deleted_macros(hass, entry, macros)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


def _prune_deleted_macros(hass: HomeAssistant, entry, macros) -> None:
    """Delete the registry rows of macro states that no longer exist.

    WHY THIS IS NOT LEFT TO HOME ASSISTANT. Nothing reclaims an entity row when
    the thing that created it stops being declared: a macro removed in the
    options flow would otherwise keep publishing
    `binary_sensor.household_state_<slug>` forever, permanently unavailable,
    and the id would stay taken — so re-adding the same macro later would land
    on `_2` and every dashboard would keep reading the ghost. That is the same
    id-is-never-reclaimed problem the README warns about for reinstalls, except
    here it is reachable from a form, which makes it routine rather than rare.

    ONLY MACRO ROWS, AND ONLY THIS ENTRY'S. The prefix match is against a
    unique_id this file and const.py agree on; the axis sensors, the per-source
    diagnostics, QUIET and feed health carry no `_macro_` prefix and cannot be
    caught by it.

    GUARDED, LIKE EVERY OTHER REGISTRY CALL IN THIS COMPONENT. The registry API
    can move under an upgrade, and a cleanup that fails must never take setup
    down with it: a stale entity row is untidy, an integration that will not
    start is an outage.
    """
    keep = {macro_unique_id(entry.entry_id, m["slug"]) for m in macros}
    try:
        registry = er.async_get(hass)
        rows = er.async_entries_for_config_entry(registry, entry.entry_id)
        prefix = entry.entry_id + MACRO_UNIQUE_ID_PREFIX
        stale = [
            row.entity_id
            for row in rows
            if str(row.unique_id).startswith(prefix) and row.unique_id not in keep
        ]
        for entity_id in stale:
            registry.async_remove(entity_id)
    except Exception as exc:  # noqa: BLE001 — RULE 1, applied to setup
        # WARNING, not debug. Setup survived, but a macro's entity row did not
        # get removed and nothing else will ever remove it — somebody has to
        # delete it by hand under Settings -> Entities. A cleanup that fails
        # silently leaves a ghost entity and no trace of why.
        _LOGGER.warning(
            "household_state: could not remove the entities of deleted macro "
            "states; delete them by hand under Settings -> Entities: %s",
            exc,
        )


async def _async_reload(
    hass: HomeAssistant, entry: HouseholdStateConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: HouseholdStateConfigEntry
) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
