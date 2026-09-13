"""A person seen by an outside camera overnight moves STAGE (#13).

The row is a binary hazard at the door-left-open level. What is new is
that it NAMES what it saw: the bound sensor carries `cameras`, a list of
the person-detection entity ids that fired, and the row forwards them raw
after "seen: " — the alarm row's "open: " shape — so the wall can say
"Driveway Camera" instead of "someone is outside". Which cameras are
outside, which hours are overnight and how long the finding holds after
the last sighting are the sensor's; this row reads `on`.
"""

from household_state.const import (
    AXIS_STAGE,
    BINDABLE,
    DISP_OK,
    DISP_UNPARSED,
    DISP_UNREACHABLE,
    OUTSIDE_PERSON_SEV,
    PERIMETER_SEV,
    SOURCES,
    STAGE_ELEVATED,
    STAGE_NORMAL,
    TIEBREAK,
)
from household_state.coordinator import HouseholdStateCoordinator as C
from household_state.resolver import resolve, stage_for

ROW = next(s for s in SOURCES if s["key"] == "outside_person")
ENTITY = "binary_sensor.test_outside_person_overnight"
DRIVEWAY = "binary_sensor.driveway_camera_person_detected"
GATE = "binary_sensor.north_gate_camera_person_detected"


class _State:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class _States:
    def __init__(self, mapping):
        self._m = mapping

    def get(self, eid):
        return self._m.get(eid)


class _Hass:
    def __init__(self, mapping):
        self.states = _States(mapping)


def read(state, attributes=None):
    """The REAL coordinator read for this row against a stubbed state."""
    mapping = {} if state is None else {ENTITY: _State(state, attributes)}
    inst = C.__new__(C)
    inst.hass = _Hass(mapping)
    inst._warn_once = lambda *a, **k: None
    inst._bindings = {"outside_person.entity_id": ENTITY}
    return C._read_source(inst, ROW)


# ---------------------------------------------------------------- the row

def test_the_row_is_a_stage_binary_hazard_at_the_door_open_level():
    assert ROW["axis"] == AXIS_STAGE
    assert ROW["kind"] == "binary_hazard"
    assert ROW["severity_when_on"] == OUTSIDE_PERSON_SEV == PERIMETER_SEV
    assert ROW["entity_id"] is None, "which sensor is the installation's, not the row's"


def test_the_row_is_bindable_and_in_tiebreak():
    assert any(k == "outside_person" and f == "entity_id" and d == "binary_sensor"
               for k, f, d, _ in BINDABLE)
    assert "outside_person" in TIEBREAK
    assert TIEBREAK.index("outside_person") < TIEBREAK.index("perimeter_open"), (
        "a person seen is named ahead of a door open when the two tie")


# --------------------------------------------------------------- reading

def test_on_is_the_configured_severity_and_names_the_cameras():
    r = read("on", {"cameras": [GATE, DRIVEWAY]})
    assert r["disposition"] == DISP_OK
    assert r["severity"] == OUTSIDE_PERSON_SEV
    assert stage_for(r["severity"]) == STAGE_ELEVATED
    # sorted, raw, comma-joined — the alarm row's list shape
    assert r["detail"] == "Person Outside Overnight, seen: " + DRIVEWAY + ", " + GATE


def test_on_with_no_camera_list_is_still_on_and_says_only_the_name():
    for attrs in (None, {}, {"cameras": []}, {"cameras": None}):
        r = read("on", attrs)
        assert r["severity"] == OUTSIDE_PERSON_SEV, attrs
        assert r["detail"] == "Person Outside Overnight", attrs


def test_a_string_camera_attribute_is_not_split_into_names():
    """A list that arrived as text is a producer defect; guessing a
    delimiter is how a name gets torn in two."""
    r = read("on", {"cameras": DRIVEWAY + ", " + GATE})
    assert r["severity"] == OUTSIDE_PERSON_SEV
    assert r["detail"] == "Person Outside Overnight"


def test_off_is_zero_and_does_not_borrow_the_boil_water_wording():
    r = read("off")
    assert r["severity"] == 0
    assert stage_for(r["severity"]) == STAGE_NORMAL
    assert r["detail"] == "no person outside overnight"


def test_unavailable_is_none_not_zero():
    r = read("unavailable")
    assert r["disposition"] == DISP_UNREACHABLE
    assert r["severity"] is None


def test_an_unrecognised_state_is_unparsed():
    r = read("maybe")
    assert r["disposition"] == DISP_UNPARSED
    assert r["severity"] is None


def test_the_boil_water_wording_is_unchanged_for_a_row_without_seen_attr():
    boil = next(s for s in SOURCES if s["key"] == "boil_water")
    eid = "binary_sensor.test_boil"
    inst = C.__new__(C)
    inst.hass = _Hass({eid: _State("on")})
    inst._warn_once = lambda *a, **k: None
    inst._bindings = {"boil_water.entity_id": eid}
    assert C._read_source(inst, boil)["detail"] == "Boil Water Advisory in effect for this address"
    inst.hass = _Hass({eid: _State("off")})
    assert C._read_source(inst, boil)["detail"] == "no boil water advisory for this address"


# -------------------------------------------------------------- resolve

def _stage_row(key, severity, detail=None):
    return {"key": key, "axis": AXIS_STAGE, "disposition": DISP_OK,
            "severity": severity, "detail": detail, "raw_state": None}


def test_a_person_outside_elevates_stage_and_is_the_named_driver():
    out = resolve([
        _stage_row("alarm", 0),
        _stage_row("outside_person", OUTSIDE_PERSON_SEV,
                   "Person Outside Overnight, seen: " + DRIVEWAY),
        _stage_row("perimeter_open", 0),
    ])
    assert out["stage"] == STAGE_ELEVATED
    assert out["severity"] == OUTSIDE_PERSON_SEV
    assert out["driver"] == "outside_person"
    assert out["detail"].endswith("seen: " + DRIVEWAY)


def test_a_tie_with_a_door_open_names_the_person():
    out = resolve([
        _stage_row("perimeter_open", PERIMETER_SEV),
        _stage_row("outside_person", OUTSIDE_PERSON_SEV),
    ])
    assert out["driver"] == "outside_person"


def test_the_alarm_still_outranks_it():
    out = resolve([
        _stage_row("alarm", 7),
        _stage_row("outside_person", OUTSIDE_PERSON_SEV),
    ])
    assert out["driver"] == "alarm"


def test_the_row_read_end_to_end_moves_stage():
    """The real read feeding the real resolver, every other stage row idle."""
    rows = [read("on", {"cameras": [DRIVEWAY]})]
    for s in SOURCES:
        if s["axis"] == AXIS_STAGE and s["key"] != "outside_person":
            rows.append(_stage_row(s["key"], 0))
    out = resolve(rows)
    assert out["stage"] == STAGE_ELEVATED
    assert out["driver"] == "outside_person"
