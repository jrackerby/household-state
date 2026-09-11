"""The component's version is declared once, in manifest.json.

GH #10: entity.py's DeviceInfo carried `sw_version="0.5.1"` as a literal while
manifest.json read 0.9.0, so the device registry published a version that had
been wrong through four releases — visible in Settings, in a diagnostics dump,
and to anything joining on the device registry.

It went wrong the way every second copy does: release.yml cuts a release on a
manifest.json version CHANGE, so the one action that bumps the version is the
one action guaranteed not to touch the other copy. A test asserting the two
agree would have caught the drift but kept the copy. Removing the copy is the
fix; this file is the guard that it stays removed.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest.json"

# A dotted numeric literal in a quoted string, e.g. "0.5.1" or '1.2'. Broad on
# purpose: the defect was a version hardcoded ANYWHERE in the shipped source,
# not specifically in a field called sw_version.
VERSION_LITERAL = re.compile(r"""["'](\d+\.\d+(?:\.\d+)?)["']""")

# Files that are allowed to state a version, and why.
#   manifest.json  - the single declaration.
#   hacs.json      - declares the minimum Home Assistant, a DIFFERENT fact.
#   const.py       - prose: rulings are attributed by the release that made
#                    them ("0.5.0 - 2026-08-22, Joel"), which is history, not
#                    a restatement of what this build is.
SHIPPED_PY = ("__init__.py", "binary_sensor.py", "config_flow.py", "coordinator.py",
              "entity.py", "resolver.py", "sensor.py")


def _manifest_version() -> str:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]


def _code_lines(path: pathlib.Path):
    """Source lines with comments and docstrings excluded.

    LAW §4: assert on code forms, not on text, and strip comments first — a
    file documenting its own history otherwise matches the check that says the
    literal was removed.
    """
    import ast
    import io
    import tokenize

    src = path.read_text(encoding="utf-8")

    # Drop every string that is a docstring or a bare expression statement.
    tree = ast.parse(src, filename=str(path))
    doc_spans = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            doc_spans.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))

    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.start[0] in doc_spans:
            continue
        out.append((tok.start[0], tok.string))
    return out


def test_the_runtime_version_comes_from_the_manifest():
    from household_state.const import VERSION

    assert VERSION == _manifest_version(), (
        f"const.VERSION is {VERSION!r}, manifest.json says {_manifest_version()!r}"
    )


def test_device_info_does_not_restate_it():
    entity_src = (ROOT / "entity.py").read_text(encoding="utf-8")
    assert "sw_version=VERSION" in entity_src, "DeviceInfo no longer reads const.VERSION"


def test_no_shipped_module_hardcodes_a_version():
    offenders = {}
    for name in SHIPPED_PY:
        for lineno, text in _code_lines(ROOT / name):
            match = VERSION_LITERAL.fullmatch(text)
            if match:
                offenders.setdefault(name, []).append((lineno, match.group(1)))
    assert not offenders, (
        "version literal in shipped code — GH #10's shape, a second copy that "
        f"release.yml will never update: {offenders}"
    )


def test_the_assertions_can_fail():
    """LAW §4: a check that cannot go red is not a check."""
    # The pattern must actually match the literal that caused GH #10 ...
    assert VERSION_LITERAL.fullmatch('"0.5.1"')
    assert VERSION_LITERAL.fullmatch("'1.2'")
    # ... and must not match things that merely look like one.
    assert not VERSION_LITERAL.fullmatch('"household_state"')
    assert not VERSION_LITERAL.fullmatch('"0"')
    assert not VERSION_LITERAL.fullmatch("0.5")  # unquoted float, not a literal string
    # The comment/docstring stripper must actually strip, or const.py's
    # release-attributed rulings would report as offenders forever.
    const_code = {t for _, t in _code_lines(ROOT / "const.py")}
    const_raw = (ROOT / "const.py").read_text(encoding="utf-8")
    assert "0.5.0 — 2026-08-22" in const_raw, "the docstring under test moved"
    assert not any("2026-08-22" in t for t in const_code), "stripper did not strip"
