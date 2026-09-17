"""The component's version is declared once, in manifest.json.

#10: entity.py's DeviceInfo carried `sw_version="0.5.1"` as a literal while
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
# Everything else is guarded, const.py included: it used to carry a changelog
# in its module docstring and was exempted for it, and the exemption outlived
# the changelog. The history lives in `git log`, where it cannot go stale.
SHIPPED_PY = ("__init__.py", "banner.py", "binary_sensor.py", "config_flow.py",
              "const.py", "coordinator.py", "entity.py", "resolver.py", "sensor.py")


def _manifest_version() -> str:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]


def _code_lines(path: pathlib.Path):
    """Source lines with comments and docstrings excluded.

    assert on code forms, not on text, and strip comments first — a
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
        "version literal in shipped code — #10's shape, a second copy that "
        f"release.yml will never update: {offenders}"
    )


def test_the_assertions_can_fail(tmp_path):
    """a check that cannot go red is not a check."""
    # The pattern must actually match the literal that caused #10 ...
    assert VERSION_LITERAL.fullmatch('"0.5.1"')
    assert VERSION_LITERAL.fullmatch("'1.2'")
    # ... and must not match things that merely look like one.
    assert not VERSION_LITERAL.fullmatch('"household_state"')
    assert not VERSION_LITERAL.fullmatch('"0"')
    assert not VERSION_LITERAL.fullmatch("0.5")  # unquoted float, not a literal string
    # The comment/docstring stripper must actually strip, or prose mentioning
    # a release would report as an offender forever. The fixture is built here
    # rather than borrowed from a shipped file: the previous version of this
    # check asserted on const.py's own changelog, so editing that changelog
    # failed a test about the stripper, which is the wrong thing to break.
    fixture = tmp_path / "fixture.py"
    fixture.write_text(
        '\'\'\'Docstring mentioning "9.9.9".\'\'\'\n'
        'X = "8.8.8"  # comment mentioning "7.7.7"\n',
        encoding="utf-8",
    )
    stripped = {t for _, t in _code_lines(fixture)}
    assert not any("9.9.9" in t for t in stripped), "docstring was not stripped"
    assert not any("7.7.7" in t for t in stripped), "comment was not stripped"
    # ... and it must NOT strip a literal that is real code, or the guard
    # would pass on the very defect it exists to catch.
    assert any('"8.8.8"' == t for t in stripped), "stripper ate a real literal"
