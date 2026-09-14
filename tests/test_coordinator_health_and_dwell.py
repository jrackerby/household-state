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
    FakeDevice,
    FakeDeviceRegistry,
    FakeEntityRegistry,
    FakeHass,
    FakeLabelRegistry,
    FakeRegistryEntry,
    FakeState,
)

CFG_SPEC = [s for s in SOURCES if s["kind"] == "config_entries"][0]


def coordinator(states=None, entries=(), registry=None, labels=(), devices=(),
                bindings=None):
    hass = FakeHass(states, registry or FakeEntityRegistry(),
                    label_registry=FakeLabelRegistry(labels),
                    device_registry=FakeDeviceRegistry(devices))
    hass.config_entries = FakeConfigEntries(entries)
    c = HouseholdStateCoordinator(hass, 3, bindings=bindings)
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
#
# OPT-IN (#28, ruled by Joel, reversing #26's opt-out): the row watches only
# what carries the scope label or sits on a device that does. Every fixture
# below therefore creates the label and puts the entities under test IN
# scope; the tests that leave something out are testing the leaving-out.

LABEL = "integrity_watched"


def watched(states=None, entries=(), registry=None, devices=(), bindings=None,
            labels=(LABEL,)):
    """A coordinator whose label registry carries the scope label."""
    return coordinator(states, entries, registry, labels=labels, devices=devices,
                       bindings=bindings)


def _reg(*entity_ids, entry="e1", device=None, labels=(LABEL,)):
    """A registry whose entities all belong to `entry` and carry the label
    themselves (or sit on `device` and carry nothing)."""
    return FakeEntityRegistry([
        FakeRegistryEntry(eid, config_entry_id=entry, device_id=device,
                          labels=() if device else labels)
        for eid in entity_ids
    ])


def _aged(c, *entry_ids):
    c._read_source(CFG_SPEC)
    for e in entry_ids:
        _age(c, "cfgentry:" + e, CONFIG_ENTRY_DWELL + 1)
    return c._read_source(CFG_SPEC)


def test_a_disabled_entry_is_not_watched():
    """A disabled entry reads `not_loaded` with a null reason — it is not a
    fault, it is a choice. Even labelled, it is skipped."""
    c = watched(entries=[FakeConfigEntry("e1", state="not_loaded", disabled_by="user"),
                         FakeConfigEntry("e2")],
                registry=FakeEntityRegistry([
                    FakeRegistryEntry("sensor.a", config_entry_id="e1", labels=(LABEL,)),
                    FakeRegistryEntry("sensor.b", config_entry_id="e2", labels=(LABEL,)),
                ]),
                states={"sensor.b": FakeState("1")})
    r = c._read_source(CFG_SPEC)
    assert r["watched_count"] == 1
    assert r["integrity"] == INTEGRITY_OK


def test_a_fresh_setup_retry_does_not_count_yet():
    """CONFIG_ENTRY_DWELL holds a fresh `bad` reading before it counts: this
    row reads raw framework state with no upstream dwell of its own, and a
    core restart's window of entries still starting would otherwise page
    before HA finished booting."""
    r = watched(entries=[FakeConfigEntry("e1", domain="music_assistant", title="MA",
                                         state="setup_retry")],
                registry=_reg("media_player.x"))._read_source(CFG_SPEC)
    assert r["integrity"] == INTEGRITY_OK


def test_a_sustained_setup_retry_degrades_and_names_the_entry():
    c = watched(entries=[FakeConfigEntry("e1", domain="music_assistant", title="MA",
                                         state="setup_retry")],
                registry=_reg("media_player.x"))
    r = _aged(c, "e1")
    assert r["integrity"] == INTEGRITY_DEGRADED
    assert "MA" in r["integrity_detail"]
    assert "music_assistant" in r["integrity_detail"]
    assert "setup_retry" in r["integrity_detail"]
    assert r["affected"] == 1


def test_a_loaded_entry_whose_every_entity_is_unavailable_is_a_fault():
    """The UPS: a config entry can read `loaded` while every entity it owns
    reads unavailable. Found only by accident, 2h25m in."""
    c = watched({"sensor.ups_load": FakeState("unavailable"),
                 "sensor.ups_charge": FakeState("unavailable")},
                entries=[FakeConfigEntry("e1", domain="nut", title="UPS")],
                registry=_reg("sensor.ups_load", "sensor.ups_charge"))
    r = _aged(c, "e1")
    assert r["integrity"] == INTEGRITY_DEGRADED
    assert "2 entities unavailable" in r["integrity_detail"]


def test_a_partially_unavailable_entry_is_not_a_fault():
    """The signal is ALL of them, not some. A device with one dead sensor is
    that integration's business, not this row's."""
    c = watched({"sensor.a": FakeState("unavailable"), "sensor.b": FakeState("12")},
                entries=[FakeConfigEntry("e1")], registry=_reg("sensor.a", "sensor.b"))
    assert _aged(c, "e1")["integrity"] == INTEGRITY_OK


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
    registry = FakeEntityRegistry([
        FakeRegistryEntry("sensor.a", config_entry_id="e1", labels=(LABEL,)),
        FakeRegistryEntry("sensor.b", config_entry_id="e2", labels=(LABEL,)),
    ])
    r = _aged(watched(entries=entries, registry=registry), "e1", "e2")
    assert r["affected"] == 2
    assert "+1 more" in r["integrity_detail"]


