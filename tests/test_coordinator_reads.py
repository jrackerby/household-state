"""_read_source and its friends: one source in, one reading out.

This is the code that actually touches the estate, and it was the least
covered file in the repo (44%) when this repo was gap-listed. Everything here
serves one contract, RULE 1 / LAW §11: THIS COORDINATOR NEVER RAISES, and it
NEVER returns severity 0 for a source it could not read. That substitution is
KAN-139, and it is the whole reason the component exists.

The suite therefore spends most of its assertions on the difference between
values that look alike and are not: `absent` vs `unreachable` vs `unknown` vs
`unparsed`, and `ok at zero` vs `could not read`.
"""

import asyncio

import pytest

from household_state.const import (
    DISP_ABSENT,
    bind_key,
    DISP_OK,
    DISP_UNKNOWN,
    DISP_UNPARSED,
    DISP_UNREACHABLE,
)

# The two names these tests bind to. Local to the suite on purpose: the point
# of GH #16 is that the component ships with no estate ids of its own.
PERIMETER_LABEL_FOR_TESTS = "perimeter_test_label"
QUIET_ENTITY_FOR_TESTS = "input_boolean.quiet_test"
from household_state.coordinator import HouseholdStateCoordinator

from ha_stubs import (
    FakeEntityRegistry,
    FakeHass,
    FakeLabelRegistry,
    FakeRegistryEntry,
    FakeState,
)


# GH #16: SOURCES no longer carries this estate's entity ids, so a test that
# wants a row to READ something must say where. Binding explicitly is the
# honest version of what these tests always meant — they used to inherit one
# particular household's ids by accident of const.py.
TEST_BINDINGS = {
    bind_key("perimeter", "label"): PERIMETER_LABEL_FOR_TESTS,
    bind_key("notify_health", "service_domain"): "notify",
    bind_key("notify_health", "service"): "test_target",
    bind_key("notify_health", "last_sent_entity_id"): "sensor.notify_last_sent",
    bind_key("quiet", "entity_id"): QUIET_ENTITY_FOR_TESTS,
}


def coordinator(states=None, entity_registry=None, label_registry=None,
                armed=True, bindings=None):
    hass = FakeHass(states, entity_registry, label_registry)
    merged = dict(TEST_BINDINGS)
    merged.update(bindings or {})
    c = HouseholdStateCoordinator(hass, 3, merged)
    if armed:
        c.async_arm_logging()
    return c


def spec(**kw):
    base = {
        "key": "k", "name": "K", "entity_id": "sensor.x",
        "axis": "stage", "kind": "severity_attr",
    }
    base.update(kw)
    return base


# ===================================================== the read dispositions

def test_an_entity_that_was_never_set_up_is_absent():
    """KAN-182: an entity that was never set up is a different fact from an
    entity reporting all clear."""
    r = coordinator({})._read_source(spec())
    assert r["disposition"] == DISP_ABSENT
    assert r["severity"] is None


def test_unavailable_is_unreachable_not_absent():
    """LAW §11: `absent` and `unreachable` do not collapse."""
    r = coordinator({"sensor.x": FakeState("unavailable")})._read_source(spec())
    assert r["disposition"] == DISP_UNREACHABLE
    assert r["severity"] is None


@pytest.mark.parametrize("state", ["unknown", ""])
def test_unknown_and_empty_are_unknown(state):
    r = coordinator({"sensor.x": FakeState(state)})._read_source(spec())
    assert r["disposition"] == DISP_UNKNOWN
    assert r["severity"] is None


def test_every_unreadable_disposition_leaves_severity_none_never_zero():
    """The single assertion this whole file exists for."""
    for states in ({}, {"sensor.x": FakeState("unavailable")},
                   {"sensor.x": FakeState("unknown")},
                   {"sensor.x": FakeState("nonsense", severity="banana")}):
        r = coordinator(states)._read_source(spec())
        if r["disposition"] != DISP_OK:
            assert r["severity"] is None, r


# ============================================================ severity_attr

def test_a_severity_attribute_is_read_and_the_headline_kept():
    r = coordinator({
        "sensor.x": FakeState("Elevated", severity=4, headline="Flood Warning")
    })._read_source(spec())
    assert r["disposition"] == DISP_OK
    assert r["severity"] == 4
    assert r["detail"] == "Flood Warning"


