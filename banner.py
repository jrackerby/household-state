"""The rendering matrix — resolved once, here, and published on the
directive entity as attributes. No Home Assistant imports, deliberately,
for the same reason resolver.py has none: a matrix that can only be
exercised by moving the real world is a matrix that never gets exercised.

WHAT THIS IS (#30). The household banner's rendering matrix — which cell
the STAGE and DIRECTIVE words land in, what that cell says, what tone it
takes, what is driving it — used to be resolved in the browser by
ha-dashboard-kit's `directive.ts` and `hazard.ts` from three sensors this
integration already computes. Every surface that wanted the same answer
(the companion app, a voice assistant, a second dashboard) would have had
to carry a second copy of 868 lines, and two copies of a safety
instruction drift. The cell is now resolved here and published as
attributes of `sensor.household_state_directive`; a surface renders the
cell and proves the display only.

THE CELL IS COPY, THE DIRECTIVE IS THE CONTRACT. Nothing here can promote
or demote an axis: resolve_directive() decides WHICH directive fires and
this module decides only how the resulting (stage, directive) pair is
worded and coloured. The rules it applies are the kit's design contract
(`jrackerby/ha-dashboard-kit/docs/DESIGN_CONTRACT.md` §3–4), restated in
this repo's contract under "The rendering matrix".

INPUT is the resolved axes and the STAGE driver's own reading; OUTPUT is a
plain dict of the attributes the entity publishes. The caller supplies two
lookups — an entity's household name, and an operator's own wording for a
cell — because both need the state machine and a function that needs the
state machine cannot be tested by inspection.
"""

import re

from .const import (
    DIRECTIVE_BOIL_WATER,
    DIRECTIVE_EVACUATE,
    DIRECTIVE_SECURE,
    DIRECTIVE_SHELTER,
    STAGE_CRITICAL,
    STAGE_ELEVATED,
    STAGE_NORMAL,
)

# ---------------------------------------------------------------------
# The cells. `normal + no directive` is the one row a banner never shows
# and resolves to None: nothing to state, and no banner to state it on.
# ---------------------------------------------------------------------
CELL_ALERT = "alert"                 # elevated, and DIRECTIVE had nothing to say
CELL_BOIL_WATER = "boil_water"       # the one non-movement instruction, either stage
CELL_ELEV_SECURE = "elev_secure"
CELL_ELEV_SHELTER = "elev_shelter"
CELL_CRIT_NONE = "crit_none"         # critical, and DIRECTIVE had nothing to say
CELL_CRIT_SECURE = "crit_secure"
CELL_CRIT_SHELTER = "crit_shelter"
CELL_EVACUATE = "evacuate"           # exclusive; reachable from any stage
CELL_UNAVAILABLE = "unavailable"     # an axis could not be read

CELLS = (
    CELL_ALERT, CELL_BOIL_WATER, CELL_ELEV_SECURE, CELL_ELEV_SHELTER,
    CELL_CRIT_NONE, CELL_CRIT_SECURE, CELL_CRIT_SHELTER, CELL_EVACUATE,
    CELL_UNAVAILABLE,
)

# THE GATE VERDICT: what a surface mounts. `evacuate` inverts the field and
# nothing co-renders with it; `banner` is every other cell; `none` is the
# empty row at Normal.
GATE_NONE = "none"
GATE_BANNER = "banner"
GATE_EVACUATE = "evacuate"

# Tones are the kit's status ramp words, published as-is so a surface maps
# them to its palette without a second vocabulary.
TONE_GOOD = "good"
TONE_WATCH = "watch"
TONE_CRIT = "crit"
TONE_STALE = "stale"
TONE_NEUTRAL = "neutral"

CELL_TONE = {
    CELL_ALERT: TONE_WATCH,
    CELL_BOIL_WATER: TONE_WATCH,
    CELL_ELEV_SECURE: TONE_WATCH,
    CELL_ELEV_SHELTER: TONE_WATCH,
    CELL_CRIT_NONE: TONE_CRIT,
    CELL_CRIT_SECURE: TONE_CRIT,
    CELL_CRIT_SHELTER: TONE_CRIT,
    CELL_EVACUATE: TONE_CRIT,
    CELL_UNAVAILABLE: TONE_STALE,
}