def test_every_sustained_fault_is_published_in_full():
    """`integrity_detail` is a headline; "+N more" in it left the other N
    unreadable anywhere on the entity (#26). The full list is an attribute."""
    entries = [FakeConfigEntry(k, domain=k, title=k.upper(), state="setup_retry")
               for k in ("a", "b", "c")]
    registry = FakeEntityRegistry([
        FakeRegistryEntry("sensor." + k, config_entry_id=k, labels=(LABEL,))
        for k in ("a", "b", "c")
    ])
    r = _aged(watched(entries=entries, registry=registry), "a", "b", "c")
    assert "+2 more" in r["integrity_detail"]
    assert r["affected_entries"] == [
        "A (a): setup_retry", "B (b): setup_retry", "C (c): setup_retry",
    ]


def test_affected_entries_is_always_present_when_the_row_reads():
    r = watched(entries=[FakeConfigEntry("e1")], registry=_reg("sensor.a"),
                states={"sensor.a": FakeState("1")})._read_source(CFG_SPEC)
    assert r["affected_entries"] == []
    assert r["watched_count"] == 1
    assert r["unwatched_count"] == 0


# ------------------------------------------------- the scope label (#28)

def _tv(label_on, label=LABEL):
    """One webOS-shaped entry: two entities on one device, both unavailable
    because the TV is off. The label sits on the device, on each entity,
    or nowhere."""
    dev_labels = (label,) if label_on == "device" else ()
    ent_labels = (label,) if label_on == "entity" else ()
    registry = FakeEntityRegistry([
        FakeRegistryEntry("media_player.tv", config_entry_id="tv",
                          device_id="d-tv", labels=ent_labels),
        FakeRegistryEntry("remote.tv", config_entry_id="tv",
                          device_id="d-tv", labels=ent_labels),
    ])
    return registry, [FakeDevice("d-tv", labels=dev_labels)]


TV_OFF = {"media_player.tv": FakeState("unavailable"), "remote.tv": FakeState("unavailable")}
TV_ENTRY = [FakeConfigEntry("tv", domain="webostv", title="Main Bed LGTV")]


def test_an_unlabelled_off_tv_is_out_of_scope_and_not_a_fault():
    """THE RULING. Nothing labelled it, so it is not integrity's business —
    but the row still needs SOMETHING in scope to read at all, hence the
    second, labelled, healthy entry."""
    registry, devices = _tv(label_on="none")
    registry.entities["sensor.ups"] = FakeRegistryEntry(
        "sensor.ups", config_entry_id="ups", labels=(LABEL,))
    c = watched({**TV_OFF, "sensor.ups": FakeState("100")},
                entries=TV_ENTRY + [FakeConfigEntry("ups", domain="nut", title="UPS")],
                registry=registry, devices=devices)
    r = _aged(c, "tv", "ups")
    assert r["integrity"] == INTEGRITY_OK
    assert r["watched_count"] == 1
    assert r["unwatched_count"] == 1
    assert r["affected_entries"] == []


def test_a_device_label_puts_an_off_tv_in_scope_and_it_faults():
    registry, devices = _tv(label_on="device")
    c = watched(TV_OFF, entries=TV_ENTRY, registry=registry, devices=devices)
    r = _aged(c, "tv")
    assert r["integrity"] == INTEGRITY_DEGRADED
    assert r["affected_entries"] == ["Main Bed LGTV (webostv): all 2 entities unavailable"]
    assert r["watched_count"] == 1


def test_an_entity_label_works_the_same_as_a_device_label():
    registry, devices = _tv(label_on="entity")
    c = watched(TV_OFF, entries=TV_ENTRY, registry=registry, devices=devices)
    assert _aged(c, "tv")["integrity"] == INTEGRITY_DEGRADED


def test_an_unlabelled_entry_in_setup_retry_is_out_of_scope_too():
    """Scope is about the device, not about which shape its integration
    chose when it could not reach it."""
    registry, devices = _tv(label_on="none")
    registry.entities["sensor.ups"] = FakeRegistryEntry(
        "sensor.ups", config_entry_id="ups", labels=(LABEL,))
    c = watched({"sensor.ups": FakeState("100")},
                entries=[FakeConfigEntry("tv", domain="webostv", title="Main Bed LGTV",
                                         state="setup_retry"),
                         FakeConfigEntry("ups", domain="nut", title="UPS")],
                registry=registry, devices=devices)
    r = _aged(c, "tv", "ups")
    assert r["integrity"] == INTEGRITY_OK
    assert r["unwatched_count"] == 1