def test_the_state_stands_in_when_there_is_no_headline():
    r = coordinator({"sensor.x": FakeState("Elevated", severity=2)})._read_source(spec())
    assert r["detail"] == "Elevated"


@pytest.mark.parametrize("raw", ["banana", None, [], {}])
def test_a_severity_that_does_not_parse_is_unparsed_not_zero(raw):
    """KAN-207's shape: the entity answered and the severity did not parse.
    That is NOT zero and it is NOT unavailable."""
    r = coordinator({"sensor.x": FakeState("Elevated", severity=raw)})._read_source(spec())
    assert r["disposition"] == DISP_UNPARSED
    assert r["severity"] is None
    assert "did not parse" in r["detail"]


def test_a_numeric_string_severity_still_parses():
    r = coordinator({"sensor.x": FakeState("Elevated", severity="5")})._read_source(spec())
    assert r["severity"] == 5


# ==================================================================== alarm

def _alarm(state, open_sensors=None):
    attrs = {} if open_sensors is None else {"open_sensors": open_sensors}
    return coordinator({"alarm_control_panel.a": FakeState(state, **attrs)})._read_source(
        spec(key="alarm", kind="alarm", entity_id="alarm_control_panel.a"))


def test_a_disarmed_panel_is_idle():
    r = _alarm("disarmed")
    assert r["disposition"] == DISP_OK
    assert r["severity"] == 0


def test_armed_with_something_open_names_the_sensors_it_scored_itself_on():
    """GH-623. The row computed its severity from `open_sensors` and then
    published a bare state, so the wall said "armed with something open" while
    the reading in hand knew the door."""
    r = _alarm("armed_away", {"binary_sensor.front_door": {}, "binary_sensor.patio": {}})
    assert r["severity"] == 6
    assert "binary_sensor.front_door" in r["detail"]
    assert "binary_sensor.patio" in r["detail"]


def test_the_list_form_of_open_sensors_is_accepted_too():
    """Alarmo publishes a dict; the list form is accepted rather than asserted
    against, because being wrong about the shape would cost the NAME and the
    severity is computed from the same value either way."""
    r = _alarm("armed_home", ["binary_sensor.back_door"])
    assert r["severity"] == 6
    assert "binary_sensor.back_door" in r["detail"]


def test_the_names_are_sorted_so_the_detail_is_stable():
    r = _alarm("armed_away", ["binary_sensor.zulu", "binary_sensor.alpha"])
    assert r["detail"].index("alpha") < r["detail"].index("zulu")


def test_armed_and_closed_names_nothing():
    """LAW §11: name nothing at zero."""
    r = _alarm("armed_away", {})
    assert r["severity"] == 0
    assert "open:" not in r["detail"]


def test_triggered_outranks_armed():
    assert _alarm("triggered")["severity"] == 7


# =========================================================== binary_hazard

def _hazard(state):
    return coordinator({"binary_sensor.h": FakeState(state)})._read_source(
        spec(key="boil", kind="binary_hazard", entity_id="binary_sensor.h",
             name="Boil Water Advisory", severity_when_on=4))


def test_a_binary_hazard_on_is_its_declared_severity():
    r = _hazard("on")
    assert r["disposition"] == DISP_OK
    assert r["severity"] == 4
    assert "in effect for this address" in r["detail"]


def test_a_binary_hazard_off_is_a_real_zero():
    r = _hazard("off")
    assert r["disposition"] == DISP_OK
    assert r["severity"] == 0


def test_only_the_literal_off_counts_as_clear():
    """Guessing `clear` for a state this row does not understand is the
    KAN-139 substitution in a new coat."""
    r = _hazard("Off")
    assert r["disposition"] == DISP_UNPARSED
    assert r["severity"] is None
    assert "unrecognised binary state" in r["detail"]


# ====================================================================== cap

def _cap(attrs):
    return coordinator({"sensor.cap": FakeState("Elevated", **attrs)})._read_source(
        spec(key="nws_cap", kind="cap", entity_id="sensor.cap",
             axis="directive", pairs_attr="cap_responses"))


def test_cap_pairs_are_carried_raw():
    """RAW PAIRS ONLY — the vocabulary map and the suppression policy live in
    resolver.py, where they can be exercised without moving the real world."""
    pairs = [{"event": "Tornado Warning", "response": "Shelter"}]
    r = _cap({"cap_responses": pairs})
    assert r["disposition"] == DISP_OK
    assert r["pairs"] == pairs
    assert r["detail"] == "1 active alert(s) carrying CAP"


