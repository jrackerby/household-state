"""The resolved cell reaches sensor.household_state_directive (#30).

banner.py is pure; this file is the seam either side of it. The coordinator
has to hand it the PUBLISHED stage (after the fall dwell), the driver's own
reading found by its published slug, the household's names for the ids it
carries, and an operator's wording off the bound helper prefix — and the
sensor has to publish every attribute, always, so a consumer can tell "no
cell" from "no matrix".
"""

import asyncio

import pytest

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


def coordinator(states, bindings=None, macros=()):
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
    c = HouseholdStateCoordinator(FakeHass(states), 3, merged, macros)
    c.async_arm_logging()
    return c


def data(states, bindings=None, macros=()):
    return asyncio.run(coordinator(states, bindings, macros)._async_update_data())


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


# ======================================================== the mask (#30)

PARTY = {"slug": "party", "name": "Party", "entity_id": "input_boolean.party",
         "on_state": "on", "masks": True}
GUEST = {"slug": "guest", "name": "Guest", "entity_id": "input_boolean.guest",
         "on_state": "on"}


def test_a_masking_macro_that_is_on_silences_the_published_cell():
    """The seam: the macro is read into `out["macros"]` and the cell is
    resolved from that reading, in the same cycle — never off the binary
    sensor this component publishes from it, which would be a cycle stale."""
    states = dict(HEAT, **{"input_boolean.party": FakeState("on")})
    out = data(states, macros=[PARTY])
    assert out["stage"] == "elevated"          # the axis is untouched (RULE 7)
    assert out["macros"]["party"]["state"] is True
    b = out["banner"]
    assert b["cell"] is None and b["gate"] == "none"
    assert b["masked"] is True and b["masked_by"] == "party"
    assert b["status"] == [] and b["hazard_name"] is None
    # The negative twin: the same house with the party off states its alert.
    states["input_boolean.party"] = FakeState("off")
    loud = data(states, macros=[PARTY])["banner"]
    assert loud["cell"] == CELL_ALERT and loud["masked"] is False
    assert loud["hazard_name"] == "Heat Advisory"


def test_a_macro_that_does_not_declare_masks_silences_nothing():
    states = dict(HEAT, **{"input_boolean.guest": FakeState("on")})
    out = data(states, macros=[GUEST])
    assert out["macros"]["guest"]["state"] is True
    assert out["banner"]["cell"] == CELL_ALERT
    assert out["banner"]["masked"] is False and out["banner"]["masked_by"] is None


@pytest.mark.parametrize("raw", ["unavailable", "unknown", None])
def test_an_unreadable_masking_macro_does_not_take_the_banner_away(raw):
    """A modifier that cannot be read publishes None, never False — and a
    mask that fired on an absence would silence a shelter instruction
    because somebody deleted a helper."""
    states = dict(HEAT)
    if raw is not None:
        states["input_boolean.party"] = FakeState(raw)
    out = data(states, macros=[PARTY])
    assert out["macros"]["party"]["state"] is None
    assert out["banner"]["cell"] == CELL_ALERT
    assert out["banner"]["masked"] is False


def test_the_party_never_masks_an_evacuation_end_to_end():
    states = dict(HEAT, **{"input_boolean.party": FakeState("on")})
    states[CAP] = FakeState(
        "ok", cap_responses=[{"response": "Evacuate", "event": "Evacuation Immediate"}]
    )
    out = data(states, macros=[PARTY])
    assert out["directive"] == "evacuate"
    b = out["banner"]
    assert b["cell"] == "evacuate" and b["gate"] == "evacuate"
    assert b["masked"] is False and b["evacuate"] is True


def test_the_first_masking_macro_that_is_on_names_itself():
    """Two masks on: the answer is the first DECLARED, not whichever the
    dict happened to yield first."""
    states = dict(HEAT, **{"input_boolean.party": FakeState("on"),
                           "input_boolean.guest": FakeState("on")})
    guest_masks = dict(GUEST, masks=True)
    assert data(states, macros=[PARTY, guest_masks])["banner"]["masked_by"] == "party"
    assert data(states, macros=[guest_masks, PARTY])["banner"]["masked_by"] == "guest"
