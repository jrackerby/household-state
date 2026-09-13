"""The config flow, exercised. Quality scale: `config-flow-test-coverage`.

config_flow.py sat at 0% when this repo was gap-listed (#2), which is the
rule's floor exactly inverted: the flow is the one code path every installer
runs, and it was the one path nothing here touched.

WHAT THIS COVERS AND WHAT IT DOES NOT. It drives this repo's own flow logic
against tests/ha_stubs' flow bases: the single-instance abort, the empty user
schema, the options default read back off the entry, and the 1-300 bound on
scan_interval. It proves nothing about core's flow manager — step dispatch,
the translation lookup behind `reason`, or how an OptionsFlow is handed its
entry in the HA version of the day. That is ha_stubs' standing trade, taken
here for the same reason it is taken for the coordinator: a green result stays
attributable to this repo rather than to a core release moving under it.

The `single_instance_allowed` abort reason is separately tied to
translations/en.json below, because a reason string with no translation behind
it renders as a raw key in the UI and no amount of flow coverage sees that.
Every step id, menu option and error key is tied to it the same way, and for
the same reason: the flow returns the key whether or not a string exists.

THE MERGE GUARD IS THE POINT OF HALF THIS FILE. The options flow grew from one
step to a menu when macro states arrived, and `async_create_entry(data=...)`
REPLACES entry.options wholesale — so a step that returns only its own fields
silently deletes everything the other steps own, and nothing notices until an
installation reboots into unbound sources. Every terminal step is exercised
here against a fully populated entry for exactly that.
"""

import json
import pathlib

import pytest
import voluptuous as vol

from household_state.config_flow import (
    HouseholdStateConfigFlow,
    HouseholdStateOptionsFlow,
)
from household_state.const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MACRO_RENAMEABLE_FIELDS,
    OPT_MACROS,
)

_ONE_MACRO = {
    OPT_MACROS: [
        {"slug": "guest", "name": "Guest", "entity_id": "input_boolean.guest",
         "on_state": "on", "icon": None},
    ]
}

_TWO_MACROS = {
    OPT_MACROS: _ONE_MACRO[OPT_MACROS] + [
        {"slug": "away", "name": "Away", "entity_id": "person.sam",
         "on_state": "not_home", "icon": "mdi:home-export-outline"},
    ]
}

ROOT = pathlib.Path(__file__).resolve().parent.parent


class _Entry:
    """Stands in for a configured entry; only `options` is read."""

    def __init__(self, options=None):
        self.options = dict(options or {})


def _flow(current_entries=()):
    flow = HouseholdStateConfigFlow()
    flow._current_entries = current_entries
    return flow


def _options_flow(options=None):
    flow = HouseholdStateOptionsFlow()
    flow.config_entry = _Entry(options)
    return flow


# --------------------------------------------------------------- user step

def test_the_flow_is_registered_against_this_domain():
    """`domain=DOMAIN` on the class keyword. Registered against nothing would
    still import, still pass every other test here, and never appear in the
    Add Integration list."""
    assert HouseholdStateConfigFlow.domain == DOMAIN


def test_the_first_run_shows_a_form():
    import asyncio

    result = asyncio.run(_flow().async_step_user(None))
    assert result["type"] == "form"
    assert result["step_id"] == "user"


def test_the_user_step_asks_for_nothing():
    """There is no host, credential or endpoint. An empty schema is the whole
    reason `test-before-configure` is exempt in quality_scale.yaml — if this
    ever grows a field, that exemption stops being true."""
    import asyncio

    result = asyncio.run(_flow().async_step_user(None))
    assert result["data_schema"]({}) == {}


def test_submitting_creates_the_entry():
    import asyncio

    result = asyncio.run(_flow().async_step_user({}))
    assert result["type"] == "create_entry"
    assert result["title"] == "Household State"
    # Nothing is stored in `data`: the one setting lives in options, so a
    # reconfigure never has to migrate it.
    assert result["data"] == {}


