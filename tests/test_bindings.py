"""Which entity supplies a source is CONFIGURATION (GH #16).

A SOURCES row says what a source MEANS — its axis, its kind, how severity is
read. Which entity supplies it is an installation detail. Hardcoding that made
this component readable by exactly one household: every id resolved to `absent`
anywhere else, and `absent` is the state the component exists to make loud.

These tests pin the resolution rules, not the estate's particular ids — so they
keep passing when the defaults are removed from const.py entirely.
"""

import asyncio

import pytest

from household_state.const import (
    BINDABLE,
    BINDABLE_TEXT,
    BIND_PERIMETER,
    BIND_QUIET,
    DISP_ABSENT,
    DISP_OK,
    SOURCES,
    bind_key,
)
from household_state.coordinator import HouseholdStateCoordinator

from ha_stubs import (
    FakeEntityRegistry,
    FakeHass,
    FakeLabelRegistry,
    FakeRegistryEntry,
    FakeServices,
    FakeState,
)


def coordinator(states=None, bindings=None, **kw):
    c = HouseholdStateCoordinator(FakeHass(states, **kw), 3, bindings)
    c.async_arm_logging()
    return c


def row(key):
    return next(s for s in SOURCES if s["key"] == key)


# ============================================================ the resolver

def test_an_unset_binding_falls_through_to_the_rows_own_default():
    c = coordinator({})
    spec = row("ntas")
    assert c._spec_entity(spec) == spec.get("entity_id")


def test_a_set_binding_wins_over_the_default():
    spec = row("ntas")
    c = coordinator({}, {bind_key("ntas", "entity_id"): "sensor.somewhere_else"})
    assert c._spec_entity(spec) == "sensor.somewhere_else"


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_cleared_binding_is_unset_not_a_blank_entity_id(blank):
    """An options flow hands back "" for a field the user cleared. Reading that
    as an entity id would look up the entity named "", which reports `absent`
    and is indistinguishable from a deleted entity. Those must not collapse."""
    spec = row("ntas")
    c = coordinator({}, {bind_key("ntas", "entity_id"): blank})
    assert c._spec_entity(spec) == spec.get("entity_id")


def test_a_binding_only_affects_the_row_it_names():
    """Two rows deliberately share one entity (local_nws and nws_cap both read
    the threat sensor). Rebinding one must not move the other."""
    c = coordinator({}, {bind_key("local_nws", "entity_id"): "sensor.moved"})
    assert c._spec_entity(row("local_nws")) == "sensor.moved"
    assert c._spec_entity(row("nws_cap")) == row("nws_cap").get("entity_id")


def test_the_read_actually_follows_the_binding():
    """Not just the resolver — the read itself. A binding the reader ignores is
    a setting that silently does nothing."""
    c = coordinator({"sensor.moved": FakeState("Elevated", severity=5)},
                    {bind_key("ntas", "entity_id"): "sensor.moved"})
    r = c._read_source(row("ntas"))
    assert r["disposition"] == DISP_OK
    assert r["severity"] == 5
    assert r["entity_id"] == "sensor.moved", "the reading must report where it read"


def test_an_unbound_row_whose_default_is_missing_is_absent_not_ok():
    """RULE 2 still governs: a source that cannot be read never contributes 0."""
    r = coordinator({})._read_source(row("ntas"))
    assert r["disposition"] == DISP_ABSENT
    assert r["severity"] is None


# ================================================== the two non-SOURCES reads

def test_quiet_follows_its_binding_and_reports_which_entity_it_read():
    c = coordinator({"input_boolean.nap": FakeState("on")},
                    {bind_key(BIND_QUIET, "entity_id"): "input_boolean.nap"})
    out = c._read_quiet()
    assert out["quiet"] is True
    assert out["quiet_source_entity_id"] == "input_boolean.nap"


def test_an_unreadable_bound_quiet_is_none_and_still_names_the_entity():
    c = coordinator({}, {bind_key(BIND_QUIET, "entity_id"): "input_boolean.nap"})
    out = c._read_quiet()
    assert out["quiet"] is None
    assert out["quiet_source_entity_id"] == "input_boolean.nap"


