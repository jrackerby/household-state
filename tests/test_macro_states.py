"""Custom macro states: what the stored rows mean, what they read, and what
they publish.

THE SHAPE UNDER TEST IS QUIET'S, GENERALISED. QUIET has been a hardcoded
read-only mirror of a sleep-mode helper since 0.5.0; a macro state is the same
thing defined in a form. So the properties that matter are the ones QUIET
already holds and that a form makes easy to lose:

  - an unreadable source publishes None, never False. A modifier that reads
    `off` because its helper was deleted makes a positive claim about the
    household out of an absence, which is the dead-feed-reads-green defect
    wearing a different name;
  - RULE 7: a macro moves no axis. It is not in the stage severity, not in
    sources_total, not in confidence. A modifier that could move stage would
    let an installation raise its own household to Critical from a form;
  - the published id is frozen at creation, because Home Assistant never
    reclaims one (#19's reasoning, one level down).

config_flow.py's half of this is in test_config_flow.py.
"""

import asyncio

import pytest

import ha_stubs
from ha_stubs import FakeHass, FakeState
from household_state.binary_sensor import MacroState, Quiet
from household_state.binary_sensor import async_setup_entry as setup_binary
from household_state.const import (
    DISP_ABSENT,
    DISP_OK,
    DISP_UNKNOWN,
    DISP_UNREACHABLE,
    MACRO_DEFAULT_ON_STATE,
    MACRO_SLUG_MAX,
    NON_BINDING_OPTIONS,
    OPT_MACROS,
    RESERVED_MACRO_SLUGS,
    macro_slugify,
    macro_unique_id,
    macros_from_options,
    normalize_macro,
    normalize_macros,
)
from household_state.coordinator import HouseholdStateCoordinator

ENTRY_ID = "01ENTRYID"

GUEST = {"slug": "guest", "name": "Guest", "entity_id": "input_boolean.guest",
         "on_state": "on", "icon": None}
AWAY = {"slug": "away", "name": "Away", "entity_id": "person.sam",
        "on_state": "not_home", "icon": "mdi:home-export-outline"}


def coordinator(states=None, macros=()):
    return HouseholdStateCoordinator(FakeHass(states or {}), 3, {}, macros)


def read(macro, states):
    """One macro's reading, off a hass that answers `states`."""
    c = coordinator(states, [macro])
    return c._read_macro(dict(macro))


# ============================================================== the slug

@pytest.mark.parametrize(
    "name,slug",
    [
        ("Guest", "guest"),
        ("Guest Mode", "guest_mode"),
        ("  Guest   Mode  ", "guest_mode"),
        ("Vacation/Away", "vacation_away"),
        ("Work-From-Home", "work_from_home"),
        ("2 Kids Home", "2_kids_home"),
        ("Guest!!!", "guest"),
        ("", ""),
        ("!!!", ""),
        (None, ""),
    ],
)
def test_a_name_slugs_the_way_an_entity_id_needs(name, slug):
    assert macro_slugify(name) == slug


def test_the_slug_is_bounded_and_never_ends_on_a_separator():
    """A slug is an entity id somebody types into a template. Truncating in the
    middle of a word is ugly; truncating onto a trailing underscore produces an
    id that reads as a mistake."""
    slug = macro_slugify("x" * 200)
    assert len(slug) == MACRO_SLUG_MAX
    assert macro_slugify("a" * (MACRO_SLUG_MAX - 1) + " bcd").endswith("a")


def test_slugify_is_this_repo_s_and_not_a_call_into_core():
    """Deliberately not homeassistant.util.slugify: this value is PERSISTED in
    the config entry and compared against entity ids that already exist, so it
    must not change when core's implementation does. The check available here
    is that it answers with core absent — the stub installs no util.slugify,
    so a call into one would raise rather than differ quietly."""
    import sys

    assert not hasattr(sys.modules["homeassistant.util"], "slugify")
    assert macro_slugify("Guest Mode") == "guest_mode"


# ======================================================= stored rows

def test_a_complete_row_survives_normalisation_unchanged():
    assert normalize_macro(dict(GUEST)) == GUEST


def test_the_defaults_are_filled_in_rather_than_demanded():
    got = normalize_macro({"slug": "guest", "entity_id": "input_boolean.guest"})
    assert got["on_state"] == MACRO_DEFAULT_ON_STATE
    assert got["name"] == "guest"
    assert got["icon"] is None


