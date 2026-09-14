"""The entities themselves: what they publish, and what they refuse to do.

binary_sensor.py was at 0% and sensor.py at 71% when this repo was gap-listed.
These are the classes every surface in the installation actually reads, and the
contract they hold: an entity here NEVER goes unavailable, because
attributes on an unavailable entity vanish and that is precisely how a broken
collector reads green.
"""

import asyncio

import pytest

from household_state.binary_sensor import FeedHealth, Quiet
from household_state.binary_sensor import async_setup_entry as setup_binary
from household_state.const import (
    DISP_OK,
    DISP_UNKNOWN,
    INTEGRITY_DEGRADED,
    INTEGRITY_OK,
    SOURCES,
)
from household_state.entity import HouseholdStateEntity
from household_state.sensor import (
    DirectiveSensor,
    IntegritySensor,
    SourceSensor,
    StageSensor,
)
from household_state.sensor import async_setup_entry as setup_sensor

ENTRY_ID = "01ENTRYID"


class FakeCoordinator:
    def __init__(self, data=None, macros=()):
        self.data = data
        # The macro roster the binary platform builds its entities from.
        # Empty by default: every case that is not about macros wants the
        # entity set this integration has always published.
        self.macros = tuple(macros)

    def slug_for(self, spec):
        """#19: the published slug. Defaults to the key, which is what
        every case here wants — nothing is rebound."""
        return spec["key"]


class FakeEntry:
    def __init__(self, data=None, macros=()):
        self.entry_id = ENTRY_ID
        self.runtime_data = FakeCoordinator(data, macros)


def _setup(platform, data=None, macros=()):
    """Drive a platform's async_setup_entry and return what it added."""
    added = []
    asyncio.run(platform(None, FakeEntry(data, macros), added.extend))
    return added


# ======================================================== platform setup

def test_the_sensor_platform_adds_three_axes_plus_one_row_per_source():
    ents = _setup(setup_sensor)
    assert len(ents) == 3 + len(SOURCES)
    assert [type(e).__name__ for e in ents[:3]] == [
        "StageSensor", "DirectiveSensor", "IntegritySensor"
    ]
    assert all(isinstance(e, SourceSensor) for e in ents[3:])


def test_the_binary_platform_adds_feed_health_and_quiet():
    ents = _setup(setup_binary)
    assert [type(e).__name__ for e in ents] == ["FeedHealth", "Quiet"]


def test_both_platforms_read_the_coordinator_off_the_entry():
    """`runtime-data`: nothing goes through hass.data, so hass is unused at
    setup — passing None for it here is the proof, not a shortcut."""
    entry = FakeEntry({"stage": "normal"})
    added = []
    asyncio.run(setup_sensor(None, entry, added.extend))
    assert added[0].coordinator is entry.runtime_data


def test_every_unique_id_is_distinct_and_carries_the_entry():
    ents = _setup(setup_sensor) + _setup(setup_binary)
    ids = [e.unique_id if hasattr(e, "unique_id") else e._attr_unique_id
           for e in ents]
    assert len(set(ids)) == len(ids), "unique_id collision"
    assert all(str(i).startswith(ENTRY_ID) for i in ids)


# ================================================= the availability contract

@pytest.mark.parametrize("data", [None, {}, {"stage": "critical"}])
def test_no_entity_ever_goes_unavailable(data):
    """the coordinator never raises, and every entity overrides
    `available` to true. A monitor that disappears with its subject cannot
    report the subject down."""
    for ent in _setup(setup_sensor, data) + _setup(setup_binary, data):
        assert ent.available is True


@pytest.mark.parametrize("data", [None, {}])
def test_an_empty_coordinator_publishes_none_not_a_crash(data):
    """`self.coordinator.data or {}` throughout. A first poll that has not
    landed must read as nothing known, never as an exception during state
    write."""
    for ent in _setup(setup_sensor, data):
        assert ent.native_value is None
        assert isinstance(ent.extra_state_attributes, dict)


# =============================================================== the axes

def test_the_stage_sensor_publishes_its_axis_and_dwell_state():
    data = {
        "stage": "elevated", "severity": 3, "raw_severity": 5, "band": "Elevated",
        "driver": "local_nws", "detail": "Flood Warning", "confidence": "partial",
        "sources_total": 5, "sources_healthy": 4, "sources_unhealthy": ["ntas"],
        "fall_dwell_holding": True, "fall_dwell_since": "2026-09-11T08:00:00+00:00",
        "stage_since": "2026-09-11T07:00:00+00:00",
    }
    ent = StageSensor(FakeCoordinator(data), ENTRY_ID)
    assert ent.native_value == "elevated"
    attrs = ent.extra_state_attributes
    assert attrs["severity"] == 3
    assert attrs["raw_severity"] == 5
    assert attrs["driver"] == "local_nws"
    assert attrs["fall_dwell_holding"] is True
    # `since` is read off stage_since, not off a key called `since`.
    assert attrs["since"] == "2026-09-11T07:00:00+00:00"


