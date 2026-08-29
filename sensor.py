"""Sensor platform.

EVERY ENTITY HERE OVERRIDES `available` TO TRUE. A monitor that
disappears when its subject does cannot report the subject being down —
kiosk_pi's binary_sensor rule, and the reason attributes on an
unavailable entity vanishing is how a broken collector reads green.
An unreadable source shows as state `unknown` with a disposition
attribute, never as the entity going away.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory

from .const import DOMAIN, SOURCES
from .entity import HouseholdStateEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    ents = [
        StageSensor(coordinator, entry.entry_id),
        DirectiveSensor(coordinator, entry.entry_id),
        IntegritySensor(coordinator, entry.entry_id),
    ]
    for spec in SOURCES:
        ents.append(SourceSensor(coordinator, entry.entry_id, spec))
    async_add_entities(ents)


class _Base(HouseholdStateEntity, SensorEntity):
    @property
    def available(self) -> bool:
        return True


class StageSensor(_Base):
    _attr_name = "Stage"
    _attr_icon = "mdi:shield-alert-outline"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = entry_id + "_stage"

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        return d.get("stage")

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {
            "severity": d.get("severity"),
            "raw_severity": d.get("raw_severity"),
            "band": d.get("band"),
            "driver": d.get("driver"),
            "detail": d.get("detail"),
            "confidence": d.get("confidence"),
            "sources_total": d.get("sources_total"),
            "sources_healthy": d.get("sources_healthy"),
            "sources_unhealthy": d.get("sources_unhealthy"),
            "fall_dwell_holding": d.get("fall_dwell_holding"),
            "fall_dwell_since": d.get("fall_dwell_since"),
            "since": d.get("stage_since"),
        }


class DirectiveSensor(_Base):
    _attr_name = "Directive"
    _attr_icon = "mdi:sign-direction"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = entry_id + "_directive"

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        return d.get("directive")

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        # `suppressed` is deliberately always present, not omitted when
        # empty. §11.20 decision 4 declines a directive the feed DID
        # offer, and the difference between "nothing applied" and "one
        # applied and we declined it" has to be readable here or the
        # policy is invisible at exactly the moment it matters.
        return {
            "reason": d.get("directive_reason"),
            "driver": d.get("directive_driver"),
            "suppressed": d.get("directive_suppressed") or [],
            "source_count": d.get("directive_sources"),
            "since": d.get("directive_since"),
        }


class IntegritySensor(_Base):
    _attr_name = "Integrity"
    _attr_icon = "mdi:check-network-outline"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = entry_id + "_integrity"

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        return d.get("integrity")

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        # NO `severity` KEY HERE, DELIBERATELY. §7.3 / RULE 4: a
        # severity on this axis would be suppressed by Critical, which
        # is the exact inversion §11.5 exists to remove. If a future
        # edit adds one, that edit is reintroducing the bug.
        return {
            "detail": d.get("integrity_detail"),
            "driver": d.get("integrity_driver"),
            "affected_count": d.get("integrity_affected"),
            "source_count": d.get("integrity_sources"),
            "since": d.get("integrity_since"),
            # KAN-343: integrity-card.js's per-source breakdown, migrated
            # off the retired sensor.household_integrity. See resolver.py's
            # resolve() for the newline-joined label~state~detail format.
            # (Retained verbatim across the household_alert -> household_state
            # rename; sensor.household_integrity is a distinct, already-
            # retired entity name and this comment is historical.)
            "sources_detail": d.get("integrity_sources_detail"),
        }


class SourceSensor(_Base):
    """One per registry row. Diagnostic: this is where a dead feed
    becomes visible instead of becoming a zero."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id, spec):
        super().__init__(coordinator, entry_id)
        self._key = spec["key"]
        self._attr_name = spec["name"]
        self._attr_unique_id = entry_id + "_src_" + spec["key"]

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        r = (d.get("readings") or {}).get(self._key) or {}
        return r.get("disposition")

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        r = (d.get("readings") or {}).get(self._key) or {}
        return {
            "entity_id": r.get("entity_id"),
            "axis": r.get("axis"),
            "severity": r.get("severity"),
            "raw_state": r.get("raw_state"),
            "detail": r.get("detail"),
        }