def test_the_perimeter_label_follows_its_binding():
    ereg = FakeEntityRegistry([FakeRegistryEntry("binary_sensor.door",
                                                 labels=("doors",))])
    c = coordinator({"binary_sensor.door": FakeState("off")},
                    {bind_key(BIND_PERIMETER, "label"): "doors"},
                    entity_registry=ereg, label_registry=FakeLabelRegistry(["doors"]))
    r = c._read_source(row("perimeter_open"))
    assert r["disposition"] == DISP_OK
    assert r["watched_count"] == 1


def test_an_unresolvable_bound_label_names_the_label_it_looked_for():
    """The detail has to say WHICH label, or a mis-typed binding is unfindable."""
    c = coordinator({}, {bind_key(BIND_PERIMETER, "label"): "typo_label"},
                    label_registry=FakeLabelRegistry([]))
    r = c._read_source(row("perimeter_open"))
    assert r["disposition"] == DISP_ABSENT
    assert "typo_label" in r["detail"]


def test_the_notify_service_identity_is_bindable():
    spec = row("notify_health")
    c = coordinator({})
    c.hass.services = FakeServices([("notify", "elsewhere")])
    c._bindings = {bind_key("notify_health", "service_domain"): "notify",
                   bind_key("notify_health", "service"): "elsewhere"}
    r = c._read_source(spec)
    assert r["integrity"] == "ok"


def test_an_unregistered_bound_service_names_it_in_the_detail():
    spec = row("notify_health")
    c = coordinator({})
    c.hass.services = FakeServices([])
    c._bindings = {bind_key("notify_health", "service_domain"): "notify",
                   bind_key("notify_health", "service"): "gone"}
    r = c._read_source(spec)
    assert r["integrity"] == "degraded"
    assert "notify.gone" in r["integrity_detail"]


# ================================================= the declaration and flow

def test_every_bindable_names_a_real_source_row_or_a_pseudo_key():
    """A binding offered in the options flow that no reader consults is a
    setting that silently does nothing."""
    keys = {s["key"] for s in SOURCES} | {BIND_QUIET, BIND_PERIMETER}
    for source_key, field, _domain, _label in BINDABLE:
        assert source_key in keys, f"{source_key} is not a source"
    for source_key, field, _label in BINDABLE_TEXT:
        assert source_key in keys, f"{source_key} is not a source"


def test_every_bindable_entity_row_actually_carries_that_field():
    for source_key, field, _domain, _label in BINDABLE:
        if source_key in (BIND_QUIET, BIND_PERIMETER):
            continue
        assert field in row(source_key), f"{source_key} has no {field}"


def test_no_binding_is_declared_twice():
    seen = [bind_key(k, f) for k, f, _d, _l in BINDABLE]
    seen += [bind_key(k, f) for k, f, _l in BINDABLE_TEXT]
    assert len(seen) == len(set(seen)), "duplicate binding key"


def test_the_options_flow_offers_every_binding_and_round_trips_it():
    """THE MERGE GUARD. The options flow is one step today, so what it returns
    IS the whole option set and it cannot drop anything. If it ever grows a
    second step, async_create_entry(data=...) replaces entry.options wholesale
    (TOOLS.md) and a step that forgets to merge silently deletes every binding
    another step owns. This is the test that goes red when that happens."""
    import asyncio

    from household_state.config_flow import HouseholdStateOptionsFlow

    every = {bind_key(k, f): f"sensor.bound_{k}_{f}" for k, f, _d, _l in BINDABLE}
    every.update({bind_key(k, f): f"text_{k}_{f}" for k, f, _l in BINDABLE_TEXT})
    every["scan_interval"] = 11

    class _Entry:
        options = dict(every)

    flow = HouseholdStateOptionsFlow()
    flow.config_entry = _Entry()

    form = asyncio.run(flow.async_step_init(None))
    offered = set(form["data_schema"].schema)
    for key in every:
        assert any(str(k) == key for k in offered), f"{key} not offered"

    saved = asyncio.run(flow.async_step_init(every))
    assert saved["type"] == "create_entry"
    assert saved["data"] == every, "a binding was dropped on save"


