"""SourceSensor reports the WORST thing known about a source (GH-562).

WHAT WENT WRONG, AND WHY NOTHING CAUGHT IT. Each registry row publishes a
diagnostic entity whose state was `disposition` alone. `disposition` answers
"did the read succeed", not "is the source healthy" -- so a row that read
perfectly and reported DEGRADED published `ok`. Live, that put
sensor.household_state_critical_networking_device_health at `ok` while its own
`detail` said "Spectrum: could not read WAN latency (unknown)", underneath a
roll-up correctly reporting the axis degraded. Any surface rendering per-source
rows showed all green under a degraded roll-up.

That is LAW 11's "`ok at zero` and `could not read` are different values at the
source" collapsing at exactly the layer built to keep them apart, and LAW 10's
monitor whose blind spot correlates with its own subject.

The roll-up was never wrong: resolve() reads `integrity` off the same readings
and orders unknown before degraded. This suite pins that SourceSensor now
agrees with it, and that the two facts stay separately readable as attributes
rather than being fused into one lossy state.
"""

import ha_stubs

ha_stubs.install()

from household_state.const import (  # noqa: E402
    DISP_ABSENT,
    DISP_OK,
    DISP_UNKNOWN,
    INTEGRITY_DEGRADED,
    INTEGRITY_OK,
)
from household_state.sensor import SourceSensor  # noqa: E402


class _Coordinator:
    def __init__(self, reading):
        self.data = {"readings": {"row": reading}} if reading is not None else None


def _sensor(reading):
    return SourceSensor(_Coordinator(reading), "entry", {"key": "row", "name": "Row"})


# -- the state ------------------------------------------------------------

def test_readable_and_healthy_is_ok():
    s = _sensor({"disposition": DISP_OK, "integrity": INTEGRITY_OK})
    assert s.native_value == DISP_OK


def test_readable_but_degraded_reports_degraded_not_ok():
    """THE DEFECT. A clean read of a source saying `degraded` used to
    publish `ok`, because only the read was being reported."""
    s = _sensor(
        {
            "disposition": DISP_OK,
            "integrity": INTEGRITY_DEGRADED,
            "integrity_detail": "Spectrum: could not read WAN latency (unknown)",
        }
    )
    assert s.native_value == INTEGRITY_DEGRADED


def test_unreadable_beats_a_verdict():
    """A verdict computed from a failed read is not a verdict, and the
    resolver orders them the same way (unknown_rows before degraded_rows)."""
    s = _sensor({"disposition": DISP_UNKNOWN, "integrity": INTEGRITY_DEGRADED})
    assert s.native_value == DISP_UNKNOWN


def test_absent_source_still_reports_absent():
    s = _sensor({"disposition": DISP_ABSENT})
    assert s.native_value == DISP_ABSENT


def test_a_stage_row_carrying_no_verdict_is_unchanged():
    """STAGE rows never get an `integrity` key written. Their state must be
    exactly the disposition it was before this change -- the presence of the
    key is the condition, not the axis."""
    s = _sensor({"disposition": DISP_OK, "axis": "stage", "severity": 0})
    assert s.native_value == DISP_OK


def test_a_row_with_no_reading_at_all_is_none_not_ok():
    """An absent reading must not read as healthy."""
    assert _sensor({}).native_value is None
    assert _sensor(None).native_value is None


# -- the attributes -------------------------------------------------------

def test_both_facts_stay_separately_readable():
    s = _sensor(
        {
            "disposition": DISP_OK,
            "integrity": INTEGRITY_DEGRADED,
            "integrity_detail": "1 DevTools unreachable",
        }
    )
    a = s.extra_state_attributes
    assert a["disposition"] == DISP_OK
    assert a["integrity"] == INTEGRITY_DEGRADED


def test_detail_falls_back_to_integrity_detail():
    """The three registry-resolved integrity rows (live_page,
    config_entries, notify_health) write `integrity_detail` and never
    `detail`; only the `fls` kind mirrors one onto the other. Reading
    `detail` alone is why those three published a bare state with no text
    while the roll-up had their reason in hand."""
    s = _sensor(
        {
            "disposition": DISP_OK,
            "integrity": INTEGRITY_DEGRADED,
            "integrity_detail": "Main Bed LGTV (webostv): all 2 entities unavailable",
        }
    )
    assert s.extra_state_attributes["detail"] == (
        "Main Bed LGTV (webostv): all 2 entities unavailable"
    )


def test_an_explicit_detail_is_not_overwritten_by_the_fallback():
    s = _sensor(
        {
            "disposition": DISP_OK,
            "detail": "all 8 perimeter members closed",
            "integrity_detail": "should not win",
        }
    )
    assert s.extra_state_attributes["detail"] == "all 8 perimeter members closed"


def test_the_source_attribute_is_exposed():
    """GH-565. Two integrity rows deliberately share
    sensor.fls_device_status and differ only by which attribute triple they
    read. With `entity_id` alone on the entity they were indistinguishable
    on glass, which is how one was reported as measuring the other's
    subject. The binding was correct; it was unreadable."""
    fls = _sensor(
        {
            "disposition": DISP_OK,
            "entity_id": "sensor.fls_device_status",
            "integrity": INTEGRITY_OK,
            "integrity_attr": "fire_life_safety_integrity",
        }
    )
    sec = _sensor(
        {
            "disposition": DISP_OK,
            "entity_id": "sensor.fls_device_status",
            "integrity": INTEGRITY_OK,
            "integrity_attr": "security_integrity",
        }
    )
    assert fls.extra_state_attributes["entity_id"] == sec.extra_state_attributes["entity_id"]
    assert fls.extra_state_attributes["source_attr"] != sec.extra_state_attributes["source_attr"]
    assert sec.extra_state_attributes["source_attr"] == "security_integrity"


# -- the suite can fail ---------------------------------------------------

def test_the_assertions_can_fail():
    """LAW 4: prove the check CAN go red. Reinstating the old behaviour --
    state is the disposition, full stop -- must break the degraded case and
    nothing else."""
    original = SourceSensor.native_value

    def old_behaviour(self):
        return self._reading().get("disposition")

    SourceSensor.native_value = property(old_behaviour)
    try:
        regressed = _sensor(
            {"disposition": DISP_OK, "integrity": INTEGRITY_DEGRADED}
        ).native_value
        assert regressed == DISP_OK, (
            "SELF-TEST FAILED: the pre-GH-562 behaviour did not reproduce, so "
            "this suite is not testing what it claims to"
        )
    finally:
        SourceSensor.native_value = original

    # and the real implementation is back
    assert _sensor(
        {"disposition": DISP_OK, "integrity": INTEGRITY_DEGRADED}
    ).native_value == INTEGRITY_DEGRADED