# The two cells with no hazard of their own. Every other cell's text IS the
# household instruction — it names the closet, the way out — and hazard
# wording must never displace it. These two are the catch-alls, and they
# are the only cells the hazard guidance below is consulted for.
GENERIC_CELLS = (CELL_ALERT, CELL_CRIT_NONE)

# Code defaults per cell: (imperative, action). An operator's own wording
# for a cell, read through the `helper_text` lookup, overrides these; a
# helper that has never been set does not. `unavailable` has no helper — a
# transport fact, not a household one — and deliberately no imperative:
# the stage word already says UNAVAILABLE, and printing it twice stacked is
# a stutter. crit_none names no location on purpose: a negated instruction
# ("no closet needed") is the wrong thing to hand someone under stress.
DEFAULT_TEXT = {
    CELL_ALERT: ("Be on alert", "Something may be developing."),
    # The advisory is a PRECAUTION, so the action says what to do, not that
    # the tap is unsafe. Overstating it is how a real advisory gets ignored.
    CELL_BOIL_WATER: (
        "Boil water before drinking",
        "Cooking and brushing teeth too. Bottled water is fine.",
    ),
    CELL_ELEV_SECURE: ("Check the perimeter", "Doors and windows shut, everyone inside."),
    CELL_ELEV_SHELTER: ("Get ready to shelter", "Know your way to the main closet."),
    CELL_CRIT_NONE: ("Conditions are severe", "Stay inside and stay alert."),
    CELL_CRIT_SECURE: ("Secure the house", "Lock up, everyone inside and accounted for."),
    CELL_CRIT_SHELTER: ("Go to the main closet", "Away from windows."),
    CELL_EVACUATE: ("EVACUATE", "Leave the house now."),
    CELL_UNAVAILABLE: ("", "The household posture axis is not reporting."),
}

# Where a STAGE driver came from, in the household's words. Keyed on the
# SOURCES key; a row not listed falls back to its own `name`, which is a
# human phrase already, never the registry key.
SOURCE_LABEL = {
    "local_nws": "National Weather Service",
    "ntas": "National Terrorism Advisory",
    "space_weather": "Space weather",
    "alarm": "Alarm",
    "perimeter_open": "Perimeter",
    "boil_water": "Water utility",
    "outside_person": "Outside cameras",
}

