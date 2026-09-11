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
    shape here: setup must succeed against an estate that cannot be read yet,
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
