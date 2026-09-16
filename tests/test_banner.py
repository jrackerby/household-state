"""The rendering matrix, exercised without Home Assistant (#30).

tests/test_banner_parity.py proves banner.py says what the kit's directive.ts
said for every state map the kit ever drew. THIS file owns what the kit
never had: the drivers the kit rendered as a bare `on` (the two binary
hazards), the jurisdiction that used to be a hardcoded county, the helper
lookup's not-set shapes, the gate verdict, and the invariants a wording
table has to keep by construction — no cell but the shelter cells names
the closet, no machine string reaches a line.

EVERY ASSERTION SET HAS A NEGATIVE TWIN. Where a test says the hazard line
wins, another says the helper wins with the hazard withdrawn; where one
says a driver is named, another says an unreadable one is not.
"""

import pytest

from household_state.banner import (
    BANNER_ATTRIBUTES,
    CELL_ALERT,
    CELL_BOIL_WATER,
    CELL_CRIT_NONE,
    CELL_CRIT_SHELTER,
    CELL_ELEV_SHELTER,
    CELL_EVACUATE,
    CELL_TONE,
    CELL_UNAVAILABLE,
    CELLS,
    DEFAULT_TEXT,
    EVENT_GUIDANCE,
    GATE_BANNER,
    GATE_EVACUATE,
    GATE_NONE,
    GENERIC_CELLS,
    TONE_CRIT,
    TONE_NEUTRAL,
    TONE_STALE,
    TONE_WATCH,
    gate_for,
    hazard_now,
    humanize_entity_name,
    humanize_headline,
    join_names,
    resolve_banner,
    resolve_cell,
    status_parts,
)
from household_state.const import SOURCES

DRIVEWAY = "binary_sensor.driveway_camera_person_detected"
GATE = "binary_sensor.north_gate_camera_person_detected"

NAMES = {
    DRIVEWAY: "Driveway Camera Person Detected",
    GATE: "North Gate Camera Person Detection",
    "binary_sensor.front_door_sensor_door_sensor": "Front Door Sensor",
}


def names_of(eid):
    return NAMES.get(eid)


def row(key):
    return next(s for s in SOURCES if s["key"] == key)


def reading(key, raw_state, detail=None, ids=None, **extra):
    spec = row(key)
    r = {"key": key, "slug": key, "kind": spec["kind"], "name": spec["name"],
         "raw_state": raw_state, "detail": detail}
    if ids is not None:
        r["ids"] = ids
    r.update(extra)
    return r


def banner(stage="elevated", directive="none", quiet=False, **kw):
    return resolve_banner(stage=stage, directive=directive, quiet=quiet, **kw)


# ============================================================== the matrix

@pytest.mark.parametrize("stage,directive,cell", [
    ("normal", "none", None),
    ("normal", "boil_water", None),
    ("elevated", "none", CELL_ALERT),
    ("elevated", "secure", "elev_secure"),
    ("elevated", "shelter", CELL_ELEV_SHELTER),
    ("elevated", "boil_water", CELL_BOIL_WATER),
    ("critical", "none", CELL_CRIT_NONE),
    ("critical", "secure", "crit_secure"),
    ("critical", "shelter", CELL_CRIT_SHELTER),
    ("critical", "boil_water", CELL_BOIL_WATER),
    ("normal", "evacuate", CELL_EVACUATE),
    ("unknown", "evacuate", CELL_EVACUATE),
    ("unknown", "none", CELL_UNAVAILABLE),
    ("elevated", "unknown", CELL_UNAVAILABLE),
    (None, "none", CELL_UNAVAILABLE),
    ("elevated", None, CELL_UNAVAILABLE),
    ("degraded", "none", CELL_UNAVAILABLE),
])
def test_every_pair_lands_in_exactly_one_cell(stage, directive, cell):
    assert resolve_cell(stage, directive) == cell


def test_the_gate_verdict_is_what_a_surface_mounts():
    assert gate_for(None) == GATE_NONE
    assert gate_for(CELL_EVACUATE) == GATE_EVACUATE
    for cell in CELLS:
        if cell != CELL_EVACUATE:
            assert gate_for(cell) == GATE_BANNER, cell


def test_every_cell_has_a_tone_and_a_default_text():
    assert set(CELL_TONE) == set(CELLS) == set(DEFAULT_TEXT)


