"""Binary sensors — feed health, QUIET, and the custom macro states.

`device_class: problem`, ALWAYS available. This is the entity that
answers "can I believe the stage sensor right now", and it is `on`
(problem) whenever any source is unreadable — including when stage
itself reads Normal. A layer that cannot see all its inputs and says
Normal anyway is the dead-feed-reads-green defect.

The other two classes here are MODIFIERS, not severities. QUIET is the
built-in one; MacroState is one per row the options flow defined. Neither
moves an axis (RULE 7) and neither is writable — a macro state names an
entity this installation already has and republishes what it says.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import macro_unique_id
from .coordinator import HouseholdStateConfigEntry
from .entity import HouseholdStateEntity

# Quality scale `parallel-updates`. Zero — coordinator-driven and read-only;
# see sensor.py.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass, entry: HouseholdStateConfigEntry, async_add_entities
) -> None:
    coordinator = entry.runtime_data
    entities = [
        FeedHealth(coordinator, entry.entry_id),
        Quiet(coordinator, entry.entry_id),
    ]
    # One per macro state the options flow defined. QUIET is NOT one of these
    # and is not migrated into the list: it already publishes
    # binary_sensor.household_state_quiet, and re-minting it as a macro would
    # hand that id to a new unique_id and orphan every dashboard reading it.
    entities += [
        MacroState(coordinator, entry.entry_id, macro)
        for macro in coordinator.macros
    ]
    async_add_entities(entities)


class FeedHealth(HouseholdStateEntity, BinarySensorEntity):
    _attr_name = "Feed health"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = entry_id + "_feed_health"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        d = self.coordinator.data or {}
        bad = d.get("sources_unhealthy") or []
        return bool(bad) or d.get("integrity") == "unknown"

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {
            "unhealthy": d.get("sources_unhealthy"),
            "confidence": d.get("confidence"),
            "sources_healthy": d.get("sources_healthy"),
            "sources_total": d.get("sources_total"),
        }


class Quiet(HouseholdStateEntity, BinarySensorEntity):
    """The QUIET modifier — a read-only mirror of
    input_boolean.sleep_mode, added 0.5.0.

    READ-ONLY, DELIBERATELY. This entity does not
    suppress or reroute anything on the STAGE/DIRECTIVE/INTEGRITY axes;
    it only gives a consumer one place to read the household's QUIET
    state instead of reaching into input_boolean.sleep_mode directly.
    Any future suppression behaviour is a new ruling, not an extension
    of this entity's meaning.

    `is_on` is None, never False, when the source cannot be read — the
    same the dead-feed-reads-green defect shape as every other entity here: an unreadable source
    must not read as a real negative.
    """

    _attr_name = "Quiet"
    _attr_icon = "mdi:sleep"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = entry_id + "_quiet"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self):
        d = self.coordinator.data or {}
        return d.get("quiet")

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {
            "source_entity_id": d.get("quiet_source_entity_id"),
            "raw_state": d.get("quiet_raw_state"),
            "since": d.get("quiet_since"),
        }


class MacroState(HouseholdStateEntity, BinarySensorEntity):
    """One custom macro state — a household modifier defined in the UI.

    THE GENERALISATION OF QUIET, AND NOTHING MORE. It mirrors one entity's
    state against one string and publishes the answer beside the axes. It is
    read-only: there is no switch here, because this integration does not own
    the fact — the bound entity does. An installation that wants something
    flippable still wants an `input_boolean`; what it stops needing is the
    template-sensor layer on top of one. See
    docs/migrating-from-input-boolean-helpers.md.

    NO DEVICE CLASS, DELIBERATELY. A device class renames the two states in
    every surface — `problem` renders as Detected/Clear, `occupancy` as
    Detected/Clear too, `presence` as Home/Away — and the correct pair for a
    macro state depends on a meaning the user holds and this file does not.
    Guessing one would put a word on a dashboard that nobody chose; `on`/`off`
    is the honest pair for "the thing you named is true".

    `is_on` is None, never False, when the source cannot be read.
    """

    def __init__(self, coordinator, entry_id, macro):
        super().__init__(coordinator, entry_id)
        self._slug = macro["slug"]
        self._attr_name = macro["name"]
        # The published identity, frozen at creation. See const.py: the slug
        # is the tail of this id AND, at first registration, of the entity id,
        # so a later rename moves the friendly name and nothing else.
        self._attr_unique_id = macro_unique_id(entry_id, macro["slug"])
        if macro.get("icon"):
            self._attr_icon = macro["icon"]

    @property
    def available(self) -> bool:
        return True

    def _reading(self):
        d = self.coordinator.data or {}
        return (d.get("macros") or {}).get(self._slug) or {}

    @property
    def is_on(self):
        return self._reading().get("state")

    @property
    def extra_state_attributes(self):
        r = self._reading()
        return {
            "slug": self._slug,
            "source_entity_id": r.get("entity_id"),
            # BOTH, ALWAYS. `raw_state` is what the entity said; `on_state` is
            # what this macro was told to watch for. A macro reading `off`
            # because the form says "home" and the entity says "Home" is
            # diagnosable from these two and from nothing else.
            "raw_state": r.get("raw_state"),
            "on_state": r.get("on_state"),
            "disposition": r.get("disposition"),
            "since": r.get("since"),
        }