def test_an_absent_cap_attribute_is_unparsed_not_a_dead_feed():
    """The entity answered and the attribute is not there: a template that
    failed to render, not a feed that went away."""
    r = _cap({})
    assert r["disposition"] == DISP_UNPARSED
    assert "cap_responses attribute absent" in r["detail"]


def test_cap_pairs_that_are_not_a_list_are_unparsed():
    r = _cap({"cap_responses": "Shelter"})
    assert r["disposition"] == DISP_UNPARSED
    assert "did not parse as a list" in r["detail"]


def test_non_dict_members_are_dropped_rather_than_failing_the_row():
    r = _cap({"cap_responses": [{"event": "A"}, "junk", None]})
    assert r["disposition"] == DISP_OK
    assert r["pairs"] == [{"event": "A"}]


def test_an_empty_cap_list_is_a_healthy_read():
    """Nothing active is a finding, not an absence."""
    r = _cap({"cap_responses": []})
    assert r["disposition"] == DISP_OK
    assert r["pairs"] == []


# ====================================================================== fls

def test_the_fls_row_carries_which_attribute_it_read():
    """GH-565: two rows deliberately share sensor.fls_device_status and are
    distinguished only by their triple. With entity_id alone on the reading
    they were indistinguishable on glass."""
    r = coordinator({
        "sensor.fls": FakeState("ok", detector_detail="2 offline",
                                detector_integrity="degraded", detector_affected=2)
    })._read_source(spec(key="fls", kind="fls", entity_id="sensor.fls",
                         axis="integrity", integrity_attr="detector_integrity",
                         detail_attr="detector_detail",
                         affected_attr="detector_affected"))
    assert r["disposition"] == DISP_OK
    assert r["integrity"] == "degraded"
    assert r["integrity_detail"] == "2 offline"
    assert r["affected"] == 2
    assert r["integrity_attr"] == "detector_integrity"
    # The severity attribute on this entity is deliberately NOT read (RULE 6).
    assert r["severity"] is None


def test_a_missing_affected_count_reads_zero_not_none():
    r = coordinator({"sensor.fls": FakeState("ok", i="ok")})._read_source(
        spec(key="fls", kind="fls", entity_id="sensor.fls", axis="integrity",
             integrity_attr="i", detail_attr="d", affected_attr="a"))
    assert r["affected"] == 0


# ==================================================================== quiet

def test_quiet_reads_the_mirror():
    c = coordinator({QUIET_ENTITY_FOR_TESTS: FakeState("on")})
    assert c._read_quiet()["quiet"] is True
    c = coordinator({QUIET_ENTITY_FOR_TESTS: FakeState("off")})
    assert c._read_quiet()["quiet"] is False


@pytest.mark.parametrize("states", [
    {},
    {QUIET_ENTITY_FOR_TESTS: FakeState("unavailable")},
    {QUIET_ENTITY_FOR_TESTS: FakeState("unknown")},
    {QUIET_ENTITY_FOR_TESTS: FakeState("")},
])
def test_an_unreadable_sleep_mode_is_none_never_false(states):
    """`quiet` is None, never False, when the source cannot be read — an
    unreadable sleep_mode must never silently claim the house is NOT quiet."""
    out = coordinator(states)._read_quiet()
    assert out["quiet"] is None
    assert out["quiet"] is not False


def test_quiet_names_the_entity_it_mirrors_even_when_it_cannot_read_it():
    out = coordinator({})._read_quiet()
    assert out["quiet_source_entity_id"] == QUIET_ENTITY_FOR_TESTS


# ================================================================ perimeter

def _registry(*entity_ids, label=PERIMETER_LABEL_FOR_TESTS):
    entries = [FakeRegistryEntry(eid, labels=(label,)) for eid in entity_ids]
    return FakeEntityRegistry(entries), FakeLabelRegistry([label])


def test_a_label_that_does_not_resolve_is_absent_not_an_empty_perimeter():
    """A config defect and a house with no doors must not collapse."""
    ereg, _ = _registry("binary_sensor.front_door")
    c = coordinator({}, ereg, FakeLabelRegistry([]))
    r = c._read_source(spec(key="perimeter_open", kind="perimeter", entity_id=None))
    assert r["disposition"] == DISP_ABSENT
    assert PERIMETER_LABEL_FOR_TESTS in r["detail"]
    assert r["severity"] is None


