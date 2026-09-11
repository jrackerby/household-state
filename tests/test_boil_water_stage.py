"""GH-583: a boil-water advisory covering this address moves STAGE.

BOTH AXES, one entity. The STAGE row elevates the house and names the driver;
a SECOND row on the same entity produces the INSTRUCTION, because "boil your
water" is a thing to do and the directive axis is where things to do live.
Two rows sharing an entity is §7.3's existing shape (sensor.fls_device_status)
rather than a duplicate.

This suite originally asserted the directive axis had exactly ONE source,
because the first cut shipped STAGE-only on the argument that adding a fourth
directive word was a ruling. It was -- and Joel made it. That assertion is now
inverted rather than deleted, so the file records the reversal instead of
quietly agreeing with whatever the code currently does.

THE LOAD-BEARING CASE IS `unavailable`. The producing entity goes unavailable
when the advisory table cannot be read or the feed goes stale, rather than
answering `off`. That must reach the resolver as severity None with a
non-OK disposition -- never severity 0. Substituting 0 for "could not read"
is KAN-139, and here it would mean a wall reading a calm house because the
water utility's website was down.

Self-test discipline (LAW 4): FAIL_CASES assert deliberately WRONG outcomes on
real inputs, and main() proves every one of them fails before any PASS below
is trusted.
"""

import sys  # noqa: E402

# conftest.py stages the repo as an importable `household_state` package, but
# only pytest loads conftest. Replicate it when run directly, so this suite is
# usable at a shell the way tools/test_*.py in jrackerby/HA are.
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
    AXIS_STAGE,
    BOIL_ADVISORY_SEV,
    DISP_OK,
    DISP_UNKNOWN,
    DISP_UNPARSED,
    DISP_UNREACHABLE,
    SOURCES,
    STAGE_ELEVATED,
    STAGE_NORMAL,
)
from household_state.resolver import band_for, stage_for  # noqa: E402

ROW = next(s for s in SOURCES if s["key"] == "boil_water")


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


def read(state):
    """Run the REAL coordinator read for this row against a stubbed state."""
    from household_state.coordinator import HouseholdStateCoordinator as C

    mapping = {} if state is None else {ROW["entity_id"]: _State(state)}
    inst = C.__new__(C)
    inst.hass = _Hass(mapping)
    inst._warn_once = lambda *a, **k: None
    # GH #16: _read_source resolves its entity through the binding map, so a
    # hand-built instance carries one. Empty means "no override", which is
    # what every case here wants: the SOURCES row's own default.
    inst._bindings = {}
    return C._read_source(inst, ROW)


# (label, callable, expected)
CASES = [
    # ---- wiring -----------------------------------------------------
    ("row is on the STAGE axis, not DIRECTIVE",
     lambda: ROW["axis"], AXIS_STAGE),
    ("row reads the address-matched entity, not the system-wide one",
     lambda: ROW["entity_id"],
     "binary_sensor.ucw_boil_water_advisory_affects_home"),
    ("directive axis now carries CAP plus this one hazard source",
     lambda: len([s for s in SOURCES if s["axis"] == "directive"]), 2),
    ("the hazard directive row names the same entity as the stage row",
     lambda: next(s for s in SOURCES if s["key"] == "boil_water_directive")
     ["entity_id"], ROW["entity_id"]),

    # ---- severity ---------------------------------------------------
    ("advisory on -> configured severity",
     lambda: read("on")["severity"], BOIL_ADVISORY_SEV),
    ("advisory on -> elevated, never critical on its own",
     lambda: stage_for(read("on")["severity"]), STAGE_ELEVATED),
    ("advisory on is inside the elevated band",
     lambda: band_for(BOIL_ADVISORY_SEV), band_for(4)),
    ("advisory on outranks perimeter-open, so it is named as driver",
     lambda: BOIL_ADVISORY_SEV > 2, True),
    ("advisory off -> severity 0",
     lambda: read("off")["severity"], 0),
    ("advisory off -> stage normal",
     lambda: stage_for(read("off")["severity"]), STAGE_NORMAL),
    ("advisory on reads a clean disposition",
     lambda: read("on")["disposition"], DISP_OK),

    # ---- THE ONE THAT MATTERS: could-not-read is not clear ----------
    ("unavailable -> severity None, NOT 0",
     lambda: read("unavailable")["severity"], None),
    ("unavailable -> unreachable disposition",
     lambda: read("unavailable")["disposition"], DISP_UNREACHABLE),
    ("unknown -> severity None, NOT 0",
     lambda: read("unknown")["severity"], None),
    ("unknown -> unknown disposition",
     lambda: read("unknown")["disposition"], DISP_UNKNOWN),
    ("entity missing entirely -> severity None",
     lambda: read(None)["severity"], None),
    ("a state this row does not understand is unparsed, not clear",
     lambda: read("maybe")["disposition"], DISP_UNPARSED),
    ("unparsed carries no severity",
     lambda: read("maybe")["severity"], None),
]

# Deliberately WRONG expectations on real inputs. Every one MUST fail.
FAIL_CASES = [
    ("an unreadable advisory must not read as clear",
     lambda: read("unavailable")["severity"], 0),
    ("a stale/unknown advisory must not read as clear",
     lambda: read("unknown")["severity"], 0),
    ("a missing entity must not read as clear",
     lambda: read(None)["severity"], 0),
    ("an active advisory must not read as clear",
     lambda: read("on")["severity"], 0),
    ("an active advisory must not reach the critical band",
     lambda: stage_for(read("on")["severity"]), "critical"),
    ("the STAGE row must not have been moved onto the directive axis",
     lambda: ROW["axis"], "directive"),
    ("an unrecognised state must not resolve OK",
     lambda: read("maybe")["disposition"], DISP_OK),
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
            failures.append((case[0], detail))

    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} passed")
    return 1 if failures else 0


def test_boil_water_stage():
    """pytest entry point; main() is the shell one."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