@pytest.mark.parametrize(
    "row",
    [
        None,
        "guest",
        {},
        {"slug": "guest"},
        {"slug": "guest", "entity_id": ""},
        {"slug": "guest", "entity_id": "   "},
        {"slug": "guest", "entity_id": 17},
        {"slug": "", "entity_id": "input_boolean.guest"},
        {"slug": "!!!", "entity_id": "input_boolean.guest"},
        {"slug": "quiet", "entity_id": "input_boolean.guest"},
    ],
)
def test_a_row_that_cannot_publish_is_dropped_rather_than_repaired(row):
    """`.storage` is hand-editable and the options flow validates before it
    writes, so an unusable row means somebody edited the file. Guessing a slug
    or an entity id for it would publish an entity under a name nobody chose."""
    assert normalize_macro(row) is None


def test_a_reserved_slug_never_survives_a_hand_edit():
    """The flow refuses these, but the flow is not the only way a row gets
    into the entry. binary_sensor.household_state_quiet is published by QUIET
    and a second claim on it lands on `_2`."""
    for slug in RESERVED_MACRO_SLUGS:
        assert normalize_macro({"slug": slug, "entity_id": "input_boolean.x"}) is None


def test_order_is_preserved_and_a_duplicate_slug_is_dropped():
    """FIRST WINS. Two rows claiming one entity id would publish one entity
    whose source depends on iteration order — the kind of fact only discovered
    during an incident."""
    rows = [GUEST, AWAY, dict(GUEST, entity_id="input_boolean.other")]
    got = normalize_macros(rows)
    assert [m["slug"] for m in got] == ["guest", "away"]
    assert got[0]["entity_id"] == "input_boolean.guest"


@pytest.mark.parametrize("value", [None, {}, "guest", 17, object()])
def test_anything_that_is_not_a_list_of_rows_is_no_macros(value):
    assert normalize_macros(value) == ()


def test_macros_are_read_off_the_options_key():
    assert macros_from_options({OPT_MACROS: [GUEST]}) == (GUEST,)
    assert macros_from_options({}) == ()
    assert macros_from_options(None) == ()


def test_the_macros_option_is_not_mistaken_for_a_source_binding():
    """__init__.py splits entry.options into bindings and everything else. A
    non-binding option missing from that set is handed to the coordinator as a
    binding for a source named after itself, which resolves to nothing and
    says nothing about why."""
    assert OPT_MACROS in NON_BINDING_OPTIONS
    assert "scan_interval" in NON_BINDING_OPTIONS


# ================================================== reading one macro

def test_a_macro_reads_on_when_its_source_matches():
    got = read(GUEST, {"input_boolean.guest": FakeState("on")})
    assert got["state"] is True
    assert got["disposition"] == DISP_OK
    assert got["raw_state"] == "on"


def test_a_macro_reads_off_when_its_source_answers_something_else():
    got = read(GUEST, {"input_boolean.guest": FakeState("off")})
    assert got["state"] is False
    assert got["disposition"] == DISP_OK


def test_a_macro_can_watch_a_state_that_is_not_on():
    """The generalisation past an input_boolean mirror: any entity, any state
    string. A person is `not_home`, a select is whatever option was chosen."""
    assert read(AWAY, {"person.sam": FakeState("not_home")})["state"] is True
    assert read(AWAY, {"person.sam": FakeState("home")})["state"] is False


def test_the_match_is_exact_and_case_sensitive():
    """`on_state` is what the user typed into the form. An input_select
    reading "Guest" is not the same fact as one reading "guest", and matching
    loosely here would make the form lie about what it was told to watch."""
    macro = dict(GUEST, entity_id="input_select.mode", on_state="Guest")
    assert read(macro, {"input_select.mode": FakeState("Guest")})["state"] is True
    assert read(macro, {"input_select.mode": FakeState("guest")})["state"] is False


@pytest.mark.parametrize(
    "state,disposition",
    [
        (None, DISP_ABSENT),
        ("unavailable", DISP_UNREACHABLE),
        ("unknown", DISP_UNKNOWN),
        ("", DISP_UNKNOWN),
    ],
)
def test_an_unreadable_macro_is_none_and_never_false(state, disposition):
    """THE ONE THAT MATTERS. `off` is a claim that the household is not in
    guest mode; a deleted helper is not evidence for that claim. Same refusal
    as QUIET and as every source read in this component."""
    states = {} if state is None else {"input_boolean.guest": FakeState(state)}
    got = read(GUEST, states)
    assert got["state"] is None
    assert got["disposition"] == disposition