def test_a_second_entry_is_refused():
    """manifest declares single_config_entry, and the flow enforces it. There
    is one household."""
    import asyncio

    result = asyncio.run(_flow(current_entries=(_Entry(),)).async_step_user(None))
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


def test_the_refusal_happens_before_the_form_is_offered():
    """Aborting only on submit would show a form that cannot succeed."""
    import asyncio

    result = asyncio.run(_flow(current_entries=(_Entry(),)).async_step_user({}))
    assert result["type"] == "abort"


# ------------------------------------------------------------ options step

def test_options_offers_the_current_value_as_the_default():
    import asyncio

    result = asyncio.run(_options_flow({"scan_interval": 17}).async_step_bindings(None))
    assert result["type"] == "form"
    assert result["data_schema"]({}) == {"scan_interval": 17}


def test_options_falls_back_to_the_shipped_default():
    import asyncio

    result = asyncio.run(_options_flow().async_step_bindings(None))
    assert result["data_schema"]({}) == {"scan_interval": DEFAULT_SCAN_INTERVAL}


@pytest.mark.parametrize("value", [1, 3, 300])
def test_the_accepted_range_is_inclusive_at_both_ends(value):
    import asyncio

    result = asyncio.run(_options_flow().async_step_bindings(None))
    assert result["data_schema"]({"scan_interval": value}) == {"scan_interval": value}


@pytest.mark.parametrize("value", [0, -1, 301])
def test_out_of_range_is_refused(value):
    """A poll interval longer than the fall dwell makes the dwell meaningless
    (const.py), and 0 would spin. The bound is load-bearing, not decoration."""
    import asyncio

    result = asyncio.run(_options_flow().async_step_bindings(None))
    with pytest.raises(vol.Invalid):
        result["data_schema"]({"scan_interval": value})


def test_a_string_is_coerced_not_refused():
    """The UI hands back a string. vol.Coerce(int) is why that works."""
    import asyncio

    result = asyncio.run(_options_flow().async_step_bindings(None))
    assert result["data_schema"]({"scan_interval": "30"}) == {"scan_interval": 30}


def test_submitting_options_stores_them():
    import asyncio

    result = asyncio.run(
        _options_flow().async_step_bindings({"scan_interval": 42})
    )
    assert result["type"] == "create_entry"
    assert result["data"] == {"scan_interval": 42}


# ----------------------------------------------------------------- the menu

def test_the_options_flow_opens_on_a_menu():
    """`init` is a menu, not a form. The bindings form is thirty-odd fields
    long and a macro state is a row rather than a field, so the two cannot
    share one form."""
    import asyncio

    result = asyncio.run(_options_flow().async_step_init())
    assert result["type"] == "menu"
    assert result["step_id"] == "init"


def test_a_fresh_entry_is_offered_only_what_it_can_do():
    """No macros defined, so nothing to edit and nothing to remove. A menu
    entry that leads to an empty picker is a dead end found by clicking."""
    import asyncio

    result = asyncio.run(_options_flow().async_step_init())
    assert result["menu_options"] == ["bindings", "macro_add"]


def test_edit_and_remove_appear_once_a_macro_exists():
    import asyncio

    result = asyncio.run(_options_flow(_ONE_MACRO).async_step_init())
    assert result["menu_options"] == [
        "bindings", "macro_add", "macro_edit", "macro_remove"
    ]


def test_a_macro_row_that_cannot_be_used_does_not_unlock_the_menu():
    """`.storage` is hand-editable. A row with no entity id publishes nothing,
    so it must not be offered for editing either — the picker would list a
    macro that no entity layer knows about."""
    import asyncio

    flow = _options_flow({OPT_MACROS: [{"slug": "guest", "name": "Guest"}]})
    assert asyncio.run(flow.async_step_init())["menu_options"] == [
        "bindings", "macro_add"
    ]


# --------------------------------------------------------- macro: defining