# KEYED ON THE NWS EVENT NAME, which is the weather source's `raw_state`.
# Only events that can actually reach a generic cell are here: the names
# in DIRECTIVE_EVENT_MAP promote to a real directive whose cell carries
# the household's own instruction, and this table must not compete with
# it. Tornado Warning and Extreme Wind Warning normally resolve to a
# shelter cell; their entries exist for the case where the CAP response is
# missing on the alert and severity 7 still drives stage to critical with
# no directive to show — a blank instruction during a tornado warning is
# the failure this whole structure exists to make impossible.
#
# NONE OF THESE NAMES THE SHELTER LOCATION. The closet belongs to the
# shelter cells; tests/test_banner.py asserts the word never appears here.
EVENT_GUIDANCE = {
    # --- severity 7, critical, only reachable with no CAP response -----
    "Tornado Warning": (
        "Get away from the windows now",
        "Lowest floor, innermost wall, and stay there until it passes.",
    ),
    "Extreme Wind Warning": (
        "Move away from every window now",
        "Interior wall, lowest floor. This wind will break glass.",
    ),
    "Flash Flood Emergency": (
        "Get to higher ground now",
        "Do not drive. Move up, not out.",
    ),
    # --- severity 5, critical -----------------------------------------
    "Severe Thunderstorm Warning": (
        "Stay inside and away from the windows",
        "Damaging wind and hail are in the area. Expect the power to blink.",
    ),
    "Flash Flood Warning": (
        "Do not drive — water is rising now",
        "Stay off low roads and out of the creek until it clears.",
    ),
    "Ice Storm Warning": (
        "Stay off the roads",
        "Charge phones and torches now — ice brings the power down.",
    ),
    # --- severity 4, elevated -----------------------------------------
    "Tornado Watch": (
        "Keep your phone on you",
        "Conditions can produce a tornado. Bring everyone and the pets inside.",
    ),
    "Winter Storm Warning": (
        "Do not travel unless you have to",
        "Roads will ice over. Charge phones and torches.",
    ),
    "Flood Warning": (
        "Do not drive through flooded roads",
        "Turn around. Move anything low in the yard.",
    ),
    # --- severity 3, elevated -----------------------------------------
    "Severe Thunderstorm Watch": (
        "Bring everyone and the pets inside",
        "Storms could turn severe. Put away anything loose outside.",
    ),
    "High Wind Warning": (
        "Secure anything loose outside",
        "Bins, umbrellas, trampoline. Stay clear of trees and expect the power to go out.",
    ),
    # --- severity 2, elevated -----------------------------------------
    "Heat Advisory": (
        "Stay out of the afternoon heat",
        "Drink water, and check on anyone working outside.",
    ),
    "Wind Advisory": (
        "Put away anything loose outside",
        "Bins, umbrellas, trampoline. Expect the power to blink.",
    ),
    "Flood Advisory": (
        "Do not drive through standing water",
        "The low spots on the road go under first.",
    ),
    # --- severity 1, elevated -----------------------------------------
    "Special Weather Statement": (
        "Keep an eye on the weather",
        "Nothing to do yet — the forecast is worth a look before you go out.",
    ),
}

# Registry words a household member standing at a wall never needs.
# Trailing only, and never to nothing: "Rear Gate Sensor Intrusion" ->
# "Rear Gate", while a name made entirely of noise keeps its original.
_NAME_NOISE = frozenset(
    {"sensor", "contact", "intrusion", "detector", "detection", "state", "status"}
)

# THE PUBLISHED ATTRIBUTE SET, declared once. sensor.py publishes exactly
# these keys off resolve_banner()'s result, always present, so a consumer
# can tell "no cell" (None) from "an older component that had no matrix".
BANNER_ATTRIBUTES = (
    "cell", "gate", "imperative", "action", "tone",
    "stage_word", "stage_on", "stage_tone", "quiet", "evacuate",
    "status", "hazard_driver", "hazard_source", "hazard_name", "hazard_window",
)

_EMPTY_HAZARD = {
    "driver": None,
    "label": None,
    "name": None,
    "window": None,
    "guidance": None,
}


# ---------------------------------------------------------------------
# The matrix itself.
# ---------------------------------------------------------------------
def resolve_cell(stage, directive):
    """(stage word, directive word) -> cell, or None for the empty row.

    EVACUATE is checked first and unconditionally: it is exclusive and
    reachable from any stage. A stage word this file has never seen is not
    Normal and never green — it reads the same as unreadable.
    """
    if directive == DIRECTIVE_EVACUATE:
        return CELL_EVACUATE
    if stage is None or directive is None:
        return CELL_UNAVAILABLE
    if stage == "unknown" or directive == "unknown":
        return CELL_UNAVAILABLE
    if stage == STAGE_NORMAL:
        return None
    if stage == STAGE_ELEVATED:
        if directive == DIRECTIVE_SECURE:
            return CELL_ELEV_SECURE
        if directive == DIRECTIVE_SHELTER:
            return CELL_ELEV_SHELTER
        if directive == DIRECTIVE_BOIL_WATER:
            return CELL_BOIL_WATER
        return CELL_ALERT
    if stage == STAGE_CRITICAL:
        if directive == DIRECTIVE_SECURE:
            return CELL_CRIT_SECURE
        if directive == DIRECTIVE_SHELTER:
            return CELL_CRIT_SHELTER
        # At critical a boil advisory has already lost the axis to anything
        # more urgent, so reaching here with it means the water IS the
        # worst thing known, and it keeps the instruction row.
        if directive == DIRECTIVE_BOIL_WATER:
            return CELL_BOIL_WATER
        return CELL_CRIT_NONE
    return CELL_UNAVAILABLE