def test_no_cell_but_the_shelter_cells_names_the_closet():
    """directive_text's own rule: crit_none must read as critical WITHOUT
    naming a location. Made mechanical across every default and every
    guidance line, not just the ones with a test."""
    for cell, (imp, act) in DEFAULT_TEXT.items():
        if cell in (CELL_ELEV_SHELTER, CELL_CRIT_SHELTER):
            continue
        assert "closet" not in (imp + " " + act).lower(), cell
    for event, (imp, act) in EVENT_GUIDANCE.items():
        assert "closet" not in (imp + " " + act).lower(), event
    # The twin: the check can fail, because the shelter cell's own text
    # does name it and the same assertion would reject it.
    assert "closet" in DEFAULT_TEXT[CELL_CRIT_SHELTER][0].lower()


# =========================================== drivers the kit never worded

def test_a_boil_water_stage_driver_is_named_and_says_boil():
    """The kit rendered this driver's raw_state — the bare word `on` — as
    the hazard name. The row's own name is the finding."""
    b = banner(driver=reading("boil_water", "on", "Boil Water Advisory in effect for this address"))
    assert b["cell"] == CELL_ALERT
    assert b["hazard_name"] == "Boil Water Advisory"
    assert b["hazard_source"] == "Water utility"
    assert "boil" in b["imperative"].lower()
    assert b["status"] == ["Boil Water Advisory", "Water utility"]
    # The twin: with the DIRECTIVE row bound too, the boil cell wins and
    # carries the same instruction from its own default.
    both = banner(directive="boil_water",
                  driver=reading("boil_water", "on"))
    assert both["cell"] == CELL_BOIL_WATER
    assert both["imperative"] == DEFAULT_TEXT[CELL_BOIL_WATER][0]


def test_a_person_seen_outside_names_the_cameras():
    """#13 forwards the camera ids raw; the matrix is where they become
    words. Names WHICH, never THAT."""
    b = banner(driver=reading("outside_person", "on", ids=[DRIVEWAY, GATE]),
               names_of=names_of)
    assert b["cell"] == CELL_ALERT
    assert b["imperative"] == "Someone is outside"
    assert b["action"].startswith("Seen by the Driveway Camera Person Detected and North Gate Camera Person.")
    assert b["hazard_name"] == "Person Outside Overnight"
    assert "binary_sensor." not in b["action"]


def test_a_person_seen_by_nothing_named_still_says_someone_is_outside():
    b = banner(driver=reading("outside_person", "on", ids=[]))
    assert b["imperative"] == "Someone is outside"
    assert b["action"].startswith("An outside camera saw a person.")


def test_an_unmapped_weather_event_names_no_place_unless_one_is_bound():
    """hazard.ts said "for Union County" for every household; the port
    says nothing about where rather than the wrong where."""
    unbound = banner(driver=reading("local_nws", "Rip Current Statement"))
    assert unbound["action"] == "Rip Current Statement is in effect."
    bound = banner(driver=reading("local_nws", "Rip Current Statement"),
                   jurisdiction="Union County")
    assert bound["action"] == "Rip Current Statement is in effect for Union County."


def test_an_ntas_bulletin_with_no_level_still_says_one_is_active():
    b = banner(driver=reading("ntas", ""))
    assert b["action"] == "A national terrorism advisory bulletin is active."
    assert b["hazard_name"] is None


def test_space_weather_with_no_scale_still_says_nothing_to_do():
    b = banner(driver=reading("space_weather", ""))
    assert b["imperative"] == "Nothing to do indoors"
    assert b["action"] == "GPS and radio may be unreliable outdoors."


def test_an_armed_house_names_the_open_sensor_off_its_ids_not_its_detail():
    """The coordinator carries the ids structured now; the log line beside
    them is never parsed. Proven by giving the two different contents."""
    b = banner(stage="critical",
               driver=reading("alarm", "armed_away", "alarm armed_away, open: cover.something_else",
                              ids=["binary_sensor.front_door_sensor_door_sensor"]),
               names_of=names_of)
    assert b["imperative"] == "Close the Front Door — the house is armed"
    assert b["hazard_name"] == "Armed with a door open"