def test_the_add_form_offers_exactly_the_editable_fields():
    """Tied to const.MACRO_RENAMEABLE_FIELDS, not to a list written twice: a
    field on the form that nothing stores is a setting that silently does
    nothing, and one stored but never offered cannot be changed."""
    import asyncio

    form = asyncio.run(_options_flow().async_step_macro_add(None))
    assert form["type"] == "form"
    assert form["step_id"] == "macro_add"
    offered = {str(k) for k in form["data_schema"].schema}
    assert offered == set(MACRO_RENAMEABLE_FIELDS)


def test_neither_macro_form_offers_a_slug():
    """#19 one level down: the slug is the tail of the published entity id and
    Home Assistant never reclaims one. It is derived once and frozen, which is
    only true while it stays off the editable list."""
    import asyncio

    assert "slug" not in MACRO_RENAMEABLE_FIELDS
    add = asyncio.run(_options_flow().async_step_macro_add(None))
    assert "slug" not in {str(k) for k in add["data_schema"].schema}


def test_on_state_defaults_to_on():
    import asyncio

    form = asyncio.run(_options_flow().async_step_macro_add(None))
    assert form["data_schema"]({"name": "Guest", "entity_id": "input_boolean.g"})[
        "on_state"
    ] == "on"


def test_defining_a_macro_stores_it_with_a_slug_derived_from_the_name():
    import asyncio

    result = asyncio.run(
        _options_flow().async_step_macro_add(
            {"name": "Guest Mode", "entity_id": "input_boolean.guest_mode"}
        )
    )
    assert result["type"] == "create_entry"
    assert result["data"][OPT_MACROS] == [
        {
            "slug": "guest_mode",
            "name": "Guest Mode",
            "entity_id": "input_boolean.guest_mode",
            "on_state": "on",
            "icon": None,
        }
    ]


def test_a_macro_can_watch_a_state_string_that_is_not_on():
    """The generalisation that makes this worth more than an input_boolean
    mirror: a macro reads any entity against any state string."""
    import asyncio

    result = asyncio.run(
        _options_flow().async_step_macro_add(
            {"name": "Away", "entity_id": "person.sam", "on_state": "not_home",
             "icon": "mdi:home-export-outline"}
        )
    )
    assert result["data"][OPT_MACROS][0]["on_state"] == "not_home"
    assert result["data"][OPT_MACROS][0]["icon"] == "mdi:home-export-outline"


def test_a_cleared_on_state_is_not_stored_as_the_empty_string():
    """No entity ever reports "", so storing it would define a macro that can
    never be true — and the form would look like it had been filled in."""
    import asyncio

    result = asyncio.run(
        _options_flow().async_step_macro_add(
            {"name": "Away", "entity_id": "person.sam", "on_state": "  ",
             "icon": "  "}
        )
    )
    assert result["data"][OPT_MACROS][0]["on_state"] == "on"
    assert result["data"][OPT_MACROS][0]["icon"] is None


def test_defining_a_second_macro_keeps_the_first():
    import asyncio

    result = asyncio.run(
        _options_flow(_ONE_MACRO).async_step_macro_add(
            {"name": "Away", "entity_id": "person.sam"}
        )
    )
    assert [m["slug"] for m in result["data"][OPT_MACROS]] == ["guest", "away"]


@pytest.mark.parametrize(
    "user_input,error",
    [
        ({"name": "!!!", "entity_id": "input_boolean.x"}, "invalid_name"),
        ({"name": "Quiet", "entity_id": "input_boolean.x"}, "reserved_name"),
        ({"name": "Feed health", "entity_id": "input_boolean.x"}, "reserved_name"),
        ({"name": "Stage", "entity_id": "input_boolean.x"}, "reserved_name"),
        ({"name": "Party", "entity_id": "  "}, "entity_required"),
    ],
)
def test_a_macro_that_cannot_be_published_is_refused(user_input, error):
    """Each of these would otherwise mint an entity that collides with one
    this integration already publishes, or an entity id built from nothing."""
    import asyncio

    result = asyncio.run(_options_flow(_ONE_MACRO).async_step_macro_add(user_input))
    assert result["type"] == "form"
    assert result["errors"] == {"base": error}


