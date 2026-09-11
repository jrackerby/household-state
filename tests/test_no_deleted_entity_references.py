"""Nothing shipped names an entity the estate has deleted.

sensor.home_threat_posture is DELETED, reversing an earlier decision to keep
it frozen — it was the comparison reference for
this integration, and that purpose was spent once 0.9.0 went live and its last
consumer moved to sensor.household_state_stage. "Do not recreate it."

#7 is what the absence of this check cost: SIX sites still described this
integration by its relationship to that entity, for five releases. One of them
was translations/en.json's config-flow description — rendered in the Home
Assistant UI at the moment someone adds the integration, pointing an installer
at an entity that does not exist. The others were headers a maintainer reads
before deciding what the component is for, and const.py contradicted itself two
lines apart.

Prose goes stale silently; that is the whole defect class. This makes one
specific ruling enforceable rather than remembered.

A ruling REVERSED upstream is handled by deleting the row here and saying so,
which is a deliberate edit with a diff — not by the check quietly passing.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# entity id -> the ruling that deleted it. Every shipped file is searched.
DELETED_ENTITIES = {
    "sensor.home_threat_posture": "deleted; do not recreate",
}

# Everything a user or a maintainer reads. Not tests/ — a test may legitimately
# name a deleted entity to assert it is gone, as this file does.
SHIPPED = (
    "__init__.py",
    "binary_sensor.py",
    "config_flow.py",
    "const.py",
    "coordinator.py",
    "entity.py",
    "resolver.py",
    "sensor.py",
    "manifest.json",
    "hacs.json",
    "README.md",
    "quality_scale.yaml",
    "translations/en.json",
)


def _shipped_files():
    return [(name, ROOT / name) for name in SHIPPED]


def test_every_shipped_file_exists():
    """A gate that could not run is not a pass. A renamed or deleted
    file would otherwise silently drop out of the sweep."""
    missing = [name for name, path in _shipped_files() if not path.is_file()]
    assert not missing, f"listed in SHIPPED but not on disk: {missing}"


@pytest.mark.parametrize("entity_id,ruling", sorted(DELETED_ENTITIES.items()))
def test_no_shipped_file_names_a_deleted_entity(entity_id, ruling):
    hits = []
    for name, path in _shipped_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if entity_id in line:
                hits.append(f"{name}:{lineno}")
    assert not hits, f"{entity_id} — {ruling} — still named at: {hits}"


def test_the_assertion_can_fail():
    """every assertion set needs a self-test proving it CAN fail."""
    # The sweep must actually be reading file contents: this very repo's
    # README says what the integration publishes, so a search for a string
    # that IS present must find it.
    present = [
        name for name, path in _shipped_files()
        if "household_state" in path.read_text(encoding="utf-8")
    ]
    assert present, "the sweep read no file contents at all"
    # And the registry must not be empty, or the parametrised test above would
    # generate zero cases and report green over nothing.
    assert DELETED_ENTITIES, "no rulings registered — the check would be vacuous"