def gate_for(cell):
    if cell is None:
        return GATE_NONE
    if cell == CELL_EVACUATE:
        return GATE_EVACUATE
    return GATE_BANNER


# ---------------------------------------------------------------------
# Names, in the household's words.
# ---------------------------------------------------------------------
def humanize_entity_name(friendly_name, entity_id=None):
    """An entity's name for a wall: `friendly_name` first, the entity_id's
    object part second (genuinely worse — HA mints ids by concatenating
    device and entity names, so real members read
    `front_door_sensor_door_sensor`). A repeated word is collapsed on both
    paths, then trailing registry noise is dropped."""
    from_id = ""
    if entity_id and "." in entity_id:
        from_id = " ".join(
            w[:1].upper() + w[1:]
            for w in entity_id.split(".", 1)[1].split("_")
            if w
        )
    source = (friendly_name or "").strip() or from_id
    if not source:
        return None
    seen = set()
    words = []
    for w in source.split():
        k = w.lower()
        if k in seen:
            continue
        seen.add(k)
        words.append(w)
    trimmed = list(words)
    while len(trimmed) > 1 and trimmed[-1].lower() in _NAME_NOISE:
        trimmed.pop()
    out = " ".join(trimmed or words).strip()
    return out or source


def join_names(names, max_named=3):
    """Names the way somebody says them, bounded so the instruction row —
    the largest type on a board — cannot be pushed off the glass. Past the
    bound the overflow is COUNTED, never dropped: a list cut at three
    reads as a complete one."""
    listed = [n.strip() for n in names if n and n.strip()]
    if not listed:
        return None
    if len(listed) == 1:
        return listed[0]
    if len(listed) <= max_named:
        return ", ".join(listed[:-1]) + " and " + listed[-1]
    return ", ".join(listed[:max_named]) + " and " + str(len(listed) - max_named) + " more"


def _names_of(ids, names_of):
    out = []
    for eid in ids or ():
        friendly = names_of(eid) if names_of is not None else None
        name = humanize_entity_name(friendly, eid)
        if name:
            out.append(name)
    return out


def humanize_headline(headline, event_name):
    """A CAP headline for the status line. Keep the `until` clause, drop the
    issuing-office tail, and return the headline unchanged when the shape
    is not the one NWS emits."""
    text = (headline or "").strip()
    m = re.search(r"\buntil\b.*", text, flags=re.IGNORECASE)
    trimmed = re.sub(r"\s+by\s+NWS\b.*$", "", m.group(0) if m else text,
                     flags=re.IGNORECASE).strip()
    if not trimmed:
        return text
    if m is None and event_name and trimmed.lower() == event_name.lower():
        return text
    return trimmed


def _open_duration(seconds):
    if seconds is None:
        return None
    mins = max(1, int(round(seconds / 60)))
    return "Open more than " + str(mins) + " minute" + ("" if mins == 1 else "s")


# ---------------------------------------------------------------------
# What is driving STAGE, named.
# ---------------------------------------------------------------------
def _hazard_name(driver):
    kind = driver.get("kind")
    raw = (driver.get("raw_state") or "").strip()
    if kind == "perimeter":
        return "Perimeter open"
    if kind == "alarm":
        if raw == "triggered":
            return "Alarm triggered"
        # The CONDITION label, not the finding: the instruction row names
        # the actual sensor, and naming it twice in adjacent rows is the
        # repetition the contract drops rather than prints.
        return "Armed with a door open" if raw else None
    if kind == "binary_hazard":
        # `on` is the state, the row's name is the finding.
        return driver.get("name") or None
    return raw or None


