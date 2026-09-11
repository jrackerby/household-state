"""GH-623: the row names WHICH door, not that a door exists.

Joel, 2026-09-06, reading a wall: "'something is left open' is silly. say
which door is left open."

He was reading `hazard.ts`'s wording, but the name was being dropped twice
before it ever got there and only one of those drops was in the kit:

  * the perimeter row published `sustained[0] + " +2 more"`, so every
    opening after the first was UNNAMEABLE at the render boundary no matter
    what the surface did with the string;
  * the alarm row computed its own severity from Alarmo's `open_sensors`
    and then published `"alarm armed_away"`, discarding the very fact that
    promoted it -- a wall saying "armed with something open" while the
    reading in hand knew the door.

Both are the same defect: a row that HOLDS the specific and publishes the
generic. This suite pins that neither can regress to a count.

WHAT IS DELIBERATELY NOT ASSERTED HERE: how the names are worded on glass.
`Front Door Sensor` -> "Front Door" is a render-boundary rewrite and lives
in ha-dashboard-kit's humanize.ts with its own tests, because the raw name
has to stay on the entity for the next diagnosis (LAW 10). What this file
owns is that the ids REACH the boundary at all.

Self-test discipline (LAW 4): FAIL_CASES assert deliberately WRONG outcomes
on real inputs, and main() proves every one fails before any PASS is
trusted.
"""

import sys  # noqa: E402

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
    ALARM_ARMED_OPEN_SEV,
    ALARM_TRIGGERED_SEV,
    PERIMETER_DWELL,
    PERIMETER_SEV,
    SOURCES,
)

ALARM_ROW = next(s for s in SOURCES if s["key"] == "alarm")
# GH #16: SOURCES ships no estate ids, so the suite names its own.
_ALARM_ENTITY = "alarm_control_panel.test_panel"
PERIM_ROW = next(s for s in SOURCES if s["key"] == "perimeter_open")

# Real ids off this estate's `fls_device` label, warts intact. The stutter
# in the first two is not a typo -- HA mints an id by concatenating device
# and entity names, and these are what `label_entities('fls_device')`
# actually returns. They are here because a naming change that only works
# on tidy ids does not work on this house.
FRONT = "binary_sensor.front_door_sensor_door_sensor"
WORKSHOP = "cover.workshop_workshop_door_door"
GARAGE = "cover.garage_door"


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


def read_perimeter(members, sustained_ids):
    """Run the REAL perimeter read. Every member is open; the ones in
    `sustained_ids` have been open long enough to clear the dwell."""
    import datetime as _dt

    from household_state.coordinator import HouseholdStateCoordinator as C

    now = _dt.datetime.now(_dt.timezone.utc)
    old = (now - _dt.timedelta(seconds=PERIMETER_DWELL + 60)).isoformat()
    fresh = now.isoformat()

    mapping = {}
    for eid in members:
        opened = "on" if eid.startswith("binary_sensor.") else "open"
        mapping[eid] = _State(opened)

    inst = C.__new__(C)
    inst.hass = _Hass(mapping)
    inst._warn_once = lambda *a, **k: None
    # GH #16: _read_source resolves its entity through the binding map, so a
    # hand-built instance carries one. Empty means "no override", which is
    # what every case here wants: the SOURCES row's own default.
    # GH #16: entity and label are configuration now, so a hand-built
    # instance must say what it binds or every row reports `unbound`.
    inst._bindings = {"perimeter.label": "fls_device"}
    inst._perimeter_entity_ids = lambda: list(members)
    inst._mark = lambda key, state: (
        old if key.split(":", 1)[1] in sustained_ids else fresh
    )
    base = {
        "key": PERIM_ROW["key"],
        "name": PERIM_ROW["name"],
        "entity_id": None,
        "axis": PERIM_ROW["axis"],
        "kind": PERIM_ROW["kind"],
        "severity": None,
        "raw_state": None,
        "detail": None,
        "disposition": None,
    }
    return C._read_perimeter(inst, PERIM_ROW, base)


def read_alarm(state, open_sensors):
    """Run the REAL alarm read against a stubbed Alarmo."""
    from household_state.coordinator import HouseholdStateCoordinator as C

    inst = C.__new__(C)
    inst.hass = _Hass(
        {_ALARM_ENTITY: _State(state, {"open_sensors": open_sensors})}
    )
    inst._warn_once = lambda *a, **k: None
    inst._bindings = {"alarm.entity_id": _ALARM_ENTITY}
    return C._read_source(inst, ALARM_ROW)


def perim_detail(members, sustained):
    return read_perimeter(members, sustained)["detail"]


def alarm_detail(state, open_sensors):
    return read_alarm(state, open_sensors)["detail"]