def test_bindings_reach_the_coordinator_from_the_entry():
    """End to end: options on the entry become bindings on the coordinator,
    and scan_interval is NOT mistaken for one."""
    import household_state

    class _Hass(FakeHass):
        def __init__(self):
            super().__init__({})
            self.config_entries = _Mgr()
            self.data = {}

    class _Mgr:
        async def async_forward_entry_setups(self, entry, platforms):
            pass

    class _Entry:
        entry_id = "01E"
        options = {"scan_interval": 9,
                   bind_key("ntas", "entity_id"): "sensor.bound_ntas"}
        runtime_data = None

        def async_on_unload(self, fn):
            return fn

        def add_update_listener(self, fn):
            return lambda: None

    hass, entry = _Hass(), _Entry()
    asyncio.run(household_state.async_setup_entry(hass, entry))
    c = entry.runtime_data
    assert c.update_interval.total_seconds() == 9
    assert "scan_interval" not in c._bindings, "scan_interval leaked into bindings"
    assert c._spec_entity(row("ntas")) == "sensor.bound_ntas"


def test_the_assertions_can_fail():
    """LAW §4."""
    spec = row("ntas")
    # The binding must actually be consulted, not merely stored.
    assert coordinator({})._spec_entity(spec) == spec.get("entity_id")
    assert coordinator({}, {bind_key("ntas", "entity_id"): "sensor.x"}) \
        ._spec_entity(spec) == "sensor.x"
    # And bind_key must actually namespace by source, or every row would
    # collide on a shared field name like "entity_id".
    assert bind_key("a", "entity_id") != bind_key("b", "entity_id")


# ============================================ the published slug (GH #19)

def test_the_slug_defaults_to_the_key():
    c = coordinator({})
    for spec in SOURCES:
        assert c.slug_for(spec) == spec["key"]


def test_a_bound_slug_preserves_a_legacy_published_id():
    """THE WHOLE POINT. A key renamed in the repo would otherwise mint a new
    entity and orphan the one an installation already publishes — HA never
    reclaims an id, so every dashboard reading the old one would be reading
    something that belongs to nothing.
    """
    from household_state.sensor import SourceSensor

    spec = row("local_nws")
    c = coordinator({}, {bind_key("local_nws", "slug"): "nws_union"})
    ent = SourceSensor(c, "01ENTRY", spec)
    assert ent._attr_unique_id == "01ENTRY_src_nws_union"
    assert c.slug_for(spec) == "nws_union"


def test_an_unbound_slug_mints_the_id_from_the_key():
    from household_state.sensor import SourceSensor

    ent = SourceSensor(coordinator({}), "01ENTRY", row("local_nws"))
    assert ent._attr_unique_id == "01ENTRY_src_local_nws"


def test_the_driver_token_is_the_published_slug_not_the_internal_key():
    """A surface matches `driver` against the per-source entity it also
    renders. If the stage sensor named the internal key while the entity
    carried the bound slug, nothing on glass could join them."""
    from household_state.resolver import resolve

    c = coordinator({"sensor.threat": FakeState("Elevated", severity=5)},
                    {bind_key("local_nws", "entity_id"): "sensor.threat",
                     bind_key("local_nws", "slug"): "nws_union"})
    reading = c._read_source(row("local_nws"))
    assert reading["slug"] == "nws_union"
    out = resolve([reading])
    assert out["driver"] == "nws_union", "driver must be the published slug"


def test_every_row_can_have_its_slug_bound():
    """Offered for every source, because which key gets renamed upstream is not
    knowable in advance."""
    from household_state.const import slug_bindings

    offered = {k for k, f, _l in slug_bindings()}
    assert offered == {s["key"] for s in SOURCES}
    assert all(f == "slug" for _k, f, _l in slug_bindings())


def test_the_slug_assertions_can_fail():
    """LAW §4."""
    spec = row("local_nws")
    assert coordinator({}).slug_for(spec) == "local_nws"
    assert coordinator({}, {bind_key("local_nws", "slug"): "x"}).slug_for(spec) == "x"
    # A blank slug must fall through, not publish an empty id tail.
    assert coordinator({}, {bind_key("local_nws", "slug"): "  "}) \
        .slug_for(spec) == "local_nws"
