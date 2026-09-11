"""The config flow, exercised. Quality scale: `config-flow-test-coverage`.

config_flow.py sat at 0% when this repo was gap-listed (GH #2), which is the
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
"""

import json
import pathlib

import pytest
import voluptuous as vol

from household_state.config_flow import (
    HouseholdStateConfigFlow,
    HouseholdStateOptionsFlow,
)
from household_state.const import DEFAULT_SCAN_INTERVAL, DOMAIN

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

    result = asyncio.run(_options_flow({"scan_interval": 17}).async_step_init(None))
    assert result["type"] == "form"
    assert result["data_schema"]({}) == {"scan_interval": 17}


def test_options_falls_back_to_the_shipped_default():
    import asyncio

    result = asyncio.run(_options_flow().async_step_init(None))
    assert result["data_schema"]({}) == {"scan_interval": DEFAULT_SCAN_INTERVAL}


@pytest.mark.parametrize("value", [1, 3, 300])
def test_the_accepted_range_is_inclusive_at_both_ends(value):
    import asyncio

    result = asyncio.run(_options_flow().async_step_init(None))
    assert result["data_schema"]({"scan_interval": value}) == {"scan_interval": value}


@pytest.mark.parametrize("value", [0, -1, 301])
def test_out_of_range_is_refused(value):
    """A poll interval longer than the fall dwell makes the dwell meaningless
    (const.py), and 0 would spin. The bound is load-bearing, not decoration."""
    import asyncio

    result = asyncio.run(_options_flow().async_step_init(None))
    with pytest.raises(vol.Invalid):
        result["data_schema"]({"scan_interval": value})


def test_a_string_is_coerced_not_refused():
    """The UI hands back a string. vol.Coerce(int) is why that works."""
    import asyncio

    result = asyncio.run(_options_flow().async_step_init(None))
    assert result["data_schema"]({"scan_interval": "30"}) == {"scan_interval": 30}


def test_submitting_options_stores_them():
    import asyncio

    result = asyncio.run(
        _options_flow().async_step_init({"scan_interval": 42})
    )
    assert result["type"] == "create_entry"
    assert result["data"] == {"scan_interval": 42}


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


def test_the_assertions_can_fail():
    """a check that cannot go red is not a check."""
    import asyncio

    # The schema really does validate, rather than accepting anything.
    result = asyncio.run(_options_flow().async_step_init(None))
    with pytest.raises(vol.Invalid):
        result["data_schema"]({"scan_interval": 10_000})
    # The single-instance guard really does depend on there being an entry.
    assert asyncio.run(_flow().async_step_user(None))["type"] == "form"
    assert asyncio.run(
        _flow(current_entries=(_Entry(),)).async_step_user(None)
    )["type"] == "abort"
