"""resolve() — the whole axis resolution, exercised directly.

That is what makes this function testable: the resolver imports nothing from
homeassistant, so the conflict table can be run against it with no live
state and no restart. "A resolver that can only be exercised by moving the
real world is a resolver that never gets exercised" (resolver.py's own
docstring).

It was at 50% when this repo was gap-listed, with resolve() itself entirely
uncovered — the safety-directive path was the least exercised code in the
repo. The existing suites reach resolve_directive, band_for and stage_for;
this one reaches the function that combines them and holds RULE 2.
"""

import pytest

from household_state.const import (
    AXIS_DIRECTIVE,
    AXIS_INTEGRITY,
    AXIS_STAGE,
    BAND_CLEAR,
    BAND_CRITICAL,
    BAND_ELEVATED,
    BAND_UNKNOWN,
    DISP_ABSENT,
    DISP_OK,
    DISP_UNKNOWN,
    INTEGRITY_DEGRADED,
    INTEGRITY_OK,
    INTEGRITY_UNKNOWN,
    STAGE_CRITICAL,
    STAGE_ELEVATED,
    STAGE_NORMAL,
    STAGE_UNKNOWN,
)
from household_state.resolver import alarm_severity, resolve


def stage(key, severity, disposition=DISP_OK, detail=None, raw_state=None, name=None):
    return {
        "key": key,
        "name": name or key.replace("_", " ").title(),
        "axis": AXIS_STAGE,
        "disposition": disposition,
        "severity": severity,
        "raw_state": raw_state,
        "detail": detail,
    }


def integrity(key, disposition=DISP_OK, verdict=INTEGRITY_OK, detail=None,
              affected=None, name=None):
    row = {
        "key": key,
        "name": name or key.replace("_", " ").title(),
        "axis": AXIS_INTEGRITY,
        "disposition": disposition,
        "severity": None,
        "raw_state": None,
        "detail": None,
        "integrity": verdict,
    }
    if detail is not None:
        row["integrity_detail"] = detail
    if affected is not None:
        row["affected"] = affected
    return row


# ============================================================ STAGE, RULE 2

def test_all_healthy_and_idle_is_normal():
    out = resolve([stage("alarm", 0), stage("local_nws", 0)])
    assert out["severity"] == 0
    assert out["stage"] == STAGE_NORMAL
    assert out["band"] == BAND_CLEAR
    assert out["confidence"] == "full"


def test_an_unhealthy_source_can_never_contribute_zero():
    """RULE 2, the whole reason resolve() exists. Healthy sources are idle but
    we cannot see all of them, so we do not get to say Normal."""
    out = resolve([
        stage("alarm", 0),
        stage("local_nws", None, disposition=DISP_UNKNOWN),
    ])
    assert out["severity"] is None
    assert out["stage"] == STAGE_UNKNOWN
    assert out["band"] == BAND_UNKNOWN
    assert out["confidence"] == "none"


def test_unknown_is_not_normal_and_never_clear():
    """unknown is not Normal and never green."""
    out = resolve([stage("alarm", None, disposition=DISP_ABSENT)])
    assert out["stage"] != STAGE_NORMAL
    assert out["band"] != BAND_CLEAR
    assert out["band"] == BAND_UNKNOWN


def test_no_rows_at_all_is_normal_not_unknown():
    """Nothing unreadable means nothing is being hidden. An empty source set is
    a configuration question, not a reading."""
    out = resolve([])
    assert out["severity"] == 0
    assert out["confidence"] == "full"
    assert out["sources_total"] == 0


def test_a_positive_severity_survives_a_partial_source_set():
    """A positive reading from a partial set is still actionable — it just is
    not a complete picture, and confidence says so rather than withholding it."""
    out = resolve([
        stage("alarm", 6),
        stage("local_nws", None, disposition=DISP_UNKNOWN),
    ])
    assert out["severity"] == 6
    assert out["stage"] == STAGE_CRITICAL
    assert out["confidence"] == "partial"
    assert out["sources_unhealthy"] == ["local_nws"]


