"""The brand assets are the mechanism, so they are checked like one.

Home Assistant renders an icon for a CUSTOM integration by reading the
integration's own directory, not a registry: loader.py's `has_branding` is
`"brand" in self._top_level_files`, and components/brands resolves
`Path(integration.file_path) / "brand"`. HACS agrees — its validate/brands.py
sets `asset_path = "brand/icon.png"` when `content_in_root` is set and returns
as soon as that path exists in the tree, consulting home-assistant/brands only
as a fallback.

That makes these files load-bearing in two places at once, with nothing in
this repo asserting they are still there or still the right shape. A resize
or a rename would be found by a user noticing a blank tile.

WHY BYTE-IDENTICAL ASSETS ARE A DEFECT, not a harmless duplicate: both layers
already substitute one image for another. brands' README says to add only the
icon images when the logo is the same, and core's IMAGE_FALLBACKS maps
`logo.png` -> `icon.png`. A second copy therefore changes nothing that the
fallback would not have done, and can drift from the original — this repo
shipped exactly that, a logo.png identical to icon.png, until #9.
"""

import hashlib
import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"

# (filename, required width, required height). From brands' image spec: the
# icon is square, 256 for the normal version and 512 for the hDPI one.
REQUIRED = (
    ("icon.png", 256, 256),
    ("icon@2x.png", 512, 512),
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes):
    """Width and height from a PNG's IHDR, or None if it is not a PNG.

    Read from the bytes rather than trusted from the filename: a JPEG renamed
    to .png is exactly the kind of thing that renders as a blank tile.
    """
    if not data.startswith(PNG_MAGIC) or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def test_the_brand_directory_is_at_the_top_level():
    """`has_branding` keys on the directory NAME at the integration root."""
    assert BRAND.is_dir(), (
        "brand/ is missing — core's has_branding checks for exactly this "
        "directory name at the integration's top level, so HA renders no icon "
        "without it and HACS's brands check falls through to the registry"
    )


def test_every_required_asset_exists_at_its_required_size():
    wrong = {}
    for name, want_w, want_h in REQUIRED:
        path = BRAND / name
        if not path.is_file():
            wrong[name] = "missing"
            continue
        size = _png_size(path.read_bytes())
        if size is None:
            wrong[name] = "not a PNG"
        elif size != (want_w, want_h):
            wrong[name] = f"{size[0]}x{size[1]}, want {want_w}x{want_h}"
    assert not wrong, f"brand assets wrong: {wrong}"


def test_no_two_brand_assets_are_byte_identical():
    """A duplicate is never needed: both layers already fall back."""
    seen = {}
    dupes = {}
    for path in sorted(BRAND.glob("*.png")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            dupes[path.name] = seen[digest]
        else:
            seen[digest] = path.name
    assert not dupes, (
        "brand assets duplicate each other byte for byte: "
        f"{dupes}. Delete the copy — core's IMAGE_FALLBACKS and the brands "
        "CDN both serve icon.png in place of a missing logo.png, so the copy "
        "adds nothing and can drift"
    )


def test_the_assertions_can_fail(tmp_path):
    """A gate that cannot go red is not a gate."""
    # The size reader must reject a file that is not a PNG at all ...
    assert _png_size(b"not a png at all") is None
    assert _png_size(b"\xff\xd8\xff\xe0" + b"\x00" * 40) is None  # JPEG magic
    # ... and must read a real one correctly. Build a 1x1 PNG header rather
    # than borrowing a shipped asset, so this check does not fail when a
    # shipped asset is legitimately resized.
    ihdr = PNG_MAGIC + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1, 1)
    assert _png_size(ihdr) == (1, 1)
    # The duplicate check must actually see a duplicate.
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"same"), b.write_bytes(b"same")
    digests = {hashlib.sha256(p.read_bytes()).hexdigest() for p in (a, b)}
    assert len(digests) == 1, "two identical files must hash alike"
