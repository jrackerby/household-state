"""Setup and teardown: the order that matters, and what is torn down with it.

__init__.py was at 42%. Two of its lines carry rules that are invisible by
reading — RULE 5's ordering, and the logging arm's registration — and both are
the kind of thing a refactor reorders without noticing.
"""

import asyncio

import pytest

import ha_stubs
import household_state
from household_state.const import DEFAULT_SCAN_INTERVAL, PLATFORMS
from household_state.coordinator import HouseholdStateCoordinator


class FakeConfigEntriesManager:
    def __init__(self):
        self.forwarded = []
        self.unloaded = []
        self.reloaded = []
        self.unload_result = True

    async def async_forward_entry_setups(self, entry, platforms):
        self.forwarded.append((entry, tuple(platforms)))

    async def async_unload_platforms(self, entry, platforms):
        self.unloaded.append((entry, tuple(platforms)))
        return self.unload_result

    async def async_reload(self, entry_id):
        self.reloaded.append(entry_id)


class FakeHass(ha_stubs.FakeHass):
    """The suite's standard hass, plus the entry manager setup drives.

    It answers nothing — every source reads as missing — which is the right
    shape here: setup must succeed against a registry that cannot be read yet,
    because on a real boot it is exactly that (the registry restores
    an entity row long before its owner publishes a state).
    """

    def __init__(self):
        super().__init__()
        self.config_entries = FakeConfigEntriesManager()
        self.data = {}


class FakeEntry:
    def __init__(self, options=None):
        self.entry_id = "01ENTRY"
        self.options = dict(options or {})
        self.runtime_data = None
        self.on_unload = []
        self.update_listeners = []

    def async_on_unload(self, fn):
        self.on_unload.append(fn)
        return fn

    def add_update_listener(self, fn):
        self.update_listeners.append(fn)
        return lambda: None


@pytest.fixture
def setup():
    hass, entry = FakeHass(), FakeEntry()
    ok = asyncio.run(household_state.async_setup_entry(hass, entry))
    return hass, entry, ok


def test_setup_reports_success(setup):
    _, _, ok = setup
    assert ok is True


def test_the_coordinator_is_stored_on_the_entry_not_in_hass_data(setup):
    """`runtime-data`. hass.data staying empty is the assertion — a coordinator
    parked there outlives a failed unload with nothing pointing at it."""
    hass, entry, _ = setup
    assert isinstance(entry.runtime_data, HouseholdStateCoordinator)
    assert hass.data == {}


def test_ages_are_loaded_before_the_first_refresh():
    """RULE 5, and it is an ORDERING, so nothing but ordering proves it. Skip
    it and every age clock restarts at zero on every HA restart — which
    under-reports age, the direction that hides the problem."""
    order = []
    real_load = HouseholdStateCoordinator.async_load_ages

    async def spy_load(self):
        order.append("load_ages")
        await real_load(self)

    async def spy_refresh(self):
        order.append("first_refresh")

    HouseholdStateCoordinator.async_load_ages = spy_load
    HouseholdStateCoordinator.async_config_entry_first_refresh = spy_refresh
    try:
        asyncio.run(household_state.async_setup_entry(FakeHass(), FakeEntry()))
    finally:
        HouseholdStateCoordinator.async_load_ages = real_load

    assert order == ["load_ages", "first_refresh"], order


def test_the_scan_interval_comes_from_the_entry_options():
    hass, entry = FakeHass(), FakeEntry({"scan_interval": 30})
    asyncio.run(household_state.async_setup_entry(hass, entry))
    assert entry.runtime_data.update_interval.total_seconds() == 30


def test_the_shipped_default_is_used_when_the_option_is_unset(setup):
    _, entry, _ = setup
    assert entry.runtime_data.update_interval.total_seconds() == DEFAULT_SCAN_INTERVAL


def test_both_platforms_are_forwarded(setup):
    hass, entry, _ = setup
    assert hass.config_entries.forwarded == [(entry, tuple(PLATFORMS))]


def test_logging_starts_disarmed_and_is_armed_by_a_registered_callback(setup):
    """Logging is gated on HA reaching RUNNING, and the gate RECORDS NOTHING
    while silent — a gate that recorded would make a fault present through
    startup read as already-reported, so it would never log at all."""
    _, entry, _ = setup
    assert entry.runtime_data._log_armed is False
    assert entry.on_unload, "nothing registered for teardown"


def test_the_options_listener_is_registered_and_reloads_the_entry(setup):
    hass, entry, _ = setup
    assert entry.update_listeners, "no options-update listener"
    asyncio.run(entry.update_listeners[0](hass, entry))
    assert hass.config_entries.reloaded == [entry.entry_id]


def test_everything_registered_is_registered_for_teardown(setup):
    """Both the logging arm and the options listener go through
    entry.async_on_unload, so neither outlives the entry."""
    _, entry, _ = setup
    assert len(entry.on_unload) >= 2


# ============================================================== teardown

def test_unload_unloads_both_platforms(setup):
    hass, entry, _ = setup
    assert asyncio.run(household_state.async_unload_entry(hass, entry)) is True
    assert hass.config_entries.unloaded == [(entry, tuple(PLATFORMS))]


def test_a_refused_platform_unload_is_reported_as_failure(setup):
    """HA keeps the entry loaded on False. Reporting True over a failed unload
    would leave half a component running with nothing tracking it."""
    hass, entry, _ = setup
    hass.config_entries.unload_result = False
    assert asyncio.run(household_state.async_unload_entry(hass, entry)) is False


def test_unload_touches_no_module_global(setup):
    """There is nothing left to pop: the coordinator went onto the entry, so
    teardown is whatever HA does to the entry and nothing else."""
    hass, entry, _ = setup
    asyncio.run(household_state.async_unload_entry(hass, entry))
    assert hass.data == {}


