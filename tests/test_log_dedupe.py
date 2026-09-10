"""GH-491. What `_warn_once` compares, at what level, and when it is armed.

THE REGRESSION THIS FILE EXISTS FOR. `_warn_once` used to compare the
human-readable MESSAGE. A blind-set message carries a count and a member
list, so a shrinking blind set produced three different strings for one
unchanged condition and re-fired a WARNING on each — live, that read as
`4 sensor(s) unreadable` / `2 ...` / `1 ...`, fifteen entries over ninety
minutes, for a house that was simply finishing its boot.

END-TO-END COVERAGE MOVED, NOT DELETED (GH-717). The reported sequence was
originally replayed through `_read_live_page`, whose row left the INTEGRITY
axis when a pikiosk on the wrong page stopped being a household integrity
fault. `_read_perimeter` has the identical shape — a set resolved fresh off
the registry every poll, a blind list, and a count in the message — so the
replay moved there rather than going away with the row it happened to be
written against.

Cited standard: Home Assistant integration quality scale, `log-when-unavailable`
(silver) — "log only once in total to avoid spamming the logs", at `info` level.
"""

from __future__ import annotations

import logging

import pytest

import ha_stubs
from ha_stubs import (
    FakeEntityRegistry,
    FakeHass,
    FakeLabelRegistry,
    FakeRegistryEntry,
    FakeState,
)

ha_stubs.install()

from household_state.coordinator import HouseholdStateCoordinator  # noqa: E402


@pytest.fixture
def coord():
    c = HouseholdStateCoordinator(FakeHass(), 5)
    c.async_arm_logging()
    return c


def levels(caplog):
    return [r.levelno for r in caplog.records]


def messages(caplog):
    return [r.getMessage() for r in caplog.records]


# ---------------------------------------------------------------- the fix


def test_one_condition_logs_once_however_the_detail_moves(coord, caplog):
    """THE BUG. Same condition, three different details -> one line."""
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        coord._warn_once("perimeter_open", "blind", "4 unreadable: a, b, c, d")
        coord._warn_once("perimeter_open", "blind", "2 unreadable: b, d")
        coord._warn_once("perimeter_open", "blind", "1 unreadable: b")
    assert len(caplog.records) == 1
    assert "4 unreadable" in messages(caplog)[0]


def test_the_harness_can_tell_the_difference(coord, caplog):
    """SELF-TEST (LAW 4). The assertion above is only worth something if a
    genuine condition CHANGE still produces a second record. If this test
    ever passes with one record, the test above is passing vacuously."""
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        coord._warn_once("src", "blind", "cannot see 3")
        coord._warn_once("src", "missing", "gone entirely")
    assert len(caplog.records) == 2


def test_recovery_logs_once_and_then_stays_quiet(coord, caplog):
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        coord._warn_once("src", "blind", "cannot see 3")
        coord._warn_once("src", "")
        coord._warn_once("src", "")
    assert len(caplog.records) == 2
    assert "recovered" in messages(caplog)[1]


def test_a_healthy_source_never_announces_a_recovery_it_did_not_have(coord, caplog):
    """The old `else` branch fired on the FIRST poll of every healthy source,
    because `self._warned.get(key)` was None and None != "". A recovery from a
    fault that never happened is a false reading in the direction that trains
    an operator to stop reading the log."""
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        coord._warn_once("src", "")
    assert caplog.records == []


# ------------------------------------------------------- level, per the scale


def test_an_unreadable_source_is_info_not_warning(coord, caplog):
    """quality scale, log-when-unavailable: INFO."""
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        coord._warn_once("src", "unavailable", "sensor.x is unavailable")
        coord._warn_once("src2", "blind", "3 members unreadable")
        coord._warn_once("src3", "unknown", "sensor.y is unknown")
    assert levels(caplog) == [logging.INFO] * 3


@pytest.mark.parametrize(
    "state", ["missing", "label_absent", "label_empty", "unparsed", "registry_error"]
)
def test_a_config_defect_stays_a_warning(state, caplog):
    """The exception the rule leaves room for: nobody waits these out. A named
    source that does not exist, a label that resolves to nothing, an attribute
    that will not parse — somebody has to edit something."""
    c = HouseholdStateCoordinator(FakeHass(), 5)
    c.async_arm_logging()
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        c._warn_once("src", state, "detail")
    assert levels(caplog) == [logging.WARNING]