def test_a_driver_reading_with_no_kind_the_matrix_knows_falls_to_the_cell_text():
    b = banner(driver={"key": "future", "slug": "future", "kind": "novel", "name": "Future Row"})
    assert b["imperative"] == DEFAULT_TEXT[CELL_ALERT][0]
    assert b["hazard_source"] == "Future Row"
    assert b["hazard_driver"] == "future"


def test_no_driver_at_all_is_an_empty_hazard():
    h = hazard_now(None)
    assert h == {"driver": None, "label": None, "name": None, "window": None, "guidance": None}


# ============================================================ helper text

@pytest.mark.parametrize("not_set", [None, "unknown", "unavailable", "", "   ", 7])
def test_a_helper_that_is_not_set_leaves_the_default_in_place(not_set):
    b = banner(directive="shelter", helper_text=lambda cell, suffix: not_set)
    assert b["imperative"] == DEFAULT_TEXT[CELL_ELEV_SHELTER][0]
    assert b["action"] == DEFAULT_TEXT[CELL_ELEV_SHELTER][1]


def test_a_set_helper_overrides_an_instruction_cell():
    def helper(cell, suffix):
        return "Everyone upstairs" if suffix == "imperative" else None

    b = banner(directive="shelter", helper_text=helper)
    assert b["imperative"] == "Everyone upstairs"
    assert b["action"] == DEFAULT_TEXT[CELL_ELEV_SHELTER][1]


def test_a_named_hazard_outranks_the_helper_on_a_generic_cell_only():
    helper = lambda cell, suffix: "Helper words"  # noqa: E731
    generic = banner(driver=reading("local_nws", "Heat Advisory"), helper_text=helper)
    assert generic["imperative"] == EVENT_GUIDANCE["Heat Advisory"][0]
    # The twin, both ways: an instruction cell keeps the helper over the
    # same hazard, and the generic cell keeps the helper once the hazard
    # cannot be named.
    instruction = banner(directive="shelter", driver=reading("local_nws", "Heat Advisory"),
                         helper_text=helper)
    assert instruction["imperative"] == "Helper words"
    unnamed = banner(driver=None, helper_text=helper)
    assert unnamed["imperative"] == "Helper words"


def test_unavailable_reads_no_helper_and_has_no_imperative():
    calls = []

    def helper(cell, suffix):
        calls.append(cell)
        return "should not be read"

    b = banner(stage="unknown", directive="unknown", helper_text=helper)
    assert b["cell"] == CELL_UNAVAILABLE
    assert calls == []
    assert b["imperative"] == ""
    assert b["stage_word"] == "UNAVAILABLE" and b["stage_tone"] == TONE_STALE


# ================================================================== tones

def test_quiet_tints_a_watch_and_never_a_crit_and_an_unreadable_quiet_is_not_on():
    assert banner(quiet=True)["tone"] == TONE_NEUTRAL
    assert banner(quiet=True)["stage_tone"] == TONE_WATCH
    assert banner(stage="critical", quiet=True)["tone"] == TONE_CRIT
    # The coordinator publishes None when the sleep helper cannot be read;
    # that is not "on".
    unread = banner(quiet=None)
    assert unread["tone"] == TONE_WATCH and unread["quiet"] is False


def test_normal_is_the_empty_row():
    b = banner(stage="normal")
    assert b["cell"] is None and b["gate"] == GATE_NONE
    assert b["imperative"] == "" and b["action"] == ""
    assert b["stage_on"] is False and b["stage_tone"] is None
    assert b["evacuate"] is False


def test_evacuate_is_exclusive_from_any_stage():
    b = banner(stage="normal", directive="evacuate")
    assert b["gate"] == GATE_EVACUATE and b["evacuate"] is True
    assert b["imperative"] == "EVACUATE" and b["tone"] == TONE_CRIT


# ============================================================ status line

def test_the_status_line_drops_a_part_that_repeats_the_stage_word_or_another_part():
    assert status_parts("ELEVATED", True, {"name": "Elevated", "label": "NTAS", "window": None}) == ["NTAS"]
    assert status_parts("ELEVATED", True, {"name": "Perimeter open", "label": "Perimeter",
                                           "window": "Open more than 5 minutes"}) \
        == ["Perimeter open", "Open more than 5 minutes"]
    # The twin: three distinct parts all survive, and at Normal the word
    # is not in the comparison at all.
    assert len(status_parts("ELEVATED", True,
                            {"name": "Heat", "label": "NWS", "window": "until 8PM"})) == 3
    assert status_parts("NORMAL", False, {"name": "Normal", "label": None, "window": None}) == ["Normal"]