def test_an_unreadable_macro_still_names_what_it_was_looking_for():
    """Diagnosable without opening the config entry: the entity it wanted and
    the state it wanted from it are both on the reading."""
    got = read(GUEST, {})
    assert got["entity_id"] == "input_boolean.guest"
    assert got["on_state"] == "on"
    assert got["name"] == "Guest"


def test_every_macro_is_read_and_keyed_by_slug():
    c = coordinator(
        {"input_boolean.guest": FakeState("on"), "person.sam": FakeState("home")},
        [GUEST, AWAY],
    )
    got = c._read_macros()
    assert set(got) == {"guest", "away"}
    assert got["guest"]["state"] is True
    assert got["away"]["state"] is False


def test_an_unusable_row_never_reaches_the_read_path():
    """Normalised once, in __init__, so no reader below has to re-check."""
    c = coordinator({}, [GUEST, {"slug": "broken"}])
    assert [m["slug"] for m in c.macros] == ["guest"]


# ================================================= RULE 7: no axis moves

def _poll(states, macros):
    c = coordinator(states, macros)
    return asyncio.run(c._async_update_data())


def test_a_macro_that_is_on_moves_no_axis():
    """RULE 7. RULE 4's reasoning one layer out: a user-defined modifier that
    could move stage would let an installation raise its own household to
    Critical from a form, and the ramp would stop meaning what const.py says."""
    states = {"input_boolean.guest": FakeState("on")}
    without = _poll(states, [])
    with_macro = _poll(states, [GUEST])
    for axis in ("stage", "severity", "directive", "integrity", "confidence",
                 "sources_total", "sources_healthy"):
        assert with_macro[axis] == without[axis], f"a macro moved {axis}"


def test_a_macro_whose_source_is_missing_does_not_count_as_an_unhealthy_source():
    """It is not a source. An unreadable macro is a modifier nobody can read,
    not a hole in the evidence behind the axes — counting it in
    sources_unhealthy would make the feed-health sensor report a problem with
    the resolution layer over a helper somebody deleted."""
    without = _poll({}, [])
    with_macro = _poll({}, [GUEST])
    assert with_macro["sources_unhealthy"] == without["sources_unhealthy"]
    assert with_macro["sources_total"] == without["sources_total"]


def test_the_macros_are_published_under_their_own_key():
    out = _poll({"input_boolean.guest": FakeState("on")}, [GUEST])
    assert out["macros"]["guest"]["state"] is True


def test_a_macro_carries_a_since_that_survives_a_poll():
    """RULE 5's mechanism, applied to a modifier: the moment it last changed
    is persisted, not derived from last_changed."""
    c = coordinator({"input_boolean.guest": FakeState("on")}, [GUEST])
    first = asyncio.run(c._async_update_data())["macros"]["guest"]["since"]
    second = asyncio.run(c._async_update_data())["macros"]["guest"]["since"]
    assert first and first == second

    c.hass.states.set("input_boolean.guest", FakeState("off"))
    third = asyncio.run(c._async_update_data())["macros"]["guest"]["since"]
    assert third != first


def test_an_installation_with_no_macros_publishes_an_empty_set_not_a_missing_key():
    assert _poll({}, [])["macros"] == {}


# ============================================================ the entity


class FakeCoordinator:
    def __init__(self, data=None, macros=()):
        self.data = data
        self.macros = tuple(macros)

    def slug_for(self, spec):
        return spec["key"]


def _entities(macros):
    added = []

    class _Entry:
        entry_id = ENTRY_ID
        runtime_data = FakeCoordinator({}, macros)

    asyncio.run(setup_binary(None, _Entry(), added.extend))
    return added


def test_the_platform_adds_one_entity_per_macro_after_the_built_ins():
    names = [type(e).__name__ for e in _entities([GUEST, AWAY])]
    assert names == ["FeedHealth", "Quiet", "MacroState", "MacroState"]


def test_quiet_is_not_re_minted_as_a_macro():
    """QUIET already publishes binary_sensor.household_state_quiet. Migrating
    it into the macro list would hand that id to a different unique_id and
    orphan every dashboard reading it."""
    ents = _entities([GUEST])
    assert isinstance(ents[1], Quiet)
    assert ents[1]._attr_unique_id == ENTRY_ID + "_quiet"


def test_a_macro_publishes_under_a_unique_id_built_from_its_slug():
    ent = _entities([GUEST])[-1]
    assert ent._attr_unique_id == macro_unique_id(ENTRY_ID, "guest")
    assert ent._attr_unique_id == ENTRY_ID + "_macro_guest"