def test_the_highest_healthy_severity_wins():
    out = resolve([stage("alarm", 2), stage("local_nws", 5), stage("ntas", 1)])
    assert out["severity"] == 5
    assert out["driver"] == "local_nws"


def test_a_tie_is_broken_by_tiebreak_order_not_by_input_order():
    """TIEBREAK is alarm, perimeter_open, nws_union, ntas, space_weather. The
    rows are fed in the opposite order to prove the resolver is not simply
    taking the first thing it sees."""
    out = resolve([stage("space_weather", 4), stage("ntas", 4), stage("alarm", 4)])
    assert out["driver"] == "alarm"


def test_a_source_outside_tiebreak_is_not_scored():
    """The loop walks TIEBREAK, so an unlisted key contributes nothing. That is
    how a new SOURCES row silently fails to reach STAGE — worth pinning."""
    out = resolve([stage("not_in_tiebreak", 7)])
    assert out["severity"] == 0
    assert out["driver"] is None


def test_nothing_is_named_at_zero():
    """name nothing at zero. A driver at severity 0 is a name with no
    finding behind it."""
    out = resolve([stage("alarm", 0), stage("local_nws", 0)])
    assert out["driver"] is None
    assert out["detail"] == "no active local, state, weather, or perimeter threats"


def test_the_unresolvable_detail_counts_what_it_could_not_read():
    out = resolve([
        stage("alarm", None, disposition=DISP_UNKNOWN),
        stage("local_nws", None, disposition=DISP_ABSENT),
        stage("ntas", 0),
    ])
    assert out["driver"] is None
    assert out["detail"] == "cannot resolve stage: 2 of 3 sources unreadable"


def test_the_driver_detail_falls_back_to_raw_state():
    out = resolve([stage("alarm", 7, detail=None, raw_state="triggered")])
    assert out["detail"] == "triggered"


def test_detail_is_preferred_over_raw_state():
    out = resolve([stage("alarm", 7, detail="Front Door", raw_state="triggered")])
    assert out["detail"] == "Front Door"


@pytest.mark.parametrize("severity,expected_stage,expected_band", [
    (0, STAGE_NORMAL, BAND_CLEAR),
    (1, STAGE_ELEVATED, BAND_ELEVATED),
    (4, STAGE_ELEVATED, BAND_ELEVATED),
    (5, STAGE_CRITICAL, BAND_CRITICAL),
    (7, STAGE_CRITICAL, BAND_CRITICAL),
])
def test_the_band_boundaries(severity, expected_stage, expected_band):
    out = resolve([stage("alarm", severity)])
    assert out["stage"] == expected_stage
    assert out["band"] == expected_band


def test_a_healthy_row_carrying_no_severity_is_skipped_not_scored_as_zero():
    """`severity is None` on a healthy row means the row has nothing to say,
    which is not the same as saying nought."""
    out = resolve([stage("alarm", None), stage("local_nws", 3)])
    assert out["severity"] == 3
    assert out["driver"] == "local_nws"


# ============================================================== INTEGRITY

def test_integrity_defaults_to_ok_with_no_rows():
    out = resolve([stage("alarm", 0)])
    assert out["integrity"] == INTEGRITY_OK
    assert out["integrity_detail"] == "all monitoring paths healthy"
    assert out["integrity_driver"] is None
    assert out["integrity_affected"] == 0


def test_a_degraded_row_moves_integrity():
    out = resolve([integrity("fls", verdict=INTEGRITY_DEGRADED,
                             detail="2 detectors offline", affected=2)])
    assert out["integrity"] == INTEGRITY_DEGRADED
    assert out["integrity_driver"] == "fls"
    assert out["integrity_detail"] == "2 detectors offline"
    assert out["integrity_affected"] == 2


