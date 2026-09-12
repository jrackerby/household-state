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
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"

# (filename, required width, required height). From brands' image spec: the
# icon is square, 256 for the normal version and 512 for the hDPI one.
REQUIRED = (
    ("icon.png", 256, 256),
    ("icon@2x.png", 512, 512),
)

# (filename, max width, max height). The logo is the wordmark lockup, so it is
# not square and brands gives it a BOX rather than a size: 512x256, doubled for
# the hDPI one. A floor comes with it — an asset well inside the box is a logo
# somebody shrank, and it arrives on a retina integration page as a soft one.
BOXED = (
    ("logo.png", 512, 256),
    ("logo@2x.png", 1024, 512),
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _ihdr(data: bytes):
    """(width, height, bit depth, colour type) from a PNG, or None.

    Read from the bytes rather than trusted from the filename: a JPEG renamed
    to .png is exactly the kind of thing that renders as a blank tile.
    """
    if not data.startswith(PNG_MAGIC) or data[12:16] != b"IHDR" or len(data) < 24:
        return None
    w, h = struct.unpack(">II", data[16:24])
    # A truncated header still yields a size, which is what _png_size wants;
    # depth and colour type simply are not there, and every caller of those
    # treats None as "not the format I need".
    return w, h, data[24] if len(data) > 24 else None, data[25] if len(data) > 25 else None


def _png_size(data: bytes):
    head = _ihdr(data)
    return None if head is None else head[:2]


def _top_left_alpha(data: bytes):
    """Alpha of the first pixel, or None if the file carries no alpha channel.

    Decodes exactly one scanline. Row 0 can be decoded alone whatever its
    filter byte says, because every filter's "prior row" term is defined as
    zero for the first row.
    """
    head = _ihdr(data)
    if head is None or head[3] != 6 or head[2] != 8:  # 6 = truecolour+alpha
        return None
    inflater, idat = zlib.decompressobj(), bytearray()
    i = 8
    while i + 8 <= len(data):
        length, kind = struct.unpack(">I", data[i : i + 4])[0], data[i + 4 : i + 8]
        if kind == b"IDAT":
            idat += data[i + 8 : i + 8 + length]
            row = inflater.decompress(bytes(idat), 8)
            if len(row) >= 5:
                # filter byte, then R G B A; Sub/Paeth/Average all reduce to
                # the raw byte on the first pixel of the first row.
                return row[4]
        i += 12 + length
    return None


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


def test_every_boxed_asset_fits_its_box_and_fills_one_side_of_it():
    wrong = {}
    for name, max_w, max_h in BOXED:
        path = BRAND / name
        if not path.is_file():
            wrong[name] = "missing"
            continue
        size = _png_size(path.read_bytes())
        if size is None:
            wrong[name] = "not a PNG"
        elif size[0] > max_w or size[1] > max_h:
            wrong[name] = f"{size[0]}x{size[1]}, over the {max_w}x{max_h} box"
        elif size[0] < max_w and size[1] < max_h:
            wrong[name] = f"{size[0]}x{size[1]}, inside the {max_w}x{max_h} box on BOTH sides"
    assert not wrong, f"brand assets wrong: {wrong}"


def test_every_asset_is_rgba_and_its_corner_is_transparent():
    """The artwork was supplied on an off-white ground, and the ground is the
    defect. An asset that keeps it is not obviously broken anywhere it is
    checked — it opens correctly, it is the right size, HACS accepts it — and
    then renders as a white slab on Home Assistant's dark theme and on a dark
    GitHub README. Colour type alone does not catch it: a baked ground can sit
    under a perfectly good alpha channel. So read a pixel."""
    wrong = {}
    for name, *_ in REQUIRED + BOXED:
        path = BRAND / name
        if not path.is_file():
            continue
        alpha = _top_left_alpha(path.read_bytes())
        if alpha is None:
            wrong[name] = "no 8-bit RGBA channel"
        elif alpha != 0:
            wrong[name] = f"corner alpha {alpha}, want 0 — the ground was baked in"
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
    # The alpha reader must report the ground an opaque asset would carry, and
    # must report it as absent on a file with no alpha channel at all.
    assert _top_left_alpha(b"not a png at all") is None
    assert _top_left_alpha(_rgba_png(0, 0, 0, 0)) == 0  # transparent corner
    assert _top_left_alpha(_rgba_png(243, 243, 243, 255)) == 255  # baked ground
    assert _ihdr(_rgba_png(0, 0, 0, 0))[:2] == (1, 1)


def _rgba_png(r, g, b, a):
    """A 1x1 8-bit RGBA PNG, built rather than borrowed.

    Reading a shipped asset here would make this self-test fail for the same
    reason the real check does, which is exactly what a self-test may not do.
    """

    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    return (
        PNG_MAGIC
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes([0, r, g, b, a])))
        + chunk(b"IEND", b"")
    )