def test_the_id_the_entity_publishes_is_the_id_the_cleanup_looks_for():
    """__init__.py finds the registry rows of DELETED macros by this same
    format. Two copies of an id format is one copy that goes stale, and the
    failure it produces — orphaned entities nothing ever cleans up — is
    silent. Both sides read const.macro_unique_id; this ties the entity's
    published id to it so a hand-rolled string in either file goes red."""
    from household_state.const import MACRO_UNIQUE_ID_PREFIX

    ent = _entities([AWAY])[-1]
    assert ent._attr_unique_id == macro_unique_id(ENTRY_ID, AWAY["slug"])
    assert ent._attr_unique_id.startswith(ENTRY_ID + MACRO_UNIQUE_ID_PREFIX)


def test_no_two_macros_collide():
    ids = [e._attr_unique_id for e in _entities([GUEST, AWAY])]
    assert len(set(ids)) == len(ids)


def test_a_macro_takes_its_friendly_name_and_icon_from_the_row():
    guest, away = _entities([GUEST, AWAY])[-2:]
    assert guest._attr_name == "Guest"
    assert away._attr_icon == "mdi:home-export-outline"


def test_a_macro_with_no_icon_leaves_the_attribute_unset():
    """Setting `_attr_icon = None` and not setting it are different: the first
    overrides whatever the entity would otherwise resolve, the second leaves
    Home Assistant to pick. A blank icon field must do the second."""
    assert "_attr_icon" not in _entities([GUEST])[-1].__dict__
    assert "_attr_icon" in _entities([AWAY])[-1].__dict__


def test_a_macro_owns_no_device_class():
    """A device class renames both states in every surface — Detected/Clear,
    Home/Away — and the right pair depends on a meaning this file does not
    hold. `on`/`off` is the honest pair for "the thing you named is true"."""
    assert getattr(MacroState, "_attr_device_class", None) is None


def test_a_macro_entity_never_goes_unavailable():
    """The standing contract: attributes on an unavailable entity vanish, and
    that is how a broken collector reads green."""
    ent = MacroState(FakeCoordinator(None), ENTRY_ID, GUEST)
    assert ent.available is True


@pytest.mark.parametrize("data", [None, {}, {"macros": {}}, {"macros": None}])
def test_a_macro_reads_none_before_the_first_poll_lands(data):
    ent = MacroState(FakeCoordinator(data), ENTRY_ID, GUEST)
    assert ent.is_on is None
    assert isinstance(ent.extra_state_attributes, dict)


def test_a_macro_publishes_its_reading():
    reading = {
        "slug": "guest", "name": "Guest", "entity_id": "input_boolean.guest",
        "on_state": "on", "icon": None, "state": True, "raw_state": "on",
        "disposition": DISP_OK, "since": "2026-09-11T02:00:00+00:00",
    }
    ent = MacroState(FakeCoordinator({"macros": {"guest": reading}}), ENTRY_ID, GUEST)
    assert ent.is_on is True
    attrs = ent.extra_state_attributes
    assert attrs["slug"] == "guest"
    assert attrs["source_entity_id"] == "input_boolean.guest"
    assert attrs["raw_state"] == "on"
    assert attrs["on_state"] == "on"
    assert attrs["disposition"] == DISP_OK
    assert attrs["since"] == "2026-09-11T02:00:00+00:00"


def test_a_macro_states_both_what_it_saw_and_what_it_wanted():
    """A macro reading `off` because the form says "home" and the entity says
    "Home" is diagnosable from these two attributes and from nothing else."""
    reading = {"entity_id": "person.sam", "raw_state": "Home", "on_state": "home",
               "state": False, "disposition": DISP_OK}
    ent = MacroState(
        FakeCoordinator({"macros": {"away": reading}}), ENTRY_ID, dict(AWAY, slug="away")
    )
    attrs = ent.extra_state_attributes
    assert (attrs["raw_state"], attrs["on_state"]) == ("Home", "home")


def test_the_entity_is_none_not_false_when_the_reading_says_so():
    reading = {"state": None, "disposition": DISP_ABSENT}
    ent = MacroState(FakeCoordinator({"macros": {"guest": reading}}), ENTRY_ID, GUEST)
    assert ent.is_on is None


def test_the_assertions_can_fail():
    """A check that cannot go red is not a check."""
    # The reading really is looked up by slug, rather than the first row.
    ent = MacroState(
        FakeCoordinator({"macros": {"away": {"state": True}}}), ENTRY_ID, GUEST
    )
    assert ent.is_on is None
    # Normalisation really does reject, rather than accepting everything.
    assert normalize_macro(dict(GUEST)) is not None
