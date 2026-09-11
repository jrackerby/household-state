"""Every third-party import in the suite is declared in tests/requirements.txt.

LAW §15: extracting a component exposes its suite's undeclared dependencies,
and the first run on a CLEAN RUNNER is when it learns this. A suite that has
only ever run inside a shared .venv imports whatever that venv happens to carry
for other reasons — the declaration is missing and nothing says so while the
code stays put. tempest_wx's `import yaml` is the worked example: green for
months inside jrackerby/HA, red at COLLECTION on that repo's first CI run
(GH-670), where it read as a broken test rather than as a missing declaration.

The rule names the remedy and says it is cheap and static: every third-party
import across the suite, by AST, against sys.stdlib_module_names, covered by
the declared set. This is that check.

It runs by AST rather than by import so that a module which fails to import is
still ASSESSED — the failure mode being guarded against is precisely one where
importing is what breaks.
"""

import ast
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REQUIREMENTS = HERE / "requirements.txt"

# Modules the suite provides for itself, resolved from this directory or from
# the staged package tree conftest.py builds. Not third-party, not stdlib.
LOCAL = {"ha_stubs", "conftest", "household_state"}

# Distribution name -> the module name it installs under, where they differ.
DISTRIBUTION_MODULES = {"pyyaml": "yaml"}


def _declared() -> set[str]:
    modules = set()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        # Strip any version specifier; the name is all this check needs.
        name = line
        for sep in ("==", ">=", "<=", "~=", ">", "<", "[", "!"):
            name = name.split(sep, 1)[0]
        name = name.strip().lower()
        modules.add(DISTRIBUTION_MODULES.get(name, name.replace("-", "_")))
    return modules


def _imported() -> dict[str, set[str]]:
    """Top-level module name -> the files importing it."""
    found: dict[str, set[str]] = {}
    for path in sorted(HERE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # A relative import resolves inside the suite, never to a dist.
                if node.level or node.module is None:
                    continue
                names = [node.module]
            else:
                continue
            for name in names:
                found.setdefault(name.split(".", 1)[0], set()).add(path.name)
    return found


def test_every_third_party_import_is_declared():
    undeclared = {
        module: sorted(files)
        for module, files in _imported().items()
        if module not in sys.stdlib_module_names
        and module not in LOCAL
        and module not in _declared()
    }
    assert not undeclared, (
        "imported by the suite but absent from tests/requirements.txt — this is "
        f"GH-670's shape and it fails at COLLECTION on a clean runner: {undeclared}"
    )


def test_the_declared_set_is_not_empty():
    """A parse that silently yields nothing would pass the check above over a
    suite it never read. A gate that could not run is not a pass (LAW §5)."""
    assert _declared(), "tests/requirements.txt parsed to nothing"
    assert _imported(), "no imports found across the suite — the AST walk read nothing"


def test_the_assertion_can_fail():
    """LAW §4: every assertion set needs a self-test proving it CAN fail."""
    declared = _declared()
    assert "pytest" in declared and "yaml" in declared, (
        "the two the suite actually imports are not both declared"
    )
    # A module that is neither stdlib, local, nor declared must be caught.
    bogus = "a_module_that_is_not_installed_anywhere"
    assert bogus not in sys.stdlib_module_names
    assert bogus not in LOCAL
    assert bogus not in declared
    # And the distribution-name mapping must be doing real work: PyYAML is the
    # declared name, `yaml` is the imported one, and a check comparing the raw
    # strings would report the suite's only real dependency as undeclared.
    assert "pyyaml" not in declared, "PyYAML was not mapped to its module name"
