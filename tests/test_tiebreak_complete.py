"""Every AXIS_STAGE row reaches STAGE, and nothing else does (#12).

resolve() scores a stage row only if its key appears in TIEBREAK; the
tuple is the list of rows that can move the axis, not merely the order
that names a driver on a tie. boil_water was added to SOURCES with
severity 4 and a comment saying it outranked perimeter-open in the
tiebreak, and it was not in the tuple — so a live advisory covering the
address read 4 on its own sensor and STAGE stayed normal. The suite
already pinned the mechanism (test_a_source_outside_tiebreak_is_not_scored)
without pinning the membership; this does the membership.
"""

from household_state.const import AXIS_STAGE, SOURCES, TIEBREAK
from household_state.resolver import resolve


def _stage_keys():
    return [r["key"] for r in SOURCES if r["axis"] == AXIS_STAGE]


def test_every_stage_row_is_in_tiebreak():
    missing = [k for k in _stage_keys() if k not in TIEBREAK]
    assert missing == [], "stage rows resolve() will never score: " + str(missing)


def test_tiebreak_names_only_stage_rows():
    stray = [k for k in TIEBREAK if k not in _stage_keys()]
    assert stray == [], "TIEBREAK keys with no AXIS_STAGE row: " + str(stray)


def test_tiebreak_has_no_duplicates():
    assert len(TIEBREAK) == len(set(TIEBREAK))


def test_every_stage_row_actually_moves_stage_through_resolve():
    """Membership by behaviour, not by list comparison: each stage row, read
    healthy at severity 3 with every other stage row idle, must be the
    driver resolve() names."""
    for key in _stage_keys():
        rows = []
        for r in SOURCES:
            if r["axis"] != AXIS_STAGE:
                continue
            rows.append({
                "key": r["key"], "axis": AXIS_STAGE, "disposition": "ok",
                "severity": 3 if r["key"] == key else 0,
                "detail": None, "raw_state": None,
            })
        out = resolve(rows)
        assert out["driver"] == key, key + " did not reach STAGE"
        assert out["severity"] == 3