def _driver_guidance(driver, names_of, jurisdiction):
    """The fallback when the driver is not the weather feed, or is the
    weather feed carrying an event EVENT_GUIDANCE has never heard of. None
    is a legitimate answer — the cell's own text then stands."""
    key = driver.get("key")
    kind = driver.get("kind")
    raw = (driver.get("raw_state") or "").strip()
    ids = driver.get("ids") or []

    if kind == "alarm":
        tripped = join_names(_names_of(ids, names_of))
        if raw == "triggered":
            return (
                "The alarm is sounding",
                (tripped + " tripped it. " if tripped else "")
                + "Do not open the door to anyone you did not let in.",
            )
        if tripped:
            return (
                "Close the " + tripped + " — the house is armed",
                "Disarm first if someone needs to go through.",
            )
        return (
            "Close up — the house is armed with something open",
            "Close it, or disarm before anyone goes through.",
        )

    if kind == "perimeter":
        # THE WHOLE POINT OF THIS BRANCH IS THE NAME. The generic wording is
        # reached only when the row named nothing, which is a shape change
        # worth noticing rather than a state to paper over.
        named = join_names(_names_of(ids, names_of))
        if named:
            # No duration here: the status line carries it, and saying it
            # twice is the stutter this module exists to remove.
            return ("Close the " + named, "Check the perimeter if nobody is out there.")
        return (
            "Something has been left open",
            "A door or gate is open — check the perimeter.",
        )

    if key == "ntas":
        return (
            "Stay aware in public places",
            "National Terrorism Advisory: " + raw + "."
            if raw else "A national terrorism advisory bulletin is active.",
        )

    if key == "space_weather":
        # Nothing in the house needs doing, and saying so is the useful
        # answer — a red that never clears teaches everyone to ignore red.
        return (
            "Nothing to do indoors",
            (raw + " — " if raw else "") + "GPS and radio may be unreliable outdoors.",
        )

    if key == "boil_water":
        # The STAGE row of the advisory. Normally the DIRECTIVE row lands
        # this on the boil cell with its own text; if only the stage row is
        # bound, the generic cell still says what to do about the water.
        return DEFAULT_TEXT[CELL_BOIL_WATER]

    if key == "outside_person":
        seen = join_names(_names_of(ids, names_of))
        return (
            "Someone is outside",
            ("Seen by the " + seen + ". " if seen else "An outside camera saw a person. ")
            + "Check the cameras before you open a door.",
        )

    if kind == "severity_attr" and raw:
        # An event name the ramp has never seen still reaches glass. Name
        # it rather than inventing an instruction for a hazard this file
        # cannot recognise.
        where = " for " + jurisdiction if jurisdiction else ""
        return ("Keep an eye on the weather", raw + " is in effect" + where + ".")

    return None


def hazard_now(driver, stage_detail=None, names_of=None, jurisdiction=None):
    """Resolve what is driving STAGE right now, from the driver's own
    reading. `driver` is the coordinator's reading dict for the row STAGE
    named (key, slug, kind, name, raw_state, detail, ids, open_seconds), or
    None at Clear and whenever stage could not be resolved."""
    if not driver:
        return dict(_EMPTY_HAZARD)

    raw = (driver.get("raw_state") or "").strip()
    name = _hazard_name(driver)
    # Event name first, driver fallback second — an event this file
    # recognises is always more specific than the feed it arrived on.
    guidance = EVENT_GUIDANCE.get(raw) or _driver_guidance(driver, names_of, jurisdiction)

    if driver.get("kind") == "perimeter":
        window = _open_duration(driver.get("open_seconds"))
    elif stage_detail:
        window = humanize_headline(stage_detail, name)
    else:
        window = None
    # Dedupe against every other line, not just the reason: the perimeter
    # driver once built its instruction and this tail from the same
    # humanised opening and printed both, stacked.
    already = {v.lower() for v in (name, guidance[1] if guidance else None) if v}
    if window and window.lower() in already:
        window = None

    return {
        "driver": driver.get("slug") or driver.get("key"),
        "label": SOURCE_LABEL.get(driver.get("key"), driver.get("name")) or None,
        "name": name,
        "window": window,
        "guidance": guidance,
    }


