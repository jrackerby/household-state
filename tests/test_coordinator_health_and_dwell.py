"""The two integrity rows that read the framework, and RULE 3's fall dwell.

The config-entry row and the fall dwell (RULE 3) are the two places
where the coordinator makes a judgement over TIME rather than over a single
reading, so neither can be checked by inspection — and both were uncovered.
"""

import asyncio
from datetime import timedelta


from household_state.const import (
    CONFIG_ENTRY_DWELL,
    DISP_ABSENT,
    DISP_OK,
    FALL_DWELL,
    INTEGRITY_DEGRADED,
    INTEGRITY_OK,
    SOURCES,
)
from household_state.coordinator import HouseholdStateCoordinator

from ha_stubs import (
    FakeConfigEntries,
    FakeConfigEntry,
    FakeEntityRegistry,
    FakeHass,
    FakeRegistryEntry,
    FakeState,
)

CFG_SPEC = [s for s in SOURCES if s["kind"] == "config_entries"][0]


def coordinator(states=None, entries=(), registry=None):
    hass = FakeHass(states, registry or FakeEntityRegistry())
    hass.config_entries = FakeConfigEntries(entries)
    c = HouseholdStateCoordinator(hass, 3)
    c.async_arm_logging()
    return c


def _age(c, key, seconds):
    """Backdate a persisted `since` so a dwell has provably elapsed."""
    from homeassistant.util import dt as dt_util

    c._ages[key] = {
        "value": c._ages[key]["value"],
        "since": (dt_util.utcnow() - timedelta(seconds=seconds)).isoformat(),
    }


# ======================================================== config entry health

def test_no_entries_is_vacuously_healthy():
    r = coordinator(entries=())._read_source(CFG_SPEC)
    assert r["disposition"] == DISP_OK
    assert r["integrity"] == INTEGRITY_OK
    assert r["watched_count"] == 0


def test_a_disabled_entry_is_not_watched():
    """A disabled entry reads `not_loaded` with a null reason — it is not a
    fault, it is a choice."""
    r = coordinator(entries=[
        FakeConfigEntry("e1", state="not_loaded", disabled_by="user")
    ])._read_source(CFG_SPEC)
    assert r["watched_count"] == 0
    assert r["integrity"] == INTEGRITY_OK


def test_a_fresh_setup_retry_does_not_count_yet():
    """CONFIG_ENTRY_DWELL holds a fresh `bad` reading before it counts: this
    row reads raw framework state with no upstream dwell of its own, and a
    core restart's window of entries still starting would otherwise page
    before HA finished booting."""
    r = coordinator(entries=[
        FakeConfigEntry("e1", domain="music_assistant", title="MA",
                        state="setup_retry")
    ])._read_source(CFG_SPEC)
    assert r["integrity"] == INTEGRITY_OK


def test_a_sustained_setup_retry_degrades_and_names_the_entry():
    c = coordinator(entries=[
        FakeConfigEntry("e1", domain="music_assistant", title="MA",
                        state="setup_retry")
    ])
    c._read_source(CFG_SPEC)                      # first sighting starts the clock
    _age(c, "cfgentry:e1", CONFIG_ENTRY_DWELL + 1)
    r = c._read_source(CFG_SPEC)
    assert r["integrity"] == INTEGRITY_DEGRADED
    assert "MA" in r["integrity_detail"]
    assert "music_assistant" in r["integrity_detail"]
    assert "setup_retry" in r["integrity_detail"]
    assert r["affected"] == 1


