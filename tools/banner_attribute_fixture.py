#!/usr/bin/env python3
"""THE RENDER FIXTURE THE KIT REPLAYS (#30, kit GH-201).

tests/fixtures/banner_parity.json is one direction of the port: what
ha-dashboard-kit's own `directiveNow()` rendered for every state map its
preview harness, design-sync previews and unit suite draw, and which
tests/test_banner_parity.py asserts banner.py reproduces.

This writes the OTHER direction, for the kit to replay once its resolver is
gone: the attributes `sensor.household_state_directive` actually publishes
for each of those same state maps, beside the render the kit recorded for
it. The kit's `directiveCell.ts` reads the attributes, mounts
DirectiveBanner/EvacuateOverlay, and asserts the words on the screen are
the words its own resolver produced — so the deletion of 868 lines is
proven against the surface, not against a description of it.

ONE FILE, TWO CONSUMERS, GENERATED NEVER HAND-EDITED:

    python3 tools/banner_attribute_fixture.py <kit>/src/__fixtures__/banner_attributes.json
"""

import json
import pathlib
import sys

TESTS = pathlib.Path(__file__).resolve().parent.parent / "tests"
sys.path.insert(0, str(TESTS))

# conftest.py stages the repo as `household_state` (HACS keeps the
# integration at the root and the directory name is not importable). It is
# the suite's own staging, reused rather than reimplemented — a second copy
# of it is a second thing to get wrong.
import conftest  # noqa: E402,F401
from test_banner_parity import DATA, _port  # noqa: E402


def main(out: str) -> None:
    cases = [
        {
            "title": case["title"],
            # What the kit's own resolver rendered for this state map, at the
            # commit the parity fixture names.
            "kit": case["expected"],
            # What household_state publishes for it, cell and all.
            "attributes": _port(case["states"]),
        }
        for case in DATA["cases"]
    ]
    payload = {
        "kit_commit": DATA["kit_commit"],
        "generator": "jrackerby/household-state tools/banner_attribute_fixture.py",
        "cases": cases,
    }
    pathlib.Path(out).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(cases)} cases -> {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "banner_attributes.json")