def test_a_duplicate_slug_is_refused():
    """Two rows claiming one entity id publish one entity whose source depends
    on iteration order."""
    import asyncio

    result = asyncio.run(
        _options_flow(_ONE_MACRO).async_step_macro_add(
            {"name": "guest", "entity_id": "input_boolean.other"}
        )
    )
    assert result["errors"] == {"base": "duplicate_name"}


def test_a_refused_form_comes_back_with_what_was_typed():
    """Re-typing four fields because one was wrong is how a form teaches
    people to give up on it."""
    import asyncio

    typed = {"name": "guest", "entity_id": "input_boolean.other",
             "on_state": "home", "icon": "mdi:account"}
    result = asyncio.run(_options_flow(_ONE_MACRO).async_step_macro_add(typed))
    schema = result["data_schema"].schema
    suggested = {
        str(k): k.description.get("suggested_value")
        for k in schema
        if getattr(k, "description", None)
    }
    assert suggested["entity_id"] == "input_boolean.other"
    assert suggested["name"] == "guest"


def test_nothing_is_written_when_the_form_is_refused():
    """A refusal returns a form, never a create_entry — the difference between
    showing an error and storing the broken row and showing an error."""
    import asyncio

    flow = _options_flow(_ONE_MACRO)
    result = asyncio.run(flow.async_step_macro_add({"name": "Quiet",
                                                    "entity_id": "input_boolean.x"}))
    assert result["type"] != "create_entry"


# ----------------------------------------------------------- macro: editing

def test_the_edit_picker_lists_every_macro_by_name():
    import asyncio

    form = asyncio.run(_options_flow(_TWO_MACROS).async_step_macro_edit(None))
    assert form["step_id"] == "macro_edit"
    container = [k for k in form["data_schema"].schema][0]
    validator = form["data_schema"].schema[container]
    assert validator.container == {"guest": "Guest", "away": "Away"}


def test_picking_a_macro_opens_its_detail_form_prefilled():
    import asyncio

    flow = _options_flow(_TWO_MACROS)
    form = asyncio.run(flow.async_step_macro_edit({"slug": "away"}))
    assert form["step_id"] == "macro_detail"
    assert form["description_placeholders"]["slug"] == "away"
    suggested = {
        str(k): k.description.get("suggested_value")
        for k in form["data_schema"].schema
        if getattr(k, "description", None)
    }
    assert suggested["entity_id"] == "person.sam"


def test_the_detail_form_offers_the_same_fields_as_the_add_form():
    """One schema behind both. Two would drift into a field the add step
    accepts and the edit step silently drops."""
    import asyncio

    flow = _options_flow(_TWO_MACROS)
    form = asyncio.run(flow.async_step_macro_edit({"slug": "guest"}))
    assert {str(k) for k in form["data_schema"].schema} == set(MACRO_RENAMEABLE_FIELDS)


def test_editing_rebinds_the_source_and_keeps_the_slug():
    """The whole reason the slug is frozen: a rename must not mint a second
    entity and orphan the one every dashboard already reads."""
    import asyncio

    flow = _options_flow(_TWO_MACROS)
    asyncio.run(flow.async_step_macro_edit({"slug": "guest"}))
    result = asyncio.run(
        flow.async_step_macro_detail(
            {"name": "Guests", "entity_id": "schedule.guests", "on_state": "on"}
        )
    )
    stored = {m["slug"]: m for m in result["data"][OPT_MACROS]}
    assert stored["guest"]["name"] == "Guests"
    assert stored["guest"]["entity_id"] == "schedule.guests"
    assert set(stored) == {"guest", "away"}


def test_editing_one_macro_does_not_reorder_or_touch_the_others():
    import asyncio

    flow = _options_flow(_TWO_MACROS)
    asyncio.run(flow.async_step_macro_edit({"slug": "away"}))
    result = asyncio.run(
        flow.async_step_macro_detail(
            {"name": "Away", "entity_id": "person.sam", "on_state": "away"}
        )
    )
    assert [m["slug"] for m in result["data"][OPT_MACROS]] == ["guest", "away"]
    assert result["data"][OPT_MACROS][0] == _TWO_MACROS[OPT_MACROS][0]