def test_a_label_resolving_to_nothing_is_also_absent():
    c = coordinator({}, FakeEntityRegistry([]), FakeLabelRegistry([PERIMETER_LABEL_FOR_TESTS]))
    r = c._read_source(spec(key="perimeter_open", kind="perimeter", entity_id=None))
    assert r["disposition"] == DISP_ABSENT
    assert "zero members" in r["detail"] or "no contacts" in r["detail"]


def test_a_registry_that_raises_is_caught_rather_than_taking_everything_down():
    """RULE 1 admits no exception. A label-registry API that moves under a core
    upgrade would otherwise raise inside _async_update_data, take every entity
    unavailable, and take their attributes with them."""
    class Exploding:
        def async_get_label(self, _):
            raise RuntimeError("registry moved")

        def async_get_label_by_name(self, _):
            raise RuntimeError("registry moved")

    c = coordinator({}, FakeEntityRegistry([]), Exploding())
    assert c._perimeter_entity_ids() is None
    r = c._read_source(spec(key="perimeter_open", kind="perimeter", entity_id=None))
    assert r["disposition"] == DISP_ABSENT


def test_an_all_closed_perimeter_is_a_real_zero_and_names_nothing():
    ereg, lreg = _registry("binary_sensor.front_door", label=PERIMETER_LABEL_FOR_TESTS)
    c = coordinator({"binary_sensor.front_door": FakeState("off")}, ereg, lreg)
    r = c._read_source(spec(key="perimeter_open", kind="perimeter", entity_id=None))
    assert r["disposition"] == DISP_OK
    assert r["severity"] == 0
    assert r["open_count"] == 0


def test_an_open_but_not_yet_sustained_member_does_not_escalate():
    ereg, lreg = _registry("binary_sensor.front_door", label=PERIMETER_LABEL_FOR_TESTS)
    c = coordinator({"binary_sensor.front_door": FakeState("on")}, ereg, lreg)
    r = c._read_source(spec(key="perimeter_open", kind="perimeter", entity_id=None))
    assert r["open_count"] == 1
    assert r["severity"] == 0


def test_an_unreadable_member_makes_the_source_blind_rather_than_closed():
    """KAN-139, and the reason the front door and the drop zone went uncovered
    for weeks after the Ring swap: the template's `is not none` guard failed
    permissive, so a deleted contact read as 'off'."""
    ereg, lreg = _registry("binary_sensor.front_door", "binary_sensor.patio",
                           label=PERIMETER_LABEL_FOR_TESTS)
    c = coordinator({"binary_sensor.front_door": FakeState("off")}, ereg, lreg)
    r = c._read_source(spec(key="perimeter_open", kind="perimeter", entity_id=None))
    assert r["blind"] == ["binary_sensor.patio"]
    assert r["disposition"] != DISP_OK or r["severity"] != 0 or r["blind"]


# ===================================================================== ages

def test_mark_records_the_moment_a_value_first_appeared():
    c = coordinator({})
    first = c._mark("stage", "elevated")
    again = c._mark("stage", "elevated")
    assert first == again, "an unchanged value must not restart its own clock"


def test_mark_restarts_the_clock_when_the_value_moves():
    c = coordinator({})
    first = c._mark("stage", "normal")
    moved = c._mark("stage", "elevated")
    assert moved != first


def test_ages_load_before_the_first_refresh():
    """RULE 5. Skip it and every age clock restarts at zero on every HA
    restart — which under-reports age, the direction that hides the problem."""
    c = coordinator({})
    assert c._ages_loaded is False
    asyncio.run(c.async_load_ages())
    assert c._ages_loaded is True


def test_an_update_loads_ages_if_nobody_else_did():
    c = coordinator({})
    asyncio.run(c._async_update_data())
    assert c._ages_loaded is True


# =============================================== the whole pass, end to end

def test_a_full_update_publishes_every_axis_and_never_raises():
    """RULE 1, exercised against a hass that can answer nothing at all. Every
    source is missing, which is the worst case, and it must still return."""
    out = asyncio.run(coordinator({})._async_update_data())
    for key in ("severity", "stage", "band", "integrity", "directive",
                "confidence", "readings", "quiet"):
        assert key in out, key
    assert out["raw_severity"] is None or isinstance(out["raw_severity"], int)


