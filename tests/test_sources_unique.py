"""Every SOURCES row must be distinguishable — by key, and by NAME.

WHY NAME AND NOT JUST KEY. Each row publishes a diagnostic entity whose
entity_id is a slug of `name`, not of `key`. Two rows sharing a name therefore
collide in the registry: the second takes `_2` and NEVER reclaims the id
(TOOLS.md), and both entities render with the identical friendly name, which
no surface can tell apart.

That is GH-565's defect — "the two per-source entities were indistinguishable
on glass and got reported as one row duplicated onto another's subject. The
binding was correct; it was unreadable." 0.7.0 reintroduced it: the boil-water
STAGE row and the boil-water DIRECTIVE row were both named "Boil Water
Advisory", and live HA produced sensor.household_state_boil_water_advisory
alongside sensor.household_state_boil_water_advisory_2.

Two rows may absolutely SHARE AN ENTITY -- that is §7.3's shape for
sensor.fls_device_status and now for the boil-water sensor. What they may not
share is the name they publish under. This suite pins the difference.

Self-test discipline (LAW 4): FAIL_CASES assert deliberately WRONG outcomes
and main() proves each fails before any PASS is trusted.
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

from household_state.const import SOURCES  # noqa: E402


def slug(name):
    """How HA derives an entity_id suffix from a friendly name."""
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


def dupes(values):
    seen, out = set(), set()
    for v in values:
        if v in seen:
            out.add(v)
        seen.add(v)
    return sorted(out)


KEYS = [r["key"] for r in SOURCES]
NAMES = [r["name"] for r in SOURCES]
SLUGS = [slug(r["name"]) for r in SOURCES]

CASES = [
    ("every row key is unique", lambda: dupes(KEYS), []),
    ("every row NAME is unique — no _2 collision", lambda: dupes(NAMES), []),
    ("every name SLUG is unique — the id is what actually collides",
     lambda: dupes(SLUGS), []),
    ("the two boil-water rows share an entity, deliberately",
     lambda: len({r["entity_id"] for r in SOURCES
                  if r["key"].startswith("boil_water")}), 1),
    ("...but publish under different names",
     lambda: len({r["name"] for r in SOURCES
                  if r["key"].startswith("boil_water")}), 2),
    ("every row names an axis", lambda: [r["key"] for r in SOURCES
                                         if not r.get("axis")], []),
    ("every row has a kind", lambda: [r["key"] for r in SOURCES
                                      if not r.get("kind")], []),
    # GH-717, Joel's ruling. A pikiosk showing the wrong page is not a
    # household integrity fault, and while `kiosk_live_page` held the axis
    # `degraded` over one pi's DevTools port, the dashboard server -- the server
    # feeding every screen in the house -- was hard down and reached this
    # registry not at all. The row is gone and this pins it gone: it would
    # otherwise be re-added by the next session that reads KAN-260 and sees
    # a signal with no consumer.
    ("the kiosk_live_page row stays removed",
     lambda: [r["key"] for r in SOURCES
              if r["key"] == "kiosk_live_page" or r["kind"] == "live_page"], []),
]

# A registry that HAS the removed row, so the check above cannot pass
# vacuously against a list that could never contain one.
_READDED = list(SOURCES) + [{
    "key": "kiosk_live_page",
    "name": "Kiosk Live Page",
    "entity_id": None,
    "kind": "live_page",
    "axis": "integrity",
}]

# The harness must catch a real duplicate, or it proves nothing.
_DUPE_NAMES = NAMES + [NAMES[0]]
_DUPE_KEYS = KEYS + [KEYS[0]]

FAIL_CASES = [
    ("a duplicated name must be reported",
     lambda: dupes(_DUPE_NAMES), []),
    ("a duplicated key must be reported",
     lambda: dupes(_DUPE_KEYS), []),
    ("the boil rows must not be collapsed to one name",
     lambda: len({r["name"] for r in SOURCES
                  if r["key"].startswith("boil_water")}), 1),
    ("a re-added kiosk_live_page row must be reported",
     lambda: [r["key"] for r in _READDED
              if r["key"] == "kiosk_live_page" or r["kind"] == "live_page"], []),
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
    print(f"ASSERTIONS  ({len(SOURCES)} rows)")
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


def test_sources_unique():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