def test_the_directive_sensor_always_publishes_suppressed():
    """a declined signal is stated on the entity, always present. The
    difference between "nothing applied" and "one applied and we declined it"
    has to be readable at exactly the moment it matters."""
    ent = DirectiveSensor(FakeCoordinator({"directive": "none"}), ENTRY_ID)
    assert ent.extra_state_attributes["suppressed"] == []

    ent = DirectiveSensor(
        FakeCoordinator({"directive": "shelter",
                         "directive_suppressed": ["Severe Thunderstorm Warning"]}),
        ENTRY_ID)
    assert ent.extra_state_attributes["suppressed"] == ["Severe Thunderstorm Warning"]


def test_the_integrity_sensor_publishes_no_severity():
    """RULE 4. A severity on this axis would be suppressed by
    Critical, which is the inversion the contract exists to remove."""
    ent = IntegritySensor(
        FakeCoordinator({"integrity": "degraded", "integrity_detail": "2 offline"}),
        ENTRY_ID)
    attrs = ent.extra_state_attributes
    assert "severity" not in attrs
    assert attrs["detail"] == "2 offline"


def test_the_integrity_sensor_carries_the_per_source_breakdown():
    ent = IntegritySensor(
        FakeCoordinator({"integrity_sources_detail": "FLS~ok~ok\nNet~degraded~down"}),
        ENTRY_ID)
    assert ent.extra_state_attributes["sources_detail"].split("\n") == [
        "FLS~ok~ok", "Net~degraded~down"
    ]


def test_the_integrity_sensor_always_publishes_suppressed():
    """#26: [] when nothing was declined, never absent."""
    ent = IntegritySensor(FakeCoordinator({"integrity": "ok"}), ENTRY_ID)
    assert ent.extra_state_attributes["suppressed"] == []
    ent = IntegritySensor(
        FakeCoordinator({"integrity_suppressed": ["Main Bed LGTV (webostv)"]}), ENTRY_ID)
    assert ent.extra_state_attributes["suppressed"] == ["Main Bed LGTV (webostv)"]


# ========================================================== feed health

def test_feed_health_is_a_problem_when_any_source_is_unreadable():
    ent = FeedHealth(FakeCoordinator({"sources_unhealthy": ["ntas"]}), ENTRY_ID)
    assert ent.is_on is True


def test_feed_health_is_a_problem_even_while_stage_reads_normal():
    """A layer that cannot see all its inputs and says Normal anyway
    is the defect this entity exists to make visible."""
    ent = FeedHealth(
        FakeCoordinator({"stage": "normal", "sources_unhealthy": ["ntas"]}),
        ENTRY_ID)
    assert ent.is_on is True


def test_feed_health_is_a_problem_when_integrity_is_unknown():
    ent = FeedHealth(
        FakeCoordinator({"sources_unhealthy": [], "integrity": "unknown"}), ENTRY_ID)
    assert ent.is_on is True


def test_feed_health_is_clear_when_everything_reads():
    ent = FeedHealth(
        FakeCoordinator({"sources_unhealthy": [], "integrity": INTEGRITY_OK}),
        ENTRY_ID)
    assert ent.is_on is False


def test_feed_health_is_not_tripped_by_a_merely_degraded_integrity():
    """`degraded` means the sources were read and reported a fault — the feed
    is fine. Only `unknown` means the feed itself is blind."""
    ent = FeedHealth(
        FakeCoordinator({"sources_unhealthy": [], "integrity": INTEGRITY_DEGRADED}),
        ENTRY_ID)
    assert ent.is_on is False


def test_feed_health_publishes_which_sources_not_merely_how_many():
    """a directive names WHICH, never THAT."""
    ent = FeedHealth(
        FakeCoordinator({"sources_unhealthy": ["ntas", "space_weather"],
                         "sources_total": 5, "sources_healthy": 3,
                         "confidence": "partial"}),
        ENTRY_ID)
    attrs = ent.extra_state_attributes
    assert attrs["unhealthy"] == ["ntas", "space_weather"]
    assert attrs["sources_healthy"] == 3


# ================================================================= quiet

def test_quiet_mirrors_sleep_mode():
    assert Quiet(FakeCoordinator({"quiet": True}), ENTRY_ID).is_on is True
    assert Quiet(FakeCoordinator({"quiet": False}), ENTRY_ID).is_on is False


def test_quiet_is_none_not_false_when_the_source_cannot_be_read():
    """The same dead-feed shape as everything else here: an unreadable source
    must not read as a real negative."""
    ent = Quiet(FakeCoordinator({}), ENTRY_ID)
    assert ent.is_on is None
    assert ent.is_on is not False


