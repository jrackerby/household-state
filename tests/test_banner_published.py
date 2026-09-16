"""The resolved cell reaches sensor.household_state_directive (#30).

banner.py is pure; this file is the seam either side of it. The coordinator
has to hand it the PUBLISHED stage (after the fall dwell), the driver's own
reading found by its published slug, the household's names for the ids it
carries, and an operator's wording off the bound helper prefix — and the
sensor has to publish every attribute, always, so a consumer can tell "no
cell" from "no matrix".
"""

import asyncio

from household_state.banner import BANNER_ATTRIBUTES, CELL_ALERT, CELL_CRIT_NONE
from household_state.const import BIND_BANNER, bind_key
from household_state.coordinator import HouseholdStateCoordinator
from household_state.sensor import DirectiveSensor

from ha_stubs import FakeHass, FakeState

NWS = "sensor.test_nws"
CAP = "sensor.test_cap"
BOIL = "binary_sensor.test_boil_water"
ALARM = "alarm_control_panel.test_panel"
FRONT = "binary_sensor.front_door_sensor_door_sensor"


def coordinator(states, bindings=None):
    # Both DIRECTIVE rows bound and readable: an unbound one is `absent`,
    # which resolves the axis to `unknown` — correctly — and lands every
    # case below on the unavailable cell before it can test anything else.
    merged = {
        bind_key("local_nws", "entity_id"): NWS,
        bind_key("nws_cap", "entity_id"): CAP,
        bind_key("boil_water_directive", "entity_id"): BOIL,
        bind_key("alarm", "entity_id"): ALARM,
    }
    merged.update(bindings or {})
    c = HouseholdStateCoordinator(FakeHass(states), 3, merged)
    c.async_arm_logging()
    return c


def data(states, bindings=None):
    return asyncio.run(coordinator(states, bindings)._async_update_data())


HEAT = {
    NWS: FakeState("Heat Advisory", severity=2,
                   headline="Heat Advisory issued today until 8:00PM EDT by NWS Somewhere"),
    CAP: FakeState("ok", cap_responses=[]),
    BOIL: FakeState("off"),
    ALARM: FakeState("disarmed"),
}


def test_the_coordinator_attaches_the_cell_and_names_the_driver_it_published():
    out = data(HEAT)
    b = out["banner"]
    assert out["stage"] == "elevated" and out["driver"] == "local_nws"
    assert b["cell"] == CELL_ALERT and b["gate"] == "banner"
    assert b["hazard_driver"] == "local_nws"
    assert b["hazard_name"] == "Heat Advisory"
    assert b["hazard_source"] == "National Weather Service"
    assert b["hazard_window"] == "until 8:00PM EDT"
    assert b["imperative"] == "Stay out of the afternoon heat"
    assert b["status"] == ["Heat Advisory", "National Weather Service", "until 8:00PM EDT"]


def test_the_driver_is_found_by_its_published_slug_not_its_key():
    """#19: an installation that kept a legacy id publishes `driver` as the
    bound slug, and the matrix must follow that identity."""
    out = data(HEAT, {bind_key("local_nws", "slug"): "nws_union"})
    assert out["driver"] == "nws_union"
    assert out["banner"]["hazard_driver"] == "nws_union"
    assert out["banner"]["hazard_name"] == "Heat Advisory"


def test_an_armed_house_names_the_door_off_the_state_machine():
    states = dict(HEAT)
    states[NWS] = FakeState("None", severity=0)
    states[ALARM] = FakeState("armed_away", open_sensors={FRONT: "open"})
    states[FRONT] = FakeState("on", friendly_name="Front Door Sensor")
    out = data(states)
    assert out["stage"] == "critical"
    assert out["readings"]["alarm"]["ids"] == [FRONT]
    assert out["banner"]["cell"] == CELL_CRIT_NONE
    assert out["banner"]["imperative"] == "Close the Front Door — the house is armed"
    # The twin: with no friendly name to read, the id's own words stand in
    # rather than nothing — and the raw id still never reaches the line.
    del states[FRONT]
    out = data(states)
    assert out["banner"]["imperative"] == "Close the Front Door — the house is armed"
    assert "binary_sensor." not in out["banner"]["imperative"]


def test_a_bound_prefix_reads_the_operators_wording_and_an_unbound_one_reads_nothing():
    states = dict(HEAT)
    states[CAP] = FakeState("ok", cap_responses=[{"response": "Shelter", "event": "X"}])
    states["input_text.directive_elev_shelter_imperative"] = FakeState("Everyone upstairs")
    states["input_text.directive_elev_shelter_action"] = FakeState("unknown")
    bound = data(states, {bind_key(BIND_BANNER, "text_prefix"): "directive"})
    assert bound["banner"]["cell"] == "elev_shelter"
    assert bound["banner"]["imperative"] == "Everyone upstairs"
    assert bound["banner"]["action"] == "Know your way to the main closet."
    unbound = data(states)
    assert unbound["banner"]["imperative"] == "Get ready to shelter"


def test_the_jurisdiction_binding_reaches_the_weather_wording():
    states = dict(HEAT)
    states[NWS] = FakeState("Rip Current Statement", severity=1)
    assert data(states)["banner"]["action"] == "Rip Current Statement is in effect."
    bound = data(states, {bind_key(BIND_BANNER, "jurisdiction"): "Union County"})
    assert bound["banner"]["action"] == "Rip Current Statement is in effect for Union County."


def test_the_cell_follows_the_published_stage_through_the_fall_dwell():
    """RULE 3 holds the stage up through a fall; the cell must be resolved
    from that held word, or the two entities disagree for the dwell."""
    c = coordinator(dict(HEAT))
    first = asyncio.run(c._async_update_data())
    assert first["banner"]["cell"] == CELL_ALERT
    c.hass.states.set(NWS, FakeState("None", severity=0))
    held = asyncio.run(c._async_update_data())
    assert held["fall_dwell_holding"] is True
    assert held["stage"] == "elevated"
    assert held["banner"]["cell"] == CELL_ALERT
    assert held["banner"]["stage_word"] == "ELEVATED"


def test_an_unreadable_axis_is_the_unavailable_cell_never_the_empty_row():
    out = data({NWS: FakeState("unavailable"), CAP: FakeState("ok", cap_responses=[]),
                BOIL: FakeState("off"), ALARM: FakeState("disarmed")})
    assert out["stage"] == "unknown"
    assert out["banner"]["cell"] == "unavailable"
    assert out["banner"]["gate"] == "banner"
    assert out["banner"]["stage_tone"] == "stale"


# ============================================================== the entity

class _Coordinator:
    def __init__(self, data):
        self.data = data


def test_the_directive_sensor_publishes_every_cell_attribute():
    out = data(HEAT)
    attrs = DirectiveSensor(_Coordinator(out), "E").extra_state_attributes
    for key in BANNER_ATTRIBUTES:
        assert key in attrs, key
        assert attrs[key] == out["banner"][key]
    # The existing contract is untouched beside it.
    assert attrs["suppressed"] == [] and attrs["reason"] == "no_directive_response"


def test_the_attributes_are_present_and_none_before_the_first_refresh():
    attrs = DirectiveSensor(_Coordinator(None), "E").extra_state_attributes
    for key in BANNER_ATTRIBUTES:
        assert key in attrs and attrs[key] is None, key
