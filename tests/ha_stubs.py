"""Enough of `homeassistant` to import coordinator.py without installing core.

WHY A STUB AND NOT pytest-homeassistant-custom-component. The behaviour under
test is this integration's OWN log-dedupe policy — which condition token is
compared, at which level it lands, and whether it is armed yet. None of that
touches core's event loop, its registries' real semantics, or a config entry.
A stub keeps the test runnable in CI in seconds and keeps a green result
attributable to this repo rather than to a core version bump.

It proves nothing about core's real registry APIs. `_perimeter_entity_ids` is
wrapped in a RULE 1 guard precisely because those APIs can move under an
upgrade, and no test here can see that happen.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone


def install() -> None:
    """Register the stub modules in sys.modules. Idempotent."""
    if "homeassistant" in sys.modules:
        return

    def mod(name: str) -> types.ModuleType:
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m

    mod("homeassistant")

    core = mod("homeassistant.core")

    class HomeAssistant:  # noqa: D101
        pass

    def callback(fn):  # noqa: D103
        return fn

    core.HomeAssistant = HomeAssistant
    core.callback = callback

    config_entries = mod("homeassistant.config_entries")

    class ConfigEntryState:  # noqa: D101
        LOADED = "loaded"
        SETUP_RETRY = "setup_retry"

    class ConfigEntry:  # noqa: D101
        # Subscriptable because the quality scale's `runtime-data` rule types
        # the entry by what it carries: coordinator.py evaluates
        # `ConfigEntry[HouseholdStateCoordinator]` at import.
        def __class_getitem__(cls, _item):
            return cls

    # Enough of the flow bases to import and drive config_flow.py.
    #
    # WHAT THIS DOES AND DOES NOT PROVE. It executes THIS repo's flow logic —
    # the single-instance abort, the empty user schema, the options default
    # read back off the entry, the 1-300 bound on scan_interval. It proves
    # nothing about core's real flow manager: step dispatch, the translation
    # lookups behind `reason`, or how an OptionsFlow is handed its entry in
    # the HA version of the day. The trade is ha_stubs' standing one, stated
    # in this file's docstring and in validate.yml's tests job.
    class _FlowBase:
        def async_show_form(self, *, step_id, data_schema=None, errors=None):
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors,
            }

        def async_create_entry(self, *, title, data):
            return {"type": "create_entry", "title": title, "data": data}

        def async_abort(self, *, reason):
            return {"type": "abort", "reason": reason}

    class ConfigFlow(_FlowBase):  # noqa: D101
        # Real core records the domain off the subclass keyword; the tests
        # read it back to prove the flow is registered against this
        # integration rather than silently against nothing.
        def __init_subclass__(cls, /, domain=None, **kw):
            super().__init_subclass__(**kw)
            cls.domain = domain

        # Set by a test to say what is already configured.
        _current_entries = ()

        def _async_current_entries(self, include_ignore=True):
            return list(self._current_entries)

    class OptionsFlow(_FlowBase):  # noqa: D101
        # Core hands the flow its entry; here a test assigns it directly.
        config_entry = None

    config_entries.ConfigEntryState = ConfigEntryState
    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow

    mod("homeassistant.helpers")

    er = mod("homeassistant.helpers.entity_registry")
    er.async_get = lambda hass: hass.entity_registry
    er.async_entries_for_label = lambda reg, label_id: [
        e for e in reg.entities.values() if label_id in getattr(e, "labels", ())
    ]
    er.async_entries_for_config_entry = lambda reg, entry_id: [
        e for e in reg.entities.values() if getattr(e, "config_entry_id", None) == entry_id
    ]

    lr = mod("homeassistant.helpers.label_registry")
    lr.async_get = lambda hass: hass.label_registry

    storage = mod("homeassistant.helpers.storage")

    class Store:  # noqa: D101
        def __init__(self, hass, version, key):
            self._data = {}

        async def async_load(self):
            return dict(self._data)

        async def async_save(self, data):
            self._data = dict(data)

    storage.Store = Store

    start = mod("homeassistant.helpers.start")
    start.async_at_started = lambda hass, cb: (lambda: None)

    uc = mod("homeassistant.helpers.update_coordinator")

    class DataUpdateCoordinator:  # noqa: D101
        def __init__(self, hass, logger, name=None, update_interval=None):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None

        async def async_config_entry_first_refresh(self):
            # Core's version raises ConfigEntryNotReady on failure. This one
            # cannot, and that is faithful here rather than a shortcut: RULE 1
            # means _async_update_data never raises, so the real call has no
            # failure path to convert. That is also why `test-before-setup` is
            # an exempt deviation in quality_scale.yaml.
            self.data = await self._async_update_data()

        async def async_refresh(self):
            self.data = await self._async_update_data()

    class CoordinatorEntity:  # noqa: D101
        def __init__(self, coordinator):
            self.coordinator = coordinator

    uc.DataUpdateCoordinator = DataUpdateCoordinator
    uc.CoordinatorEntity = CoordinatorEntity

    # Enough of the sensor platform to import sensor.py. An earlier stub put real
    # behaviour in SourceSensor.native_value -- which of two facts about a
    # source its state reports -- and that is policy this repo owns, so it is
    # testable here for the same reason the log-dedupe policy is. None of it
    # touches core's entity machinery; these are name-holders only.
    dr = mod("homeassistant.helpers.device_registry")

    class DeviceInfo(dict):  # noqa: D101
        def __init__(self, **kw):
            super().__init__(**kw)

    dr.DeviceInfo = DeviceInfo

    const = mod("homeassistant.const")

    class EntityCategory:  # noqa: D101
        DIAGNOSTIC = "diagnostic"

    const.EntityCategory = EntityCategory

    mod("homeassistant.components")
    sensor_mod = mod("homeassistant.components.sensor")

    class SensorEntity:  # noqa: D101
        pass

    sensor_mod.SensorEntity = SensorEntity

    binary_mod = mod("homeassistant.components.binary_sensor")

    class BinarySensorEntity:  # noqa: D101
        pass

    class BinarySensorDeviceClass:  # noqa: D101
        PROBLEM = "problem"

    binary_mod.BinarySensorEntity = BinarySensorEntity
    binary_mod.BinarySensorDeviceClass = BinarySensorDeviceClass

    mod("homeassistant.util")
    dt = mod("homeassistant.util.dt")
    dt.utcnow = lambda: datetime.now(timezone.utc)

    def parse_datetime(value):
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    dt.parse_datetime = parse_datetime


class FakeState:
    """`hass.states.get()`'s return shape, reduced to what is read."""

    def __init__(self, state, **attributes):
        self.state = state
        self.attributes = attributes