def test_the_axis_gathers_what_every_readable_row_suppressed():
    """#26: a declined signal is stated on the axis too, always as a list.
    An unreadable row's declined set is not gathered — a verdict computed
    from a failed read is not a verdict, and neither is its exclusion."""
    ok_row = integrity("cfg", verdict=INTEGRITY_OK)
    ok_row["suppressed"] = ["Main Bed LGTV (webostv)", "Family Room LGTV (webostv)"]
    dead_row = integrity("net", verdict=INTEGRITY_OK)
    dead_row["disposition"] = DISP_UNKNOWN
    dead_row["suppressed"] = ["never gathered"]
    out = resolve([ok_row, dead_row])
    assert out["integrity_suppressed"] == [
        "Main Bed LGTV (webostv)", "Family Room LGTV (webostv)"
    ]
    assert resolve([stage("alarm", 0)])["integrity_suppressed"] == []


def test_unknown_outranks_degraded():
    """On this axis `unknown` is first-class and OUTRANKS `degraded`. A verdict
    computed from a failed read is not a verdict."""
    out = resolve([
        integrity("fls", verdict=INTEGRITY_DEGRADED, detail="2 offline", affected=2),
        integrity("net", disposition=DISP_UNKNOWN),
    ])
    assert out["integrity"] == INTEGRITY_UNKNOWN
    assert out["integrity_driver"] == "net"
    assert out["integrity_detail"] == "cannot read 1 integrity source(s)"
    assert out["integrity_affected"] == 1


def test_affected_counts_sum_across_every_degraded_row():
    out = resolve([
        integrity("fls", verdict=INTEGRITY_DEGRADED, affected=2),
        integrity("sec", verdict=INTEGRITY_DEGRADED, affected=3),
    ])
    assert out["integrity_affected"] == 5


def test_a_degraded_row_with_no_detail_still_says_something():
    out = resolve([integrity("fls", verdict=INTEGRITY_DEGRADED)])
    assert out["integrity_detail"] == "degraded"


def test_integrity_never_moves_stage():
    """The inversion this component was built to remove. INTEGRITY addresses
    the operator; STAGE addresses the household. They are different audiences,
    not different intensities."""
    clean = resolve([stage("alarm", 0)])
    with_fault = resolve([
        stage("alarm", 0),
        integrity("net", disposition=DISP_UNKNOWN),
    ])
    assert with_fault["severity"] == clean["severity"] == 0
    assert with_fault["stage"] == clean["stage"] == STAGE_NORMAL
    assert with_fault["confidence"] == clean["confidence"] == "full"
    assert with_fault["integrity"] == INTEGRITY_UNKNOWN


def test_there_is_no_severity_key_on_the_integrity_axis():
    """RULE 4. A severity here would be suppressed by Critical, which is the
    exact inversion this component exists to remove. If a future edit adds one,
    that edit is reintroducing the bug."""
    out = resolve([integrity("fls", verdict=INTEGRITY_DEGRADED)])
    assert "integrity_severity" not in out


# ------------------------------------------------ the per-source breakdown

def test_every_integrity_row_appears_in_the_breakdown_not_just_the_driver():
    """The aggregate axis needs one driver to decide; an operator reading the
    card needs to see all of them."""
    out = resolve([
        integrity("fls", verdict=INTEGRITY_DEGRADED, detail="2 offline", name="FLS"),
        integrity("sec", verdict=INTEGRITY_OK, detail="ok", name="Security"),
        integrity("net", disposition=DISP_UNKNOWN, name="Networking"),
    ])
    rows = out["integrity_sources_detail"].split("\n")
    assert len(rows) == 3
    assert rows[0] == "FLS~degraded~2 offline"
    assert rows[1] == "Security~ok~ok"
    assert rows[2] == "Networking~unreadable~monitor unavailable"


