"""Binary sensor — feed health.

`device_class: problem`, ALWAYS available. This is the entity that
answers "can I believe the stage sensor right now", and it is `on`
(problem) whenever any source is unreadable — including when stage
itself reads Normal. A layer that cannot see all its inputs and says
Normal anyway is the dead-feed-reads-green defect.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .coordinator import HouseholdStateConfigEntry
from .entity import HouseholdStateEntity

# Quality scale `parallel-updates`. Zero — coordinator-driven and read-only;
# see sensor.py.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass, entry: HouseholdStateConfigEntry, async_add_entities
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([FeedHealth(coordinator, entry.entry_id), Quiet(coordinator, entry.entry_id)])


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
