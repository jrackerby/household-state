"""GH-583: `boil_water` is a directive, and it is the WEAKEST one.

Joel's ruling: elevating a banner without saying "boil it" is half a surface,
so the water advisory produces an instruction and not just a stage bump. That
made `boil_water` the fourth word on an axis that had three, and the first one
that is not about where the household should BE.

WHAT THIS SUITE IS ACTUALLY FOR: precedence. A boil-water advisory and a
tornado warning can be true at the same time, and on that day the instruction
row must say "go to the main closet". Water you have to boil is not a reason
to leave the closet. Every combination below exists to pin that ordering, in
both directions, because the failure is silent -- a wrong precedence renders a
perfectly formatted instruction that is the wrong instruction.

Self-test discipline (LAW 4): FAIL_CASES assert deliberately WRONG outcomes on
real inputs and main() proves each one fails before any PASS is trusted.
"""

import sys

if __name__ == "__main__" and "household_state" not in sys.modules:
    import atexit
    import shutil
    import tempfile
    from pathlib import Path

    _root = Path(__file__).resolve().parent.parent
    _stage = Path(tempfile.mkdtemp(prefix="household_state_test_"))
    atexit.register(shutil.rmtree, _stage, True)
    (_stage / "household_state").symlink_to(_root, target_is_directory=True)
    sys.path.insert(0, str(_stage))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import ha_stubs  # noqa: E402

ha_stubs.install()

from household_state.const import (  # noqa: E402
    DIRECTIVE_BOIL_WATER,
    DIRECTIVE_EVACUATE,
    DIRECTIVE_NULL,
    DIRECTIVE_SECURE,
    DIRECTIVE_SHELTER,
    DIRECTIVE_UNKNOWN,
    DISP_OK,
    DISP_UNREACHABLE,
)
from household_state.resolver import resolve_directive  # noqa: E402


def hazard(on, disposition=DISP_OK):
    """The boil-water row as the coordinator would hand it over."""
    return {
        "key": "boil_water_directive",
        "name": "Boil Water Advisory",
        "kind": "binary_hazard",
        "disposition": disposition,
        "severity": 4 if on else 0,
        "directive_when_on": DIRECTIVE_BOIL_WATER,
    }


def cap(*responses, disposition=DISP_OK, event="Test Alert"):
    return {
        "key": "cap",
        "name": "CAP",
        "kind": "cap",
        "disposition": disposition,
        "pairs": [{"response": r, "event": event} for r in responses],
    }


def d(rows):
    return resolve_directive(rows)[0]


def reason(rows):
    return resolve_directive(rows)[1]