def test_a_detail_containing_the_internal_pipe_separator_survives_intact():
    """a value joined into a delimited channel must not be able to
    contain the delimiter. `detail` bodies use " | " as their OWN part
    separator throughout this codebase, so a pipe-joined row separator would
    tear one multi-part detail into two rows."""
    out = resolve([integrity("net", verdict=INTEGRITY_DEGRADED,
                             detail="Spectrum: no WAN latency | uplink flapping",
                             name="Networking")])
    rows = out["integrity_sources_detail"].split("\n")
    assert len(rows) == 1
    assert rows[0] == "Networking~degraded~Spectrum: no WAN latency | uplink flapping"


def test_an_ok_row_with_no_detail_reads_ok_and_a_non_ok_one_says_so():
    out = resolve([
        integrity("a", verdict=INTEGRITY_OK, name="A"),
        integrity("b", verdict=INTEGRITY_DEGRADED, name="B"),
    ])
    rows = out["integrity_sources_detail"].split("\n")
    assert rows[0] == "A~ok~ok"
    assert rows[1] == "B~degraded~no detail reported"


def test_the_stage_detail_is_not_overwritten_by_the_breakdown_loop():
    """Python has no block scoping, and a first draft of the breakdown used
    bare `detail`/`state`, so the STAGE sensor's own detail came back reading
    the last integrity row's text. Caught live, not by inspection."""
    out = resolve([
        stage("alarm", 0),
        integrity("net", verdict=INTEGRITY_DEGRADED, detail="Spectrum down",
                  name="Networking"),
    ])
    assert out["detail"] == "no active local, state, weather, or perimeter threats"
    assert "Spectrum down" in out["integrity_sources_detail"]


# ================================================================== COUNTS

def test_the_counts_describe_only_their_own_axis():
    out = resolve([
        stage("alarm", 0),
        stage("local_nws", None, disposition=DISP_UNKNOWN),
        integrity("fls", verdict=INTEGRITY_OK),
        {"key": "cap", "name": "CAP", "axis": AXIS_DIRECTIVE,
         "disposition": DISP_OK, "severity": None, "raw_state": None,
         "detail": None, "pairs": []},
    ])
    assert out["sources_total"] == 2
    assert out["sources_healthy"] == 1
    assert out["sources_unhealthy"] == ["local_nws"]
    assert out["integrity_sources"] == 1
    assert out["directive_sources"] == 1


# =========================================================== alarm ladder

@pytest.mark.parametrize("state", ["armed_home", "armed_away", "armed_night",
                                   "armed_vacation"])
def test_armed_with_something_open_escalates(state):
    assert alarm_severity(state, ["binary_sensor.front_door"]) == 6


@pytest.mark.parametrize("state", ["armed_home", "armed_away", "armed_night",
                                   "armed_vacation"])
def test_armed_and_closed_is_idle(state):
    assert alarm_severity(state, []) == 0


def test_triggered_outranks_everything():
    assert alarm_severity("triggered", []) == 7


@pytest.mark.parametrize("state", ["disarmed", "arming", "pending", "unknown", ""])
def test_states_that_do_not_escalate(state):
    assert alarm_severity(state, ["binary_sensor.front_door"]) == 0


# ================================================================ self-test

def test_the_assertions_can_fail():
    """every assertion set needs a self-test proving it CAN fail."""
    # RULE 2 must actually depend on the unhealthy row being there.
    assert resolve([stage("alarm", 0)])["severity"] == 0
    assert resolve([
        stage("alarm", 0), stage("local_nws", None, disposition=DISP_UNKNOWN)
    ])["severity"] is None
    # The tiebreak must actually depend on TIEBREAK order, not input order.
    assert resolve([stage("ntas", 4), stage("alarm", 4)])["driver"] == "alarm"
    assert resolve([stage("alarm", 4), stage("ntas", 4)])["driver"] == "alarm"
    # And a genuinely higher severity must beat the tiebreak.
    assert resolve([stage("alarm", 4), stage("ntas", 5)])["driver"] == "ntas"
