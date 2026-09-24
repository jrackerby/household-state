"""banner.py says what ha-dashboard-kit's directive.ts said, case for case.

THE ORACLE IS THE KIT. tests/fixtures/banner_parity.json is what the kit's
own `directiveNow()` rendered for every state map its preview harness,
design-sync previews and unit suite draw, recorded at the commit the file
names by tools/banner_parity_fixture.ts. A port proven by reading two files
side by side is proven by nobody; this file replays the kit's own fixtures
through the port and compares the rendered cell — text, tone, driver,
status line — field by field.

WHAT THE CONVERTER DOES, AND WHY IT IS ALLOWED TO. The kit read three
PUBLISHED entities plus the driver's own SourceSensor; banner.py reads the
coordinator's internal shape. The bridge below turns a kit state map into
that shape — the driver key off the kit's driver token, the open ids and
the dwell off the source's `detail` string exactly as hazard.ts parsed it.
That parsing is test plumbing standing in for the coordinator, which
carries the same facts structured (`ids`, `open_seconds`).

THE MASK IS PROVEN THE SAME WAY, AND IT DIVERGES ON PURPOSE. `party.ts`
(kit GH-198) landed after the first recording — kit c6fea2a carried no such
file — so the fixture was regenerated at the kit commit it now names, with
the party macro on across the axes. Where the party masks, the kit rendered
nothing and left the stage word, the hazard and the status line computed
underneath, unreachable because the banner returned null; the port states
nothing at all instead, because an attribute can be read by a surface the
kit never had. The two are compared on what a surface could reach, and the
port's stricter silence is asserted on its own.

ONE KIT CASE IS DELIBERATELY NOT HERE: the pre-0.8.0 perimeter detail shape
(`<id> +2 more open over 300s`), which hazard.ts still accepted because a
wall can run a kit and a component from different weeks. This module IS the
component, and the component has named every opening since 0.8.0, so there
is no skew for it to bridge.
"""

import json
import pathlib
import re

import pytest

from household_state.banner import resolve_banner

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "banner_parity.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))

STAGE = "sensor.household_state_stage"
DIRECTIVE = "sensor.household_state_directive"
QUIET = "binary_sensor.household_state_quiet"
# The kit's party macro (`party.ts`, kit GH-198). It is a macro state of
# this component's own — `binary_sensor.household_state_party` — and the
# bridge below hands it to the port the way the coordinator does: as a macro
# slug that declares `masks`.
PARTY = "binary_sensor.household_state_party"

# The kit's driver token -> (SOURCES key, kind, row name, source entity). The
# token is the PUBLISHED slug (nws_example is a #19 slug override of
# local_nws on the estate the kit was written against).
KIT_DRIVERS = {
    "nws_example": ("local_nws", "severity_attr", "Local NWS", "sensor.household_state_nws_example"),
    "ntas": ("ntas", "severity_attr", "NTAS Advisory", "sensor.household_state_ntas_advisory"),
    "space_weather": ("space_weather", "severity_attr", "Space Weather",
                      "sensor.household_state_space_weather"),
    "alarm": ("alarm", "alarm", "Alarm", "sensor.household_state_alarm"),
    "perimeter_open": ("perimeter_open", "perimeter", "Perimeter Open, Sustained",
                       "sensor.household_state_perimeter_open_sustained"),
}

# hazard.ts's own three parsers, for the bridge only.
_ENTITY_ID = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")


def _ids(text):
    return [t.strip() for t in text.split(",") if _ENTITY_ID.match(t.strip())]


def _alarm_ids(detail):
    m = re.search(r"\bopen:\s*(.+)$", detail.strip())
    return _ids(m.group(1)) if m else []


def _perimeter(detail):
    m = re.match(r"^(.+?)\s+open over (\d+)s$", detail.strip())
    if not m:
        return [], None
    head = re.sub(r"\s\+\d+\s+more$", "", m.group(1))
    ids = _ids(head)
    return (ids, int(m.group(2))) if ids else ([], None)


def _driver_reading(states):
    """The coordinator reading for the row STAGE names, off the kit map."""
    token = (states.get(STAGE) or {}).get("attributes", {}).get("driver")
    if not token:
        return None
    if token not in KIT_DRIVERS:
        # A driver the kit had never heard of: no source to read, no label,
        # no name. The coordinator can never produce this (every driver is
        # a SOURCES row) but the kit's own fixtures draw it, and the port
        # must degrade the same way — to the cell's own text.
        return {"key": token, "slug": token, "kind": "unknown", "name": None,
                "raw_state": None, "detail": None}
    key, kind, name, source_id = KIT_DRIVERS[token]
    src = states.get(source_id) or {"attributes": {}}
    raw = src["attributes"].get("raw_state")
    detail = src["attributes"].get("detail") or ""
    reading = {"key": key, "slug": token, "kind": kind, "name": name,
               "raw_state": raw, "detail": detail or None}
    if kind == "alarm":
        reading["ids"] = _alarm_ids(detail)
    if kind == "perimeter":
        reading["ids"], reading["open_seconds"] = _perimeter(detail)
    return reading