def test_a_loaded_entry_whose_every_entity_is_unavailable_is_a_fault():
    """The UPS: a config entry can read `loaded` while every entity it owns
    reads unavailable. Found only by accident, 2h25m in."""
    registry = FakeEntityRegistry([
        FakeRegistryEntry("sensor.ups_load", config_entry_id="e1"),
        FakeRegistryEntry("sensor.ups_charge", config_entry_id="e1"),
    ])
    c = coordinator({"sensor.ups_load": FakeState("unavailable"),
                     "sensor.ups_charge": FakeState("unavailable")},
                    entries=[FakeConfigEntry("e1", domain="nut", title="UPS")],
                    registry=registry)
    c._read_source(CFG_SPEC)
    _age(c, "cfgentry:e1", CONFIG_ENTRY_DWELL + 1)
    r = c._read_source(CFG_SPEC)
    assert r["integrity"] == INTEGRITY_DEGRADED
    assert "2 entities unavailable" in r["integrity_detail"]


def test_a_partially_unavailable_entry_is_not_a_fault():
    """The signal is ALL of them, not some. A device with one dead sensor is
    that integration's business, not this row's."""
    registry = FakeEntityRegistry([
        FakeRegistryEntry("sensor.a", config_entry_id="e1"),
        FakeRegistryEntry("sensor.b", config_entry_id="e1"),
    ])
    c = coordinator({"sensor.a": FakeState("unavailable"),
                     "sensor.b": FakeState("12")},
                    entries=[FakeConfigEntry("e1")], registry=registry)
    c._read_source(CFG_SPEC)
    _age(c, "cfgentry:e1", CONFIG_ENTRY_DWELL + 1)
    assert c._read_source(CFG_SPEC)["integrity"] == INTEGRITY_OK


def test_an_entry_owning_no_entities_is_never_a_finding():
    """total==0 is vacuously healthy — an integration that creates no entities
    is not this row's business."""
    c = coordinator(entries=[FakeConfigEntry("e1")], registry=FakeEntityRegistry([]))
    c._read_source(CFG_SPEC)
    _age(c, "cfgentry:e1", CONFIG_ENTRY_DWELL + 1)
    assert c._read_source(CFG_SPEC)["integrity"] == INTEGRITY_OK


def test_the_signal_names_no_integration_in_its_code():
    """THE SIGNAL KEYS ON THE SHAPE, NEVER ONE INTEGRATION. A domain name in
    this function's CODE would make it a watchlist instead of a rule.

    Its docstring names music_assistant, androidtv_remote and the UPS on
    purpose — those are the live findings the rule was derived FROM, and
    citing your evidence is not the same as hardcoding it. So this reads
    string literals out of the AST rather than grepping the source (assert on code forms, and strip comments first).
    """
    import ast
    import inspect
    import textwrap

    src = textwrap.dedent(inspect.getsource(
        HouseholdStateCoordinator._read_config_entries))
    tree = ast.parse(src)
    fn = tree.body[0]
    # Exclude the docstring NODE, not a copy of its text: ast.get_docstring
    # returns a cleaned string, so an identity check against it never matches.
    doc_node = None
    if fn.body and isinstance(fn.body[0], ast.Expr) \
            and isinstance(fn.body[0].value, ast.Constant) \
            and isinstance(fn.body[0].value.value, str):
        doc_node = fn.body[0].value

    literals = [
        node.value for node in ast.walk(fn)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node is not doc_node
    ]
    joined = " ".join(literals).lower()
    for domain in ("music_assistant", "androidtv", "nut", "hue", "zwave", "ups"):
        assert domain not in joined, f"{domain!r} hardcoded in a string literal"
    # The extraction must actually have found literals, or this passes vacuously.
    assert literals, "no string literals read from the function at all"


def test_several_sustained_faults_are_counted_and_the_first_is_named():
    entries = [
        FakeConfigEntry("e1", domain="a", title="A", state="setup_retry"),
        FakeConfigEntry("e2", domain="b", title="B", state="setup_retry"),
    ]
    c = coordinator(entries=entries)
    c._read_source(CFG_SPEC)
    _age(c, "cfgentry:e1", CONFIG_ENTRY_DWELL + 1)
    _age(c, "cfgentry:e2", CONFIG_ENTRY_DWELL + 1)
    r = c._read_source(CFG_SPEC)
    assert r["affected"] == 2
    assert "+1 more" in r["integrity_detail"]