CASES = [
    # ---- the advisory alone -----------------------------------------
    ("advisory alone -> boil_water",
     lambda: d([hazard(True)]), DIRECTIVE_BOIL_WATER),
    ("advisory alone names its source as the driver",
     lambda: resolve_directive([hazard(True)])[2], "Boil Water Advisory"),
    ("advisory alone carries a non-CAP reason",
     lambda: reason([hazard(True)]), "hazard_source"),
    ("no advisory, no CAP rows -> unknown, not none",
     lambda: d([hazard(False)]), DIRECTIVE_UNKNOWN),

    # ---- alongside a quiet CAP source -------------------------------
    ("advisory + CAP with nothing to say -> boil_water",
     lambda: d([hazard(True), cap("Monitor")]), DIRECTIVE_BOIL_WATER),
    ("no advisory + CAP with nothing to say -> none",
     lambda: d([hazard(False), cap("Monitor")]), DIRECTIVE_NULL),

    # ---- PRECEDENCE: the whole point of this file --------------------
    ("shelter OUTRANKS boil_water",
     lambda: d([hazard(True), cap("Shelter")]), DIRECTIVE_SHELTER),
    ("evacuate OUTRANKS boil_water",
     lambda: d([hazard(True), cap("Evacuate")]), DIRECTIVE_EVACUATE),
    # `secure` is reachable only through the EVENT-NAME classifier:
    # DIRECTIVE_RESPONSE_MAP carries Shelter and Evacuate and nothing else.
    # The first draft of this case used a responseType and the self-test
    # caught it -- the fixture was wrong, not the precedence.
    ("secure OUTRANKS boil_water",
     lambda: d([hazard(True), cap(None, event="Law Enforcement Warning")]),
     DIRECTIVE_SECURE),
    ("boil_water does not suppress a co-active shelter's driver",
     lambda: resolve_directive([hazard(True), cap("Shelter")])[2], "Test Alert"),
    ("order of rows does not change precedence",
     lambda: d([cap("Shelter"), hazard(True)]), DIRECTIVE_SHELTER),

    # ---- unreadable is not clear ------------------------------------
    ("unreadable advisory + quiet CAP -> unknown, never none",
     lambda: d([hazard(False, DISP_UNREACHABLE), cap("Monitor")]),
     DIRECTIVE_UNKNOWN),
    ("unreadable advisory never blocks a shelter we CAN see",
     lambda: d([hazard(False, DISP_UNREACHABLE), cap("Shelter")]),
     DIRECTIVE_SHELTER),
    ("unreadable CAP never blocks an advisory we CAN see",
     lambda: d([hazard(True), cap("Shelter", disposition=DISP_UNREACHABLE)]),
     DIRECTIVE_BOIL_WATER),

    # ---- the pre-existing CAP contract is intact ---------------------
    ("CAP-only shelter still resolves",
     lambda: d([cap("Shelter")]), DIRECTIVE_SHELTER),
    ("CAP-only evacuate still resolves",
     lambda: d([cap("Evacuate")]), DIRECTIVE_EVACUATE),
    ("no rows at all is still unknown",
     lambda: d([]), DIRECTIVE_UNKNOWN),
]

FAIL_CASES = [
    ("boil_water must not outrank shelter",
     lambda: d([hazard(True), cap("Shelter")]), DIRECTIVE_BOIL_WATER),
    ("boil_water must not outrank evacuate",
     lambda: d([hazard(True), cap("Evacuate")]), DIRECTIVE_BOIL_WATER),
    ("boil_water must not outrank secure",
     lambda: d([hazard(True), cap(None, event="Law Enforcement Warning")]),
     DIRECTIVE_BOIL_WATER),
    ("an active advisory must not resolve to none",
     lambda: d([hazard(True)]), DIRECTIVE_NULL),
    ("an unreadable advisory must not resolve to none",
     lambda: d([hazard(False, DISP_UNREACHABLE), cap("Monitor")]),
     DIRECTIVE_NULL),
    ("a quiet CAP source must not be turned into boil_water",
     lambda: d([hazard(False), cap("Monitor")]), DIRECTIVE_BOIL_WATER),
    ("shelter must not be downgraded by row order",
     lambda: d([cap("Shelter"), hazard(True)]), DIRECTIVE_BOIL_WATER),
]


def _run(case):
    label, fn, expected = case
    try:
        got = fn()
    except Exception as exc:  # noqa: BLE001
        return False, f"raised {type(exc).__name__}: {exc}"
    return got == expected, f"got {got!r}, expected {expected!r}"


def main():
    print("=" * 70)
    print("SELF-TEST: proving the suite can fail")
    print("=" * 70)
    broken = []
    for case in FAIL_CASES:
        passed, detail = _run(case)
        if passed:
            broken.append(case[0])
            print(f"  BROKEN   {case[0]} -- passed but must not ({detail})")
        else:
            print(f"  fails ok {case[0]}")
    if broken:
        print(f"\nSELF-TEST FAILED: {len(broken)} wrong assertion(s) passed.")
        return 1
    print(f"\nself-test OK: all {len(FAIL_CASES)} wrong assertions failed\n")

    print("=" * 70)
    print("ASSERTIONS")
    print("=" * 70)
    failures = []
    for case in CASES:
        passed, detail = _run(case)
        print(f"  {'PASS' if passed else 'FAIL'} {case[0]}"
              + ("" if passed else f" -- {detail}"))
        if not passed:
            failures.append(case[0])
    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} passed")
    return 1 if failures else 0


def test_boil_water_directive():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