# ----------------------------------------------------------------- arming


def test_nothing_is_logged_before_ha_has_started(caplog):
    c = HouseholdStateCoordinator(FakeHass(), 5)
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        c._warn_once("src", "blind", "everything is still booting")
    assert caplog.records == []


def test_a_defect_that_survives_the_boot_still_logs_once_armed(caplog):
    """THE TRAP IN THE GATE. If the unarmed path RECORDED the condition, a
    source that was genuinely missing all through boot would read as
    already-reported the moment logging came up, and would never be logged at
    all — a silence indistinguishable from health."""
    c = HouseholdStateCoordinator(FakeHass(), 5)
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        c._warn_once("src", "missing", "sensor.x does not exist (never set up?)")
        c.async_arm_logging()
        c._warn_once("src", "missing", "sensor.x does not exist (never set up?)")
    assert len(caplog.records) == 1
    assert levels(caplog) == [logging.WARNING]


# ------------------------------------------- end to end, through a real read


def _perimeter_hass(states):
    """Four labelled perimeter contacts, exactly the shape the live estate
    resolves off `fls_device` — a set discovered every poll, never pinned."""
    reg = FakeEntityRegistry(
        FakeRegistryEntry(f"binary_sensor.{d}_contact", labels=("fls_device",))
        for d in ("back_door", "drop_zone", "front_door", "garage")
    )
    return FakeHass(
        states=states,
        entity_registry=reg,
        label_registry=FakeLabelRegistry(("fls_device",)),
    )


PERIMETER_SPEC = {
    "key": "perimeter_open",
    "name": "Perimeter Open, Sustained",
    "entity_id": None,
    "kind": "perimeter",
    "axis": "stage",
}


def _base():
    return {
        "key": PERIMETER_SPEC["key"],
        "name": PERIMETER_SPEC["name"],
        "entity_id": None,
        "axis": PERIMETER_SPEC["axis"],
        "kind": PERIMETER_SPEC["kind"],
        "severity": None,
        "raw_state": None,
        "detail": None,
        "disposition": "absent",
    }


def test_the_live_boot_sequence_produces_exactly_one_line(caplog):
    """Replays the reported sequence through _read_perimeter itself: four
    contacts with no state, then two arriving, then one more. One condition
    throughout — one log line, and the live count stays where a dashboard
    reads it, on the reading."""
    hass = _perimeter_hass({})
    c = HouseholdStateCoordinator(hass, 5)
    c.async_arm_logging()

    closed = FakeState("off")
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        r1 = c._read_perimeter(PERIMETER_SPEC, _base())
        hass.states.set("binary_sensor.back_door_contact", closed)
        hass.states.set("binary_sensor.front_door_contact", closed)
        r2 = c._read_perimeter(PERIMETER_SPEC, _base())
        hass.states.set("binary_sensor.garage_contact", closed)
        r3 = c._read_perimeter(PERIMETER_SPEC, _base())

    assert len(caplog.records) == 1
    assert levels(caplog) == [logging.INFO]

    # The readings still carry the moving truth, unflattened.
    assert [len(r["blind"]) for r in (r1, r2, r3)] == [4, 2, 1]
    assert all(r["disposition"] == "unknown" for r in (r1, r2, r3))


def test_the_contacts_coming_back_logs_the_recovery(caplog):
    hass = _perimeter_hass({})
    c = HouseholdStateCoordinator(hass, 5)
    c.async_arm_logging()
    closed = FakeState("off")
    with caplog.at_level(logging.DEBUG, logger="household_state.coordinator"):
        c._read_perimeter(PERIMETER_SPEC, _base())
        for d in ("back_door", "drop_zone", "front_door", "garage"):
            hass.states.set(f"binary_sensor.{d}_contact", closed)
        reading = c._read_perimeter(PERIMETER_SPEC, _base())
    assert len(caplog.records) == 2
    assert "recovered" in messages(caplog)[1]
    assert reading["severity"] == 0