# (label, callable, expected)
CASES = [
    # ---- the perimeter row names every sustained opening ------------
    ("one sustained opening is named",
     lambda: perim_detail([FRONT], {FRONT}),
     FRONT + " open over " + str(PERIMETER_DWELL) + "s"),
    ("THREE sustained openings are all named, never `+2 more`",
     lambda: perim_detail([FRONT, WORKSHOP, GARAGE], {FRONT, WORKSHOP, GARAGE}),
     FRONT + ", " + WORKSHOP + ", " + GARAGE
     + " open over " + str(PERIMETER_DWELL) + "s"),
    ("no `+N more` count survives anywhere in the detail",
     lambda: "more" in perim_detail([FRONT, WORKSHOP], {FRONT, WORKSHOP}), False),
    ("a member open but not yet dwelled is still counted as open",
     lambda: read_perimeter([FRONT, WORKSHOP], {FRONT})["open_count"], 2),
    ("...but does not reach the sustained detail",
     lambda: perim_detail([FRONT, WORKSHOP], {FRONT}),
     FRONT + " open over " + str(PERIMETER_DWELL) + "s"),
    ("a sustained opening still scores the configured severity",
     lambda: read_perimeter([FRONT], {FRONT})["severity"], PERIMETER_SEV),
    ("the ids are comma-joined, which no entity_id can contain (LAW 4)",
     lambda: perim_detail([FRONT, GARAGE], {FRONT, GARAGE}).count(", "), 1),
    ("nothing sustained -> the all-closed detail, not a name",
     lambda: "open over" in perim_detail([FRONT, GARAGE], set()), False),

    # ---- the alarm row forwards the sensors Alarmo named ------------
    ("armed with one open sensor names it",
     lambda: alarm_detail("armed_away", {FRONT: "on"}),
     "alarm armed_away, open: " + FRONT),
    ("armed with two open sensors names both",
     lambda: alarm_detail("armed_away", {FRONT: "on", GARAGE: "open"}),
     "alarm armed_away, open: " + FRONT + ", " + GARAGE),
    ("triggered names the zone that tripped it",
     lambda: alarm_detail("triggered", {FRONT: "on"}),
     "alarm triggered, open: " + FRONT),
    ("a list-shaped open_sensors is accepted too",
     lambda: alarm_detail("armed_home", [FRONT]),
     "alarm armed_home, open: " + FRONT),
    ("armed and quiet says so without an empty `open:` tail",
     lambda: alarm_detail("armed_away", None), "alarm armed_away"),
    ("disarmed carries no open list",
     lambda: alarm_detail("disarmed", None), "alarm disarmed"),
    ("naming the sensor did not disturb the severity ladder",
     lambda: read_alarm("armed_away", {FRONT: "on"})["severity"],
     ALARM_ARMED_OPEN_SEV),
    ("...nor the triggered rung",
     lambda: read_alarm("triggered", {FRONT: "on"})["severity"],
     ALARM_TRIGGERED_SEV),
    ("...nor armed-and-quiet, which still scores 0",
     lambda: read_alarm("armed_away", None)["severity"], 0),
]

# Deliberately WRONG expectations on real inputs. Every one MUST fail.
FAIL_CASES = [
    ("three openings must not collapse to a count",
     lambda: perim_detail([FRONT, WORKSHOP, GARAGE], {FRONT, WORKSHOP, GARAGE}),
     FRONT + " +2 more open over " + str(PERIMETER_DWELL) + "s"),
    ("a named opening must not vanish from the detail",
     lambda: GARAGE in perim_detail([FRONT, GARAGE], {FRONT, GARAGE}), False),
    ("an armed house with a door open must not publish the bare state",
     lambda: alarm_detail("armed_away", {FRONT: "on"}), "alarm armed_away"),
    ("a triggered alarm must not hide the zone",
     lambda: FRONT in alarm_detail("triggered", {FRONT: "on"}), False),
    ("a member that has not dwelled must not be reported sustained",
     lambda: WORKSHOP in perim_detail([FRONT, WORKSHOP], {FRONT}), True),
    ("severity must not have been lost to the wording change",
     lambda: read_perimeter([FRONT], {FRONT})["severity"], None),
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
        ok, _msg = _run(case)
        if ok:
            broken.append(case[0])
            print(f"  BROKEN  {case[0]} -- passed, but must fail")
        else:
            print(f"  ok      {case[0]}")
    if broken:
        print("\nSELF-TEST FAILED: the suite cannot detect these regressions.")
        return 1

    print("\n" + "=" * 70)
    print("GH-623: the row names which door")
    print("=" * 70)
    failed = []
    for case in CASES:
        ok, msg = _run(case)
        if not ok:
            failed.append((case[0], msg))
            print(f"  FAIL    {case[0]}: {msg}")
        else:
            print(f"  pass    {case[0]}")
    print()
    if failed:
        print(f"{len(failed)} of {len(CASES)} FAILED")
        return 1
    print(f"all {len(CASES)} passed")
    return 0


# -- pytest surface -------------------------------------------------------

def test_self_test_cases_all_fail():
    for case in FAIL_CASES:
        ok, msg = _run(case)
        assert not ok, f"FAIL_CASE passed but must fail: {case[0]} ({msg})"


def test_cases():
    bad = [(c[0], _run(c)[1]) for c in CASES if not _run(c)[0]]
    assert not bad, bad


if __name__ == "__main__":
    sys.exit(main())