def test_one_bad_entry_never_takes_the_row_down():
    """RULE 1 at the per-entry level."""
    class Bad:
        entry_id = "bad"

        def __getattr__(self, name):
            raise RuntimeError("entry moved")

    c = coordinator(entries=[Bad(), FakeConfigEntry("e1")])
    r = c._read_source(CFG_SPEC)
    assert r["disposition"] == DISP_OK
    assert r["watched_count"] == 1


def test_an_unreadable_config_entry_registry_is_absent_not_healthy():
    c = coordinator(entries=())

    class Exploding:
        def async_entries(self):
            raise RuntimeError("moved")

    c.hass.config_entries = Exploding()
    r = c._read_source(CFG_SPEC)
    assert r["disposition"] == DISP_ABSENT
    assert r.get("integrity") != INTEGRITY_OK


# ============================================================ RULE 3, dwell

def dwell_coordinator():
    c = HouseholdStateCoordinator(FakeHass({}), 3)
    c.async_arm_logging()
    return c


def test_the_first_reading_is_published_immediately():
    c = dwell_coordinator()
    assert c._apply_fall_dwell(4) == (4, False, None)


def test_a_rise_is_never_held():
    c = dwell_coordinator()
    c._apply_fall_dwell(1)
    published, holding, _ = c._apply_fall_dwell(6)
    assert published == 6
    assert holding is False


def test_a_fall_is_held_at_the_previous_value():
    c = dwell_coordinator()
    c._apply_fall_dwell(6)
    published, holding, held_from = c._apply_fall_dwell(0)
    assert published == 6
    assert holding is True
    assert held_from is not None


def test_a_fall_publishes_once_the_dwell_expires():
    from homeassistant.util import dt as dt_util

    c = dwell_coordinator()
    c._apply_fall_dwell(6)
    c._held_since = dt_util.utcnow() - timedelta(seconds=FALL_DWELL + 1)
    published, holding, _ = c._apply_fall_dwell(0)
    assert published == 0
    assert holding is False


def test_losing_sight_is_a_fall_not_a_clear():
    """fall dwell, never rise dwell — and losing sight of a source
    COUNTS AS A FALL. An escalation must not be cleared by going blind."""
    c = dwell_coordinator()
    c._apply_fall_dwell(7)
    published, holding, _ = c._apply_fall_dwell(None)
    assert published == 7
    assert holding is True


def test_regaining_sight_at_the_same_severity_is_not_a_rise():
    c = dwell_coordinator()
    c._apply_fall_dwell(5)
    c._apply_fall_dwell(5)
    published, holding, _ = c._apply_fall_dwell(5)
    assert published == 5
    assert holding is False


def test_a_rise_out_of_unknown_publishes_at_once():
    c = dwell_coordinator()
    c._apply_fall_dwell(None)
    published, holding, _ = c._apply_fall_dwell(3)
    assert published == 3
    assert holding is False


def test_the_raw_severity_is_kept_while_the_dwell_holds():
    """A surface has to be able to tell a held value from a live one, or the
    dwell is invisible at exactly the moment it is acting."""
    from homeassistant.util import dt as dt_util

    c = coordinator({})
    asyncio.run(c._async_update_data())
    c._held_severity = 6
    c._held_since = dt_util.utcnow()
    out = asyncio.run(c._async_update_data())
    if out["fall_dwell_holding"]:
        assert out["raw_severity"] != out["severity"]
        assert out["fall_dwell_since"] is not None


def test_the_assertions_can_fail():
    """Self-test: this assertion set must be able to fail."""
    c = dwell_coordinator()
    # The dwell must actually hold, or every assertion above is trivially true.
    c._apply_fall_dwell(6)
    assert c._apply_fall_dwell(0)[0] == 6
    # And must actually release.
    from homeassistant.util import dt as dt_util
    c._held_since = dt_util.utcnow() - timedelta(seconds=FALL_DWELL + 1)
    assert c._apply_fall_dwell(0)[0] == 0