@pytest.mark.parametrize(
    "user_input,error",
    [
        ({"name": "Guest", "entity_id": "   "}, "entity_required"),
        ({"name": "   ", "entity_id": "input_boolean.guest"}, "invalid_name"),
    ],
)
def test_an_edit_that_would_break_the_macro_is_refused(user_input, error):
    import asyncio

    flow = _options_flow(_TWO_MACROS)
    asyncio.run(flow.async_step_macro_edit({"slug": "guest"}))
    result = asyncio.run(flow.async_step_macro_detail(user_input))
    assert result["type"] == "form"
    assert result["errors"] == {"base": error}


def test_the_pickers_fall_back_to_the_menu_when_there_is_nothing_to_pick():
    """Reachable by opening two browser tabs and deleting the last macro in
    one of them. A picker over an empty set would render an unsubmittable
    form."""
    import asyncio

    flow = _options_flow()
    assert asyncio.run(flow.async_step_macro_edit(None))["type"] == "menu"
    assert asyncio.run(flow.async_step_macro_remove(None))["type"] == "menu"


def test_a_detail_form_for_a_macro_that_vanished_falls_back_to_the_menu():
    """Same two tabs, one step later: the picker resolved, the entry was
    reconfigured, and writing here would store a slug nothing declares."""
    import asyncio

    flow = _options_flow(_TWO_MACROS)
    flow._editing = "deleted_elsewhere"
    assert asyncio.run(flow.async_step_macro_detail(None))["type"] == "menu"


# ---------------------------------------------------------- macro: removing

def test_removing_needs_a_confirmation():
    """It deletes a published entity: every card, trigger and template reading
    binary_sensor.household_state_<slug> stops resolving."""
    import asyncio

    result = asyncio.run(
        _options_flow(_TWO_MACROS).async_step_macro_remove(
            {"slug": "guest", "confirm": False}
        )
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "not_confirmed"}


def test_a_confirmed_removal_drops_exactly_one_macro():
    import asyncio

    result = asyncio.run(
        _options_flow(_TWO_MACROS).async_step_macro_remove(
            {"slug": "guest", "confirm": True}
        )
    )
    assert [m["slug"] for m in result["data"][OPT_MACROS]] == ["away"]


def test_the_remove_form_defaults_to_not_confirmed():
    import asyncio

    form = asyncio.run(_options_flow(_TWO_MACROS).async_step_macro_remove(None))
    assert form["data_schema"]({"slug": "guest"})["confirm"] is False


# ------------------------------------------------------------- the merge guard

def _populated():
    """An entry carrying one of everything: the interval, a binding, a slug
    override and two macros."""
    return {
        "scan_interval": 11,
        "ntas.entity_id": "sensor.ntas",
        "local_nws.slug": "old_name",
        OPT_MACROS: list(_TWO_MACROS[OPT_MACROS]),
    }


@pytest.mark.parametrize(
    "step,user_input",
    [
        ("async_step_bindings", {"scan_interval": 30}),
        ("async_step_macro_add", {"name": "Party", "entity_id": "input_boolean.p"}),
        ("async_step_macro_remove", {"slug": "guest", "confirm": True}),
    ],
)
def test_no_step_can_drop_an_option_another_step_owns(step, user_input):
    """THE MERGE GUARD. async_create_entry(data=...) REPLACES entry.options, so
    a step returning only its own fields silently deletes the rest. Every
    terminal step routes through one merge helper; this is what goes red if a
    later step reaches for async_create_entry directly."""
    import asyncio

    options = _populated()
    result = asyncio.run(getattr(_options_flow(options), step)(user_input))
    assert result["type"] == "create_entry"
    for key in ("ntas.entity_id", "local_nws.slug"):
        assert result["data"][key] == options[key], f"{key} was dropped"
    assert OPT_MACROS in result["data"]