def test_a_partly_labelled_entry_is_judged_on_the_labelled_part():
    """A hub entry with one watched device and one that is not: only the
    watched device's entities form the ratio."""
    registry = FakeEntityRegistry([
        FakeRegistryEntry("media_player.tv", config_entry_id="hub", device_id="d-tv"),
        FakeRegistryEntry("sensor.hub_uptime", config_entry_id="hub", device_id="d-hub"),
    ])
    devices = [FakeDevice("d-tv"), FakeDevice("d-hub", labels=(LABEL,))]
    entries = [FakeConfigEntry("hub", domain="x", title="Hub")]

    c = watched({"media_player.tv": FakeState("unavailable"),
                 "sensor.hub_uptime": FakeState("unavailable")},
                entries=entries, registry=registry, devices=devices)
    r = _aged(c, "hub")
    assert r["integrity"] == INTEGRITY_DEGRADED
    assert "all 1 entities unavailable" in r["integrity_detail"]

    c = watched({"media_player.tv": FakeState("unavailable"),
                 "sensor.hub_uptime": FakeState("42")},
                entries=entries, registry=registry, devices=devices)
    assert _aged(c, "hub")["integrity"] == INTEGRITY_OK


def test_no_label_in_the_registry_is_absent_not_ok(caplog):
    """A row that watches only what is labelled, with no label, watches
    nothing — and a monitor with no scope must not read green. Somebody has
    to create the label, so this is a WARNING, not INFO."""
    registry, devices = _tv(label_on="device")
    c = watched(TV_OFF, entries=TV_ENTRY, registry=registry, devices=devices, labels=())
    r = c._read_source(CFG_SPEC)
    assert r["disposition"] == DISP_ABSENT
    assert "integrity_watched" in r["detail"]
    assert r.get("integrity") != INTEGRITY_OK
    assert "does not resolve" in caplog.text
    assert "WARNING" in caplog.text


def test_a_label_that_nothing_carries_is_absent_not_ok(caplog):
    registry, devices = _tv(label_on="none")
    c = watched(TV_OFF, entries=TV_ENTRY, registry=registry, devices=devices)
    r = c._read_source(CFG_SPEC)
    assert r["disposition"] == DISP_ABSENT
    assert "carries label integrity_watched" in r["detail"]
    assert r["watched_count"] == 0
    assert r["unwatched_count"] == 1
    assert "zero watched entries" in caplog.text


def test_a_cleared_binding_falls_back_to_the_default_label():
    """An options flow hands back "" for a cleared field; that is unset,
    not a label named ""."""
    registry, devices = _tv(label_on="device")
    c = watched(TV_OFF, entries=TV_ENTRY, registry=registry, devices=devices,
                bindings={"config_entry_health.label": "   "})
    assert _aged(c, "tv")["integrity"] == INTEGRITY_DEGRADED


def test_the_scope_label_follows_its_binding():
    """`config_entry_health.label` renames the label the row honours."""
    registry, devices = _tv(label_on="device", label="depends_on")
    c = watched(TV_OFF, entries=TV_ENTRY, registry=registry, devices=devices,
                labels=("depends_on",),
                bindings={"config_entry_health.label": "depends_on"})
    assert _aged(c, "tv")["integrity"] == INTEGRITY_DEGRADED


def test_a_broken_label_registry_is_absent_not_ok():
    """RULE 1: the label lookup cannot take the row down, and cannot make
    it read healthy either."""
    class Broken:
        def async_get_label(self, _):
            raise RuntimeError("label registry moved")

        def async_get_label_by_name(self, _):
            raise RuntimeError("label registry moved")

    registry, devices = _tv(label_on="device")
    c = watched(TV_OFF, entries=TV_ENTRY, registry=registry, devices=devices)
    c.hass.label_registry = Broken()
    r = c._read_source(CFG_SPEC)
    assert r["disposition"] == DISP_ABSENT
    assert r.get("integrity") != INTEGRITY_OK


def test_a_label_applied_later_starts_the_dwell_fresh():
    """An unwatched entry is marked `ok` while out of scope, so labelling it
    mid-fault does not page on the very next poll."""
    registry, devices = _tv(label_on="none")
    registry.entities["sensor.ups"] = FakeRegistryEntry(
        "sensor.ups", config_entry_id="ups", labels=(LABEL,))
    c = watched({**TV_OFF, "sensor.ups": FakeState("100")},
                entries=TV_ENTRY + [FakeConfigEntry("ups", domain="nut", title="UPS")],
                registry=registry, devices=devices)
    c._read_source(CFG_SPEC)
    devices[0].labels.add(LABEL)               # the operator labels the TV
    r = c._read_source(CFG_SPEC)
    assert r["watched_count"] == 2
    assert r["integrity"] == INTEGRITY_OK, "fresh reading, dwell not elapsed"
    _age(c, "cfgentry:tv", CONFIG_ENTRY_DWELL + 1)
    assert c._read_source(CFG_SPEC)["integrity"] == INTEGRITY_DEGRADED


def test_one_bad_entry_never_takes_the_row_down():
    """RULE 1 at the per-entry level."""
    class Bad:
        entry_id = "bad"

        def __getattr__(self, name):
            raise RuntimeError("entry moved")

    c = watched(entries=[Bad(), FakeConfigEntry("e1")], registry=_reg("sensor.a"),
                states={"sensor.a": FakeState("1")})
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