def test_the_assertions_can_fail(setup):
    """Self-test: this assertion set must be able to fail."""
    hass, entry, _ = setup
    # The unload result really is plumbed through, not hardcoded True.
    hass.config_entries.unload_result = True
    assert asyncio.run(household_state.async_unload_entry(hass, entry)) is True
    hass.config_entries.unload_result = False
    assert asyncio.run(household_state.async_unload_entry(hass, entry)) is False


# ======================================== macro states: setup and cleanup

_GUEST = {"slug": "guest", "name": "Guest", "entity_id": "input_boolean.guest",
          "on_state": "on", "icon": None}


def _hass_with_rows(*rows):
    """A hass whose entity registry already carries `rows` for this entry."""
    hass = FakeHass()
    hass.entity_registry = ha_stubs.FakeEntityRegistry(rows)
    return hass


def _row(entity_id, unique_id, entry_id="01ENTRY"):
    return ha_stubs.FakeRegistryEntry(
        entity_id, unique_id=unique_id, config_entry_id=entry_id
    )


def test_the_macros_reach_the_coordinator_from_the_entry():
    hass, entry = FakeHass(), FakeEntry({"macros": [_GUEST]})
    asyncio.run(household_state.async_setup_entry(hass, entry))
    assert [m["slug"] for m in entry.runtime_data.macros] == ["guest"]


def test_the_macros_option_is_not_handed_over_as_a_source_binding():
    """__init__ splits entry.options into bindings and everything else. A
    non-binding option missing from that split becomes a binding for a source
    named after itself, which resolves to nothing and says nothing."""
    hass, entry = FakeHass(), FakeEntry({"macros": [_GUEST], "scan_interval": 9})
    asyncio.run(household_state.async_setup_entry(hass, entry))
    assert entry.runtime_data._bindings == {}


def test_a_macro_that_was_deleted_takes_its_registry_row_with_it():
    """NOTHING ELSE RECLAIMS IT. A macro removed in the options flow would
    otherwise keep publishing binary_sensor.household_state_<slug> forever,
    permanently unavailable, with the id still taken — so re-adding the same
    macro later lands on `_2` and every dashboard keeps reading the ghost.
    Same id-is-never-reclaimed problem the README warns about for reinstalls,
    except this one is reachable from a form."""
    hass = _hass_with_rows(
        _row("binary_sensor.household_state_guest", "01ENTRY_macro_guest"),
        _row("binary_sensor.household_state_party", "01ENTRY_macro_party"),
    )
    entry = FakeEntry({"macros": [_GUEST]})
    asyncio.run(household_state.async_setup_entry(hass, entry))
    assert hass.entity_registry.removed == ["binary_sensor.household_state_party"]


def test_the_cleanup_leaves_every_entity_that_is_not_a_macro_alone():
    """The axes, the per-source diagnostics, QUIET and feed health carry no
    `_macro_` prefix. A cleanup that caught one of them would delete the
    entity every dashboard in the house reads."""
    hass = _hass_with_rows(
        _row("sensor.household_state_stage", "01ENTRY_stage"),
        _row("binary_sensor.household_state_quiet", "01ENTRY_quiet"),
        _row("binary_sensor.household_state_feed_health", "01ENTRY_feed_health"),
        _row("sensor.household_state_ntas", "01ENTRY_src_ntas"),
    )
    asyncio.run(household_state.async_setup_entry(hass, FakeEntry()))
    assert hass.entity_registry.removed == []


def test_another_entry_s_macro_rows_are_not_touched():
    """The prefix carries the entry id. `single_config_entry` makes a second
    entry unreachable today, but a cleanup keyed on `_macro_` alone would be
    wrong the moment that stops being true — and wrong by deleting."""
    hass = _hass_with_rows(
        _row("binary_sensor.other_guest", "OTHERENTRY_macro_guest",
             entry_id="OTHERENTRY"),
    )
    asyncio.run(household_state.async_setup_entry(hass, FakeEntry()))
    assert hass.entity_registry.removed == []


def test_the_cleanup_runs_before_the_platforms_are_set_up():
    """An entity added and then removed in the same pass flickers through
    every surface subscribed to the registry."""
    order = []

    hass = _hass_with_rows(
        _row("binary_sensor.household_state_party", "01ENTRY_macro_party"),
    )

    class _Registry(ha_stubs.FakeEntityRegistry):
        def async_remove(self, entity_id):
            order.append("remove")
            super().async_remove(entity_id)

    hass.entity_registry = _Registry(list(hass.entity_registry.entities.values()))

    real_forward = hass.config_entries.async_forward_entry_setups

    async def _forward(entry, platforms):
        order.append("forward")
        await real_forward(entry, platforms)

    hass.config_entries.async_forward_entry_setups = _forward
    asyncio.run(household_state.async_setup_entry(hass, FakeEntry()))
    assert order == ["remove", "forward"]


def test_a_registry_that_will_not_answer_does_not_take_setup_down():
    """RULE 1's reasoning, applied to setup: the registry API can move under
    an upgrade, and a stale entity row is untidy where an integration that
    will not start is an outage."""
    hass = FakeHass()

    class _Exploding:
        @property
        def entities(self):
            raise RuntimeError("registry moved")

    hass.entity_registry = _Exploding()
    assert asyncio.run(household_state.async_setup_entry(hass, FakeEntry())) is True


def test_nothing_is_removed_when_no_macro_row_exists():
    """The common case: an installation that has never defined one."""
    hass = _hass_with_rows()
    asyncio.run(household_state.async_setup_entry(hass, FakeEntry()))
    assert hass.entity_registry.removed == []
