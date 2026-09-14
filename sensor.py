"""Sensor platform.

EVERY ENTITY HERE OVERRIDES `available` TO TRUE. A monitor that
disappears when its subject does cannot report the subject being down —
a standing binary_sensor rule, and the reason attributes on an
unavailable entity vanishing is how a broken collector reads green.
An unreadable source shows as state `unknown` with a disposition
attribute, never as the entity going away.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory

from .const import DISP_OK, INTEGRITY_OK, SOURCES
from .coordinator import HouseholdStateConfigEntry
from .entity import HouseholdStateEntity

# Quality scale `parallel-updates`. Zero, and it costs nothing: every entity
# here is coordinator-driven and read-only, so there is no per-entity update
# to serialise and no device to overwhelm. Declared rather than left to the
# default because the rule is about saying which it is.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass, entry: HouseholdStateConfigEntry, async_add_entities
) -> None:
    coordinator = entry.runtime_data
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
        # empty. A ruling declines a directive the feed DID
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
        # NO `severity` KEY HERE, DELIBERATELY. RULE 4: a
        # severity on this axis would be suppressed by Critical, which
        # is the exact inversion this component exists to remove. If a future
        # edit adds one, that edit is reintroducing the bug.
        return {
            "detail": d.get("integrity_detail"),
            "driver": d.get("integrity_driver"),
            "affected_count": d.get("integrity_affected"),
            "source_count": d.get("integrity_sources"),
            "since": d.get("integrity_since"),
            # The per-source breakdown a dashboard card reads, migrated
            # off the retired sensor.household_integrity. See resolver.py's
            # resolve() for the newline-joined label~state~detail format.
            # (Retained verbatim across the household_alert -> household_state
            # rename; sensor.household_integrity is a distinct, already-
            # retired entity name and this comment is historical.)
            "sources_detail": d.get("integrity_sources_detail"),
            # Always present (#26), like the directive's: what the integrity
            # rows declined on the operator's say-so, by name.
            "suppressed": d.get("integrity_suppressed") or [],
        }


class SourceSensor(_Base):
    """One per registry row. Diagnostic: this is where a dead feed
    becomes visible instead of becoming a zero.

    THE STATE IS THE WORST THING KNOWN ABOUT THE SOURCE, NOT MERELY
    WHETHER IT COULD BE READ. It used to be `disposition` alone,
    and disposition answers a narrower question than the name on the
    entity suggests: `ok` there means "the read succeeded", never "the
    source is healthy". So a row that read cleanly and reported DEGRADED
    published `ok` — sensor.household_state_critical_networking_device_health
    sat at `ok` with `Spectrum: could not read WAN latency` in its own
    detail, underneath a roll-up correctly reporting it degraded.

    That is `ok at zero` and `could not read` collapsing into one value
    at exactly the layer built to keep them apart, and it is a
    monitor whose blind spot correlates with its own subject: any surface
    rendering per-source rows showed all-green under a degraded roll-up.

    The two facts stay separate as ATTRIBUTES — `disposition` for the
    read, `integrity` for the verdict — and the state reports the worse
    of them. An unreadable source still wins, because a verdict computed
    from a failed read is not a verdict; the resolver orders them the
    same way (unknown_rows before degraded_rows).

    STAGE rows are untouched by construction: nothing writes `integrity`
    on them, so their state is still the disposition it always was. The
    axis is not tested here — the presence of the key is the condition,
    which keeps a future non-integrity row carrying a verdict from
    needing a change in this file.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id, spec):
        super().__init__(coordinator, entry_id)
        self._key = spec["key"]
        self._attr_name = spec["name"]
        # #19: the PUBLISHED slug, which defaults to the key. Binding it is
        # what lets a key be renamed upstream without minting a new entity and
        # orphaning the one this installation already publishes.
        self._attr_unique_id = entry_id + "_src_" + coordinator.slug_for(spec)

    def _reading(self):
        d = self.coordinator.data or {}
        return (d.get("readings") or {}).get(self._key) or {}

    @property
    def native_value(self):
        r = self._reading()
        disposition = r.get("disposition")
        if disposition != DISP_OK:
            return disposition
        integrity = r.get("integrity")
        if integrity and integrity != INTEGRITY_OK:
            return integrity
        return disposition

    @property
    def extra_state_attributes(self):
        r = self._reading()
        return {
            "entity_id": r.get("entity_id"),
            "axis": r.get("axis"),
            "severity": r.get("severity"),
            "raw_state": r.get("raw_state"),
            # BOTH, ALWAYS, and never collapsed into the state alone:
            # `disposition` is whether the read worked, `integrity` is
            # what the source said. Reading one off the other is the
            # confusion this component exists to prevent.
            "disposition": r.get("disposition"),
            "integrity": r.get("integrity"),
            # The two registry-resolved integrity rows (config_entries,
            # notify_health) write `integrity_detail` and
            # never `detail` — only the `fls` kind mirrors one onto the
            # other. Reading `detail` alone is why those rows published a
            # bare `ok` with no text at all while the roll-up had their
            # reason in hand.
            "detail": r.get("detail") or r.get("integrity_detail"),
            # Which ATTRIBUTE TRIPLE this row reads, when it reads one.
            # Two integrity rows deliberately share sensor.fls_device_status
            # and are told apart only by their triple (const.py's SOURCES
            # note); with just `entity_id` exposed they looked like one
            # duplicated row, which is exactly how the indistinguishable-entity defect was raised.
            "source_attr": r.get("integrity_attr"),
            # The config-entry row's full findings and its declined set
            # (#26). `detail` above is the one-line headline; a card that
            # wants the other "+N more" reads these. `suppressed` is
            # always a list so "nothing declined" reads as [] and never
            # as absent.
            "affected_entries": r.get("affected_entries"),
            "suppressed": r.get("suppressed") or [],
        }