def _port(states):
    def helper_text(cell, suffix):
        st = states.get("input_text.directive_" + cell + "_" + suffix)
        return None if st is None else st["state"]

    def names_of(eid):
        st = states.get(eid)
        return None if st is None else st["attributes"].get("friendly_name")

    stage = states.get(STAGE)
    directive = states.get(DIRECTIVE)
    quiet = states.get(QUIET)
    return resolve_banner(
        stage=None if stage is None else stage["state"],
        directive=None if directive is None else directive["state"],
        quiet=quiet is not None and quiet["state"] == "on",
        driver=_driver_reading(states),
        stage_detail=None if stage is None else stage["attributes"].get("detail"),
        helper_text=helper_text,
        names_of=names_of,
        # hazard.ts named the county in its fallback line; the port binds it.
        jurisdiction="Union County",
        masked_by="party" if _party_on(states) else None,
    )


def _party_on(states):
    st = states.get(PARTY)
    return st is not None and st["state"] == "on"


COMPARED = (
    "cell", "imperative", "action", "tone", "evacuate", "stage_word", "stage_on",
    "stage_tone", "quiet", "hazard_source", "hazard_name", "hazard_window", "status",
)

# THE MASKED CASES ARE COMPARED ON WHAT A SURFACE COULD REACH, AND THE
# DIVERGENCE IS THE POINT (#30). With the party on and no evacuation, the
# kit's banner rendered NOTHING — `cell: null` returned before a word of it
# reached the screen — and everything it had computed underneath (the stage
# word it substituted to `normal`, the hazard, the status line) was
# unreachable by construction. An attribute has no such floor: whatever
# banner.py publishes can be read by a surface written next year. So the port
# states nothing at all, and the fields below are the ones both agree on:
# nothing mounts, and the stage pill is off.
MASKED_COMPARED = ("cell", "evacuate", "stage_on", "quiet")

# What the port publishes instead of the kit's unreachable leftovers.
MASKED_SILENCE = {
    "cell": None, "gate": "none", "imperative": "", "action": "",
    "stage_word": None, "stage_on": False, "stage_tone": None,
    "status": [], "hazard_driver": None, "hazard_source": None,
    "hazard_name": None, "hazard_window": None,
    "masked": True, "masked_by": "party",
}


def test_the_fixture_names_the_kit_commit_it_was_recorded_at():
    assert re.fullmatch(r"[0-9a-f]{40}", DATA["kit_commit"])
    assert len(DATA["cases"]) >= 50


def _masked(expected):
    """The kit's own verdict for a case: the party macro is on and the
    directive is not an evacuation. Read off what the kit recorded, never
    re-derived here — the oracle decides which cases it masked."""
    return bool(expected.get("party")) and not expected["evacuate"]


@pytest.mark.parametrize("case", DATA["cases"], ids=[c["title"] for c in DATA["cases"]])
def test_the_port_renders_what_the_kit_rendered(case):
    got = _port(case["states"])
    want = case["expected"]
    compared = MASKED_COMPARED if _masked(want) else COMPARED
    diff = {k: (want[k], got[k]) for k in compared if want[k] != got[k]}
    assert not diff, diff
    if not _masked(want):
        assert got["masked"] is False and got["masked_by"] is None


@pytest.mark.parametrize(
    "case",
    [c for c in DATA["cases"] if _masked(c["expected"])],
    ids=[c["title"] for c in DATA["cases"] if _masked(c["expected"])],
)
def test_a_masked_case_states_nothing_at_all(case):
    """The half the kit had no oracle for, because it never needed one: the
    published cell is empty in every field, not merely unrendered."""
    got = _port(case["states"])
    assert {k: got[k] for k in MASKED_SILENCE} == MASKED_SILENCE


def test_the_fixture_carries_masked_cases_on_both_sides_of_the_exception():
    """A mask proven only where it fires proves half a rule."""
    masked = [c for c in DATA["cases"] if _masked(c["expected"])]
    evacuations = [
        c for c in DATA["cases"]
        if c["expected"].get("party") and c["expected"]["evacuate"]
    ]
    assert len(masked) >= 5 and len(evacuations) >= 2
    for case in evacuations:
        got = _port(case["states"])
        assert got["cell"] == "evacuate" and got["gate"] == "evacuate"
        assert got["masked"] is False and got["masked_by"] is None


def test_the_comparison_can_fail():
    """A parity check that could not fail is a parity check that proves
    nothing: the same bridge with the stage word swapped must diverge."""
    case = next(c for c in DATA["cases"] if c["expected"]["cell"] == "alert")
    states = json.loads(json.dumps(case["states"]))
    states[STAGE]["state"] = "critical"
    got = _port(states)
    assert got["cell"] != case["expected"]["cell"]
    assert got["stage_word"] != case["expected"]["stage_word"]