def status_parts(stage_word, stage_on, hazard):
    """The status line: reason, source, duration, as one uniform line. The
    stage word is a corner pill and is NOT printed here, but it is still
    compared: NTAS publishes the bare word "Elevated" as its reason under a
    stage that is also ELEVATED. A part repeating an earlier part is
    dropped, substring either way, case-insensitive."""
    said = [stage_word] if stage_on and stage_word else []
    parts = []
    for c in (hazard.get("name"), hazard.get("label"), hazard.get("window")):
        if not c:
            continue
        lower = c.lower()
        if any(p.lower() in lower or lower in p.lower() for p in said):
            continue
        said.append(c)
        parts.append(c)
    return parts


# ---------------------------------------------------------------------
# The published cell.
# ---------------------------------------------------------------------
def _cell_text(cell, hazard, helper_text):
    """Cell text, in the order that produces the most specific line the
    system can stand behind. For the instruction cells: the operator's own
    wording, then the code default — those words ARE the household fact.
    For the two generic cells the hazard's own line comes FIRST: the
    helper answers "the stage moved and we cannot say why", and the moment
    the driver IS named that premise is gone."""
    guidance = hazard.get("guidance")
    if guidance and cell in GENERIC_CELLS:
        return guidance[0], guidance[1]
    default = DEFAULT_TEXT[cell]
    if cell == CELL_UNAVAILABLE or helper_text is None:
        return default

    def read(suffix, fallback):
        v = helper_text(cell, suffix)
        # `unknown` is HA's own state for a helper never set; empty is the
        # other "not set" shape. Both degrade to the default.
        if v is None or not isinstance(v, str):
            return fallback
        if v in ("unknown", "unavailable") or not v.strip():
            return fallback
        return v

    return read("imperative", default[0]), read("action", default[1])


def resolve_banner(*, stage, directive, quiet, driver=None, stage_detail=None,
                   helper_text=None, names_of=None, jurisdiction=None):
    """The one function the coordinator calls. Returns the attribute dict."""
    cell = resolve_cell(stage, directive)
    hazard = hazard_now(driver, stage_detail, names_of, jurisdiction)

    word = (stage or "").strip().lower()
    known = word in (STAGE_NORMAL, STAGE_ELEVATED, STAGE_CRITICAL)
    stage_word = word.upper() if known else "UNAVAILABLE"
    stage_on = (word != STAGE_NORMAL) if known else True
    # The stage's own colour, modified by nothing — QUIET tints the banner
    # and must not take the elevation's amber away with it.
    if word == STAGE_CRITICAL:
        stage_tone = TONE_CRIT
    elif word == STAGE_ELEVATED:
        stage_tone = TONE_WATCH
    elif known:
        stage_tone = None
    else:
        stage_tone = TONE_STALE

    quiet_on = quiet is True

    if cell is None:
        imperative, action, tone = "", "", TONE_GOOD
    else:
        imperative, action = _cell_text(cell, hazard, helper_text)
        # QUIET tints, never suppresses — and never at critical: a red
        # banner going indigo because someone is napping is the one place
        # this modifier could hide something that matters.
        tone = CELL_TONE[cell]
        if quiet_on and tone != TONE_CRIT:
            tone = TONE_NEUTRAL

    return {
        "cell": cell,
        "gate": gate_for(cell),
        "imperative": imperative,
        "action": action,
        "tone": tone,
        "stage_word": stage_word,
        "stage_on": stage_on,
        "stage_tone": stage_tone,
        "quiet": quiet_on,
        "evacuate": cell == CELL_EVACUATE,
        "status": status_parts(stage_word, stage_on, hazard),
        "hazard_driver": hazard["driver"],
        "hazard_source": hazard["label"],
        "hazard_name": hazard["name"],
        "hazard_window": hazard["window"],
    }