def test_editing_a_macro_does_not_drop_the_bindings():
    import asyncio

    options = _populated()
    flow = _options_flow(options)
    asyncio.run(flow.async_step_macro_edit({"slug": "guest"}))
    result = asyncio.run(
        flow.async_step_macro_detail(
            {"name": "Guest", "entity_id": "input_boolean.guest", "on_state": "on"}
        )
    )
    assert result["data"]["ntas.entity_id"] == "sensor.ntas"
    assert result["data"]["scan_interval"] == 11


def test_the_bindings_step_does_not_drop_the_macros():
    """The direction that is easy to get wrong: the bindings form knows
    nothing about macros and returns a dict that does not mention them."""
    import asyncio

    result = asyncio.run(
        _options_flow(_populated()).async_step_bindings({"scan_interval": 5})
    )
    assert result["data"][OPT_MACROS] == _TWO_MACROS[OPT_MACROS]


# ------------------------------------------------- the flow's other surface

def test_the_options_flow_is_reachable_from_the_config_flow():
    """async_get_options_flow is a staticmethod + callback. If it stopped
    returning the options flow, the entry would simply show no Configure
    button and nothing would raise."""
    got = HouseholdStateConfigFlow.async_get_options_flow(_Entry())
    assert isinstance(got, HouseholdStateOptionsFlow)


def test_every_abort_reason_has_a_translation():
    """A reason with no string behind it renders as a raw key in the UI, and
    no amount of flow coverage sees that — the flow returns the key either
    way."""
    translations = json.loads(
        (ROOT / "translations" / "en.json").read_text(encoding="utf-8")
    )
    declared = translations["config"]["abort"]
    assert "single_instance_allowed" in declared
    assert declared["single_instance_allowed"].strip()


def test_every_step_and_error_the_flow_can_return_has_a_translation():
    """A step id with no strings behind it renders as a blank dialog and an
    error key renders as the key itself. The flow returns them either way, so
    no amount of flow coverage sees this — only a comparison against the file
    the UI actually reads does."""
    translations = json.loads(
        (ROOT / "translations" / "en.json").read_text(encoding="utf-8")
    )
    steps = translations["options"]["step"]

    declared_steps = {
        name.split("async_step_", 1)[1]
        for name in dir(HouseholdStateOptionsFlow)
        if name.startswith("async_step_")
    }
    for step in declared_steps:
        assert step in steps, f"step {step} has no strings"

    # The menu names its options; each has to resolve to a step with strings.
    for option in steps["init"]["menu_options"]:
        assert option in steps, f"menu option {option} has no strings"

    declared_errors = set(translations["options"]["error"])
    source = (ROOT / "config_flow.py").read_text(encoding="utf-8")
    for key in ("invalid_name", "reserved_name", "duplicate_name",
                "entity_required", "not_confirmed"):
        assert f'"{key}"' in source, f"{key} is no longer raised"
        assert key in declared_errors, f"{key} has no string"


def test_every_macro_form_field_is_labelled():
    """An unlabelled field renders as its raw key — `on_state` rather than
    "State that means on" — which is exactly the kind of thing that is obvious
    to whoever wrote the schema and to nobody else."""
    translations = json.loads(
        (ROOT / "translations" / "en.json").read_text(encoding="utf-8")
    )
    steps = translations["options"]["step"]
    for step in ("macro_add", "macro_detail"):
        for field in ("name", "entity_id", "on_state", "icon"):
            assert field in steps[step]["data"], f"{step}.{field} is unlabelled"


def test_the_assertions_can_fail():
    """a check that cannot go red is not a check."""
    import asyncio

    # The schema really does validate, rather than accepting anything.
    result = asyncio.run(_options_flow().async_step_bindings(None))
    with pytest.raises(vol.Invalid):
        result["data_schema"]({"scan_interval": 10_000})
    # The macro store really is read back off the entry, rather than the add
    # step starting from an empty list every time.
    assert _options_flow(_TWO_MACROS)._macros() != _options_flow()._macros()
    # The single-instance guard really does depend on there being an entry.
    assert asyncio.run(_flow().async_step_user(None))["type"] == "form"
    assert asyncio.run(
        _flow(current_entries=(_Entry(),)).async_step_user(None)
    )["type"] == "abort"