def test_the_window_is_the_dwell_for_the_perimeter_and_the_until_clause_for_weather():
    perim = banner(driver=reading("perimeter_open", "1 open of 8",
                                  ids=["binary_sensor.front_door_sensor_door_sensor"],
                                  open_seconds=300), names_of=names_of)
    assert perim["hazard_window"] == "Open more than 5 minutes"
    assert perim["imperative"] == "Close the Front Door"
    one = banner(driver=reading("perimeter_open", "1 open of 8", ids=["cover.x"], open_seconds=45))
    assert one["hazard_window"] == "Open more than 1 minute"
    wx = banner(driver=reading("local_nws", "Heat Advisory"),
                stage_detail="Heat Advisory issued today until 8:00PM EDT by NWS Somewhere")
    assert wx["hazard_window"] == "until 8:00PM EDT"


def test_humanize_headline_keeps_a_shape_it_does_not_recognise():
    assert humanize_headline("Heat Advisory", "Heat Advisory") == "Heat Advisory"
    assert humanize_headline("Anything at all", None) == "Anything at all"
    assert humanize_headline("   ", None) == ""
    assert humanize_headline("Wind until noon by NWS X", "Wind") == "until noon"


# ================================================================== names

def test_names_come_off_the_friendly_name_then_the_id_and_lose_registry_noise():
    assert humanize_entity_name("Rear Gate Sensor Intrusion") == "Rear Gate"
    assert humanize_entity_name(None, "cover.workshop_workshop_door_door") == "Workshop Door"
    assert humanize_entity_name("Sensor", "binary_sensor.sensor") == "Sensor"
    assert humanize_entity_name("", None) is None
    assert humanize_entity_name("LAN Room Door Sensor Contact") == "LAN Room Door"


def test_join_names_counts_the_overflow_rather_than_dropping_it():
    assert join_names([]) is None
    assert join_names(["A"]) == "A"
    assert join_names(["A", "B"]) == "A and B"
    assert join_names(["A", "B", "C"]) == "A, B and C"
    assert join_names(["A", "B", "C", "D", "E"]) == "A, B, C and 2 more"


# ============================================================ the contract

def test_the_published_attribute_set_is_exactly_what_resolve_banner_returns():
    assert tuple(banner().keys()) == BANNER_ATTRIBUTES


def test_nothing_machine_shaped_reaches_a_line():
    """Every driver the coordinator can name, worded, with ids in hand and
    no friendly names to lean on: no entity_id and no underscore reaches
    the instruction, the status line or the hazard slots."""
    cases = [
        reading("alarm", "armed_away", ids=["binary_sensor.front_door_sensor_door_sensor"]),
        reading("alarm", "triggered", ids=["binary_sensor.north_gate_sensor_intrusion"]),
        reading("perimeter_open", "2 open of 8",
                ids=["binary_sensor.front_door_sensor_door_sensor", "cover.garage_door"],
                open_seconds=300),
        reading("outside_person", "on", ids=[DRIVEWAY, GATE]),
        reading("boil_water", "on"),
        reading("ntas", "Elevated"),
        reading("space_weather", "Storm (G1)"),
        reading("local_nws", "Heat Advisory"),
    ]
    for r in cases:
        b = banner(driver=r)
        for text in [b["imperative"], b["action"], b["hazard_name"] or "",
                     b["hazard_source"] or "", b["hazard_window"] or ""] + b["status"]:
            assert "binary_sensor." not in text and "cover." not in text, (r["key"], text)
            assert "_" not in text, (r["key"], text)


def test_the_generic_cells_are_the_only_ones_the_hazard_words():
    assert set(GENERIC_CELLS) == {CELL_ALERT, CELL_CRIT_NONE}
    hazard = reading("local_nws", "Heat Advisory")
    for cell_directive, cell in (("secure", "elev_secure"), ("shelter", CELL_ELEV_SHELTER),
                                 ("boil_water", CELL_BOIL_WATER)):
        b = banner(directive=cell_directive, driver=hazard)
        assert b["cell"] == cell
        assert b["imperative"] == DEFAULT_TEXT[cell][0]