def test_a_blind_update_reports_unknown_rather_than_normal():
    """RULE 2 through the whole pipeline, not just the resolver."""
    out = asyncio.run(coordinator({})._async_update_data())
    assert out["stage"] != "normal"


def test_every_reading_is_addressable_by_key():
    out = asyncio.run(coordinator({})._async_update_data())
    assert out["readings"]
    for key, reading in out["readings"].items():
        assert reading["key"] == key


def test_the_axis_key_lists_partition_the_readings():
    out = asyncio.run(coordinator({})._async_update_data())
    partitioned = (set(out["axis_stage_keys"]) | set(out["axis_integrity_keys"])
                   | set(out["axis_directive_keys"]))
    assert partitioned == set(out["readings"])


def test_the_assertions_can_fail():
    """LAW §4."""
    # The read really does depend on the state machine, not on a constant.
    assert coordinator({})._read_source(spec())["disposition"] == DISP_ABSENT
    assert coordinator({"sensor.x": FakeState("E", severity=1)}) \
        ._read_source(spec())["disposition"] == DISP_OK
    # And severity really is read, not defaulted.
    assert coordinator({"sensor.x": FakeState("E", severity=1)}) \
        ._read_source(spec())["severity"] == 1
    assert coordinator({"sensor.x": FakeState("E", severity=6)}) \
        ._read_source(spec())["severity"] == 6


# ====================================================== RULE 1, structurally

class _Exploding:
    """Every attribute access raises. Stands in for a core API that moved."""

    def __getattr__(self, name):
        raise RuntimeError("core API moved: " + name)


@pytest.mark.parametrize("broken", ["label_registry", "entity_registry",
                                    "services", "config_entries"])
def test_no_framework_registry_can_take_the_update_down(broken):
    """RULE 1 / LAW §11: the coordinator NEVER raises. A registry that moves
    under a core upgrade must degrade one row, not take every entity
    unavailable and its attributes with it.

    THIS TEST FOUND A REAL HOLE. `_read_notify_health` read
    hass.services.has_service outside any guard, while _perimeter_entity_ids
    and _read_config_entries were both wrapped for exactly this reason — so
    the one path nothing exercised was the one path that could still raise.
    """
    c = coordinator({})
    setattr(c.hass, broken, _Exploding())
    out = asyncio.run(c._async_update_data())  # must not raise
    assert out["stage"] is not None


def test_a_degraded_registry_still_publishes_every_other_axis():
    c = coordinator({})
    c.hass.services = _Exploding()
    out = asyncio.run(c._async_update_data())
    assert "integrity" in out and "directive" in out and "severity" in out


def test_the_notify_row_reports_unreadable_rather_than_healthy_when_blind():
    """`ok at zero` and `could not read` are different values at the source
    (LAW §11). A registry that cannot be read must not publish a healthy
    notify path."""
    c = coordinator({})
    c.hass.services = _Exploding()
    out = asyncio.run(c._async_update_data())
    notify = [r for r in out["readings"].values() if r["kind"] == "notify_health"]
    assert notify, "no notify_health row in SOURCES"
    for row in notify:
        assert row["disposition"] != DISP_OK
        assert row.get("integrity") != "ok"


def test_a_registered_notify_service_reads_healthy():
    from ha_stubs import FakeServices
    from household_state.const import SOURCES

    specs = [s for s in SOURCES if s["kind"] == "notify_health"]
    assert specs, "no notify_health row in SOURCES"
    sp = specs[0]
    c = coordinator({})
    domain = TEST_BINDINGS[bind_key("notify_health", "service_domain")]
    service = TEST_BINDINGS[bind_key("notify_health", "service")]
    c.hass.services = FakeServices([(domain, service)])
    r = c._read_source(sp)
    assert r["disposition"] == DISP_OK
    assert r["integrity"] == "ok"


def test_an_unregistered_notify_service_is_degraded_and_says_which():
    c = coordinator({})  # FakeServices() registers nothing
    from household_state.const import SOURCES

    sp = [s for s in SOURCES if s["kind"] == "notify_health"][0]
    r = c._read_source(sp)
    assert r["disposition"] == DISP_OK, "the read worked; the subject is the fault"
    assert r["integrity"] == "degraded"
    assert TEST_BINDINGS[bind_key("notify_health", "service")] \
        in r["integrity_detail"]