class FakeStates:
    def __init__(self, mapping=None):
        self._m = dict(mapping or {})

    def get(self, entity_id):
        return self._m.get(entity_id)

    def set(self, entity_id, state):
        self._m[entity_id] = state

    def drop(self, entity_id):
        self._m.pop(entity_id, None)


class FakeRegistryEntry:
    def __init__(self, entity_id, platform=None, unique_id=None, labels=(),
                 config_entry_id=None):
        self.entity_id = entity_id
        self.platform = platform
        self.unique_id = unique_id
        self.labels = labels
        self.config_entry_id = config_entry_id


class FakeEntityRegistry:
    def __init__(self, entries=()):
        self.entities = {e.entity_id: e for e in entries}


class FakeLabelRegistry:
    def __init__(self, labels=()):
        self._by_id = {name: name for name in labels}

    def async_get_label(self, label_id):
        return _Label(label_id) if label_id in self._by_id else None

    def async_get_label_by_name(self, name):
        return _Label(name) if name in self._by_id else None


class _Label:
    def __init__(self, label_id):
        self.label_id = label_id


class FakeServices:
    """`hass.services`, reduced to the one question this integration asks."""

    def __init__(self, registered=()):
        self._registered = {tuple(r) for r in registered}

    def has_service(self, domain, service):
        return (domain, service) in self._registered


class FakeConfigEntries:
    """`hass.config_entries`, reduced to the listing the integrity row reads."""

    def __init__(self, entries=()):
        self._entries = list(entries)

    def async_entries(self):
        return list(self._entries)


class FakeConfigEntry:
    def __init__(self, entry_id, domain="x", title="X", state="loaded",
                 disabled_by=None):
        self.entry_id = entry_id
        self.domain = domain
        self.title = title
        self.state = state
        self.disabled_by = disabled_by


class FakeHass:
    def __init__(self, states=None, entity_registry=None, label_registry=None,
                 services=None, config_entries=None):
        self.states = FakeStates(states)
        self.entity_registry = entity_registry or FakeEntityRegistry()
        self.label_registry = label_registry or FakeLabelRegistry()
        self.services = services if services is not None else FakeServices()
        self.config_entries = (
            config_entries if config_entries is not None else FakeConfigEntries()
        )
