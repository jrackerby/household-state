"""quality_scale.yaml is a gap-list nothing else validates.

hassfest's `validate_iqs_file` opens with `if not integration.core: return`,
so a custom component's quality_scale.yaml is NEVER read by the tool that
reads core's — while manifest.json's schema still accepts a `quality_scale`
key. Left ungated, the file is decoration: a rule added upstream silently goes
unassessed, a typo'd status silently means nothing, and an `exempt` loses the
reason that made it a ruling rather than a skip.

This is that gate (LAW §10: make the gate impossible to skip).

ALL_RULES BELOW IS A SNAPSHOT, and is marked as one. It was read from
`ALL_RULES` in home-assistant/core's script/hassfest/quality_scale.py on
2026-09-11, per LAW §15 — never from the docs page, which names the tiers and
not the rules. A second copy of an upstream list goes stale; the point here is
not to track core, it is to make drift a DELIBERATE edit to this file rather
than a rule quietly missing from the gap-list.
"""

import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
QS = ROOT / "quality_scale.yaml"

# Snapshot of ALL_RULES, 2026-09-11. Order is the tier order upstream uses.
BRONZE = (
    "action-setup",
    "appropriate-polling",
    "brands",
    "common-modules",
    "config-flow",
    "config-flow-test-coverage",
    "dependency-transparency",
    "docs-actions",
    "docs-conditions",
    "docs-high-level-description",
    "docs-installation-instructions",
    "docs-removal-instructions",
    "docs-triggers",
    "entity-event-setup",
    "entity-unique-id",
    "has-entity-name",
    "runtime-data",
    "test-before-configure",
    "test-before-setup",
    "unique-config-entry",
)
SILVER = (
    "action-exceptions",
    "config-entry-unloading",
    "docs-configuration-parameters",
    "docs-installation-parameters",
    "entity-unavailable",
    "integration-owner",
    "log-when-unavailable",
    "parallel-updates",
    "reauthentication-flow",
    "test-coverage",
)
GOLD = (
    "devices",
    "diagnostics",
    "discovery",
    "discovery-update-info",
    "docs-data-update",
    "docs-examples",
    "docs-known-limitations",
    "docs-supported-devices",
    "docs-supported-functions",
    "docs-troubleshooting",
    "docs-use-cases",
    "dynamic-devices",
    "entity-category",
    "entity-device-class",
    "entity-disabled-by-default",
    "entity-translations",
    "exception-translations",
    "icon-translations",
    "reconfiguration-flow",
    "repair-issues",
    "stale-devices",
)
PLATINUM = ("async-dependency", "inject-websession", "strict-typing")

ALL_RULES = BRONZE + SILVER + GOLD + PLATINUM

# The target. LAW §15: Silver for anything reading a device, a service, or
# another integration's entities, which is this integration's entire input.
TARGET_TIERS = BRONZE + SILVER

VALID = {"todo", "done", "exempt"}


@pytest.fixture(scope="module")
def rules():
    data = yaml.safe_load(QS.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and "rules" in data, "quality_scale.yaml has no `rules` map"
    return data["rules"]


def _status(value):
    """hassfest's shape: a bare string, or a mapping with status + comment."""
    return value["status"] if isinstance(value, dict) else value


def _comment(value):
    return value.get("comment") if isinstance(value, dict) else None


def test_every_rule_is_assessed(rules):
    """A rule missing from the file is a rule nobody decided."""
    missing = [r for r in ALL_RULES if r not in rules]
    assert not missing, f"rules with no verdict: {missing}"


def test_no_rule_outside_the_snapshot(rules):
    """An unknown key is a typo or a rule renamed upstream — either way it is
    silently assessing nothing."""
    extra = sorted(set(rules) - set(ALL_RULES))
    assert not extra, f"rules not in ALL_RULES: {extra}"


@pytest.mark.parametrize("rule", ALL_RULES)
def test_status_is_one_hassfest_accepts(rules, rule):
    status = _status(rules[rule])
    assert status in VALID, f"{rule}: status {status!r} is not one of {sorted(VALID)}"


@pytest.mark.parametrize("rule", ALL_RULES)
def test_exempt_carries_its_reason(rules, rule):
    """hassfest's SCHEMA REQUIRES a comment on exempt, and the reason is the
    whole difference between a ruling and a skip (LAW §15)."""
    value = rules[rule]
    if _status(value) != "exempt":
        return
    comment = _comment(value)
    assert comment and comment.strip(), f"{rule}: exempt with no comment"


def test_no_tier_is_silently_claimed():
    """manifest.json must not declare a quality_scale key while Bronze carries
    todos: hassfest accepts the key for a custom component and validates
    nothing behind it, so the declaration would be a self-claim."""
    import json

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert "quality_scale" not in manifest, (
        "manifest declares a tier; nothing gates that claim for a custom "
        "component. Close the Bronze todos in quality_scale.yaml first."
    )


def test_the_assertions_can_fail():
    """A gate that cannot fail is not a gate (LAW §4)."""
    # An unassessed rule is caught.
    assert [r for r in ALL_RULES if r not in {"action-setup"}], "snapshot is empty"
    # A bad status is caught.
    assert _status({"status": "maybe", "comment": "x"}) not in VALID
    assert _status("nonsense") not in VALID
    # An exempt with no comment is caught.
    assert not _comment({"status": "exempt"})
    # A bare string carries no comment, which is why exempt may not be one.
    assert _comment("done") is None