def test_quiet_names_the_entity_it_mirrors():
    ent = Quiet(
        FakeCoordinator({"quiet": True,
                         "quiet_source_entity_id": "input_boolean.sleep_mode",
                         "quiet_raw_state": "on",
                         "quiet_since": "2026-09-11T02:00:00+00:00"}),
        ENTRY_ID)
    attrs = ent.extra_state_attributes
    assert attrs["source_entity_id"] == "input_boolean.sleep_mode"
    assert attrs["raw_state"] == "on"


def test_quiet_owns_no_device_class():
    """QUIET owns no words on any surface. A device_class would give
    it one — `problem` or `safety` both editorialise."""
    assert getattr(Quiet, "_attr_device_class", None) is None


# ========================================================= source sensors

def _source(reading, key="fls"):
    spec = {"key": key, "name": "FLS"}
    return SourceSensor(FakeCoordinator({"readings": {key: reading}}), ENTRY_ID, spec)


def test_a_source_row_reports_the_worse_of_the_two_facts():
    """`ok` on disposition means the READ succeeded, never that the
    source is healthy. A row that read cleanly and reported DEGRADED published
    `ok` underneath a roll-up correctly reporting it degraded."""
    ent = _source({"disposition": DISP_OK, "integrity": INTEGRITY_DEGRADED})
    assert ent.native_value == INTEGRITY_DEGRADED


def test_an_unreadable_source_outranks_any_verdict():
    """A verdict computed from a failed read is not a verdict."""
    ent = _source({"disposition": DISP_UNKNOWN, "integrity": INTEGRITY_DEGRADED})
    assert ent.native_value == DISP_UNKNOWN


def test_a_healthy_row_reports_ok():
    assert _source({"disposition": DISP_OK, "integrity": INTEGRITY_OK}).native_value \
        == DISP_OK


def test_a_stage_row_carrying_no_verdict_is_its_disposition():
    """Nothing writes `integrity` on a STAGE row, so its state is the
    disposition it always was — and the presence of the key is the condition,
    not the axis, so a future non-integrity row with a verdict needs no edit."""
    assert _source({"disposition": DISP_OK}).native_value == DISP_OK


def test_a_missing_reading_publishes_none():
    ent = SourceSensor(FakeCoordinator({"readings": {}}), ENTRY_ID,
                       {"key": "gone", "name": "Gone"})
    assert ent.native_value is None


def test_both_facts_stay_separately_readable_as_attributes():
    ent = _source({"disposition": DISP_OK, "integrity": INTEGRITY_DEGRADED,
                   "integrity_detail": "Spectrum: could not read WAN latency"})
    attrs = ent.extra_state_attributes
    assert attrs["disposition"] == DISP_OK
    assert attrs["integrity"] == INTEGRITY_DEGRADED
    assert attrs["detail"] == "Spectrum: could not read WAN latency"


def test_source_rows_are_diagnostic():
    """They are where a dead feed becomes visible instead of becoming a zero —
    operator information, not household state."""
    assert SourceSensor._attr_entity_category == "diagnostic"


def test_the_source_attribute_triple_is_exposed():
    """Two integrity rows deliberately share one entity_id and are told apart
    only by their attribute triple; with just entity_id exposed they looked
    like one duplicated row, which is how the indistinguishable-entity defect was raised."""
    ent = _source({"disposition": DISP_OK, "entity_id": "sensor.fls_device_status",
                   "integrity_attr": "detector_detail"})
    assert ent.extra_state_attributes["source_attr"] == "detector_detail"


# ================================================================ device

def test_all_entities_share_one_device():
    ents = _setup(setup_sensor) + _setup(setup_binary)
    infos = [e.device_info for e in ents]
    assert len({tuple(sorted(i["identifiers"])) for i in infos}) == 1
    assert infos[0]["name"] == "Household State"


def test_the_device_reports_the_shipped_version():
    """#10: this read 0.5.1 for a 0.9.0 component."""
    import json
    import pathlib

    manifest = json.loads(
        (pathlib.Path(__file__).resolve().parent.parent / "manifest.json")
        .read_text(encoding="utf-8"))
    info = HouseholdStateEntity(FakeCoordinator(), ENTRY_ID).device_info
    assert info["sw_version"] == manifest["version"]


def test_entity_names_slug_from_the_device():
    """_attr_has_entity_name, so ids read sensor.household_state_stage rather
    than sensor.household_state_stage_stage."""
    assert HouseholdStateEntity._attr_has_entity_name is True


def test_the_assertions_can_fail():
    """Self-test: this assertion set must be able to fail."""
    # The availability override must be a real override, not the default.
    assert FeedHealth(FakeCoordinator(None), ENTRY_ID).available is True
    # is_on must actually depend on the data, or every assertion above is
    # reading a constant.
    assert FeedHealth(FakeCoordinator({"sources_unhealthy": ["x"]}), ENTRY_ID).is_on
    assert not FeedHealth(FakeCoordinator({"sources_unhealthy": []}), ENTRY_ID).is_on
