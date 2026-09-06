"""Pure resolution of §11.3 — no Home Assistant imports, deliberately.

THIS FILE MUST STAY IMPORT-FREE OF `homeassistant.*`. That is what makes
§11.18's obligation payable: the conflict table (fire + tornado, tornado
+ intrusion, nap + severe weather, FLS offline + everything, evacuate +
degraded, all inputs unavailable, every input fresh and idle) can be
run against this function directly, with no live state and no restart.
A resolver that can only be exercised by moving the real world is a
resolver that never gets exercised.

INPUT is a list of reading dicts, each:
    {key, name, axis, disposition, severity, raw_state, detail}
`severity` is None whenever disposition is not `ok`. It is never 0 as a
stand-in for "could not read" — that substitution is KAN-139.

OUTPUT is a plain dict. The caller applies the fall dwell and the
persisted ages; neither belongs here, because both need a clock and a
function that needs a clock cannot be tested by inspection.
"""

from .const import (
    ALARM_ARMED_OPEN_SEV,
    AXIS_DIRECTIVE,
    AXIS_INTEGRITY,
    AXIS_STAGE,
    BAND_CLEAR,
    BAND_CRITICAL,
    BAND_ELEVATED,
    BAND_UNKNOWN,
    CAP_ABSENT,
    DIRECTIVE_EVACUATE,
    DIRECTIVE_EVENT_MAP,
    DIRECTIVE_EVENT_SUPPRESS,
    DIRECTIVE_NULL,
    DIRECTIVE_RESPONSE_MAP,
    DIRECTIVE_SECURE,
    DIRECTIVE_SHELTER,
    DIRECTIVE_UNKNOWN,
    DISP_OK,
    INTEGRITY_DEGRADED,
    INTEGRITY_OK,
    INTEGRITY_UNKNOWN,
    DIRECTIVE_BOIL_WATER,
    STAGE_CRITICAL,
    STAGE_ELEVATED,
    STAGE_NORMAL,
    STAGE_UNKNOWN,
    TIEBREAK,
)


def band_for(severity):
    """§7 bands. 0 Clear / 1-4 Elevated / 5-7 Critical."""
    if severity is None:
        return BAND_UNKNOWN
    if severity <= 0:
        return BAND_CLEAR
    if severity <= 4:
        return BAND_ELEVATED
    return BAND_CRITICAL


def stage_for(severity):
    if severity is None:
        return STAGE_UNKNOWN
    if severity <= 0:
        return STAGE_NORMAL
    if severity <= 4:
        return STAGE_ELEVATED
    return STAGE_CRITICAL


def resolve_directive(rows):
    """§11.9 mapped onto §11.3's precedence rules. KAN-208, extended KAN-336.

    Returns (directive, reason, driver, suppressed).

    RULE 2 OF §11.3: EVACUATE IS EXCLUSIVE and is never reached by
    aggregation — it is only ever returned because one alert said
    `Evacuate` outright, whether by CAP's `response` or by DIRECTIVE_EVENT_MAP.

    TWO CLASSIFIERS, BOTH RUN ON EVERY PAIR. NWS's own non-weather event
    names (Law Enforcement Warning, Shelter In Place Warning, ...) carry
    their real meaning in the event name itself, not in CAP's generic
    `responseType` — the same reasoning the local severity ramp already
    applies to Tornado Warning — so DIRECTIVE_EVENT_MAP supplies a default
    finding for those event names. It does NOT suppress the response-based
    classifier on the same pair: a Law Enforcement Warning defaults to
    `secure`, but if that SAME alert also carries a more urgent CAP
    `response` (Shelter, or Evacuate), that finding is added too, and the
    precedence loop below — never either classifier — decides which one
    wins. An event-name default must never be able to downgrade an
    alert-specific CAP signal.

    §11.20 decision 4, extended KAN-336: an event in DIRECTIVE_EVENT_SUPPRESS
    is declined regardless of which classifier would have promoted it, and
    the decline is RECORDED, never silent. `suppressed` is returned so the
    entity can say what it declined; "no directive applies" and "a directive
    applied and we declined it" must not collapse.

    KAN-139 ON THIS AXIS TOO: an alert whose `response` field is missing
    means we cannot say there is no directive, so the answer is
    `unknown` — but only if nothing positive was found first. A Shelter
    we CAN see is not withheld because a second alert was unreadable.
    Absence of `response` never blocks an EVENT_MAP match — that
    classifier does not read `response` at all.
    """
    # GH-583. The axis is no longer CAP-only, so split by kind before any
    # early return. A `binary_hazard` row states its directive outright --
    # there is no payload to classify, it either applies or it does not.
    cap_rows = [r for r in rows if r.get("kind") != "binary_hazard"]
    hazard_rows = [r for r in rows if r.get("kind") == "binary_hazard"]

    found = []
    suppressed = []
    absent = 0
    unreadable = 0

    for r in hazard_rows:
        if r["disposition"] != DISP_OK:
            # Same rule the CAP branch applies to a missing `response`: an
            # unreadable hazard row means we cannot say there is NO
            # directive. It never forces `unknown` on its own -- a finding
            # we CAN see still wins below.
            unreadable = unreadable + 1
            continue
        if (r.get("severity") or 0) > 0:
            found.append((r["directive_when_on"], r["name"]))

    if not cap_rows:
        if not found:
            return DIRECTIVE_UNKNOWN, "no_cap_source", None, []
    else:
        healthy_cap = [r for r in cap_rows if r["disposition"] == DISP_OK]
        if not healthy_cap:
            unreadable = unreadable + 1
        cap_rows = healthy_cap

    for r in cap_rows:
        for p in r.get("pairs") or []:
            resp = p.get("response")
            event = p.get("event")
            event_suppressed = event in DIRECTIVE_EVENT_SUPPRESS

            # BOTH classifiers run, independently, on the SAME pair. An
            # event-name default (e.g. Law Enforcement Warning -> secure)
            # must never suppress a MORE urgent, alert-specific CAP response
            # on that same alert (e.g. that LEW also carrying
            # response: Evacuate) -- only the precedence loop below decides
            # which finding wins. Suppression still applies to each
            # classifier independently, so a suppressed event's response is
            # never promoted through the back door either.
            event_mapped = DIRECTIVE_EVENT_MAP.get(event)
            if event_mapped is not None:
                if event_suppressed:
                    suppressed.append(str(event) + " -> event")
                else:
                    found.append((event_mapped, event))

            if resp == CAP_ABSENT:
                absent = absent + 1
                continue
            mapped = DIRECTIVE_RESPONSE_MAP.get(resp)
            if mapped is None:
                continue
            if event_suppressed:
                suppressed.append(str(event) + " -> " + str(resp))
                continue
            found.append((mapped, event))

    for d, e in found:
        if d == DIRECTIVE_EVACUATE:
            return DIRECTIVE_EVACUATE, "cap_response", e, suppressed
    for d, e in found:
        if d == DIRECTIVE_SHELTER:
            return DIRECTIVE_SHELTER, "cap_response", e, suppressed
    for d, e in found:
        if d == DIRECTIVE_SECURE:
            return DIRECTIVE_SECURE, "cap_response", e, suppressed
    # LAST. A shelter or evacuate order always takes the instruction row
    # from this; water you must boil is not a reason to leave the closet.
    for d, e in found:
        if d == DIRECTIVE_BOIL_WATER:
            return DIRECTIVE_BOIL_WATER, "hazard_source", e, suppressed

    if unreadable and not found:
        return DIRECTIVE_UNKNOWN, "directive_source_unreadable", None, suppressed
    if absent:
        return (
            DIRECTIVE_UNKNOWN,
            "cap_response_absent_on_" + str(absent) + "_alert",
            None,
            suppressed,
        )
    if suppressed:
        return DIRECTIVE_NULL, "suppressed_by_policy", None, suppressed
    return DIRECTIVE_NULL, "no_directive_response", None, []


def resolve(readings):
    """Resolve every axis from the source readings.

    RULE 2 lives here and is the whole reason this function exists:
    an unhealthy source can never contribute 0. If nothing healthy
    reports a positive severity and something is unreadable, the answer
    is `unknown` — not `normal`.
    """
    stage_rows = [r for r in readings if r["axis"] == AXIS_STAGE]
    integ_rows = [r for r in readings if r["axis"] == AXIS_INTEGRITY]
    dir_rows = [r for r in readings if r["axis"] == AXIS_DIRECTIVE]

    healthy = [r for r in stage_rows if r["disposition"] == DISP_OK]
    unhealthy = [r for r in stage_rows if r["disposition"] != DISP_OK]

    # --- STAGE -------------------------------------------------------
    top = None
    driver = None
    detail = None
    for key in TIEBREAK:
        for r in healthy:
            if r["key"] != key:
                continue
            sev = r["severity"]
            if sev is None:
                continue
            if top is None or sev > top:
                top = sev
                driver = r["key"]
                detail = r["detail"] or r["raw_state"]

    if top is None:
        # Nothing healthy produced a number at all.
        severity = None if unhealthy else 0
    elif top == 0 and unhealthy:
        # RULE 2. Healthy sources are idle but we cannot see all of
        # them, so we do not get to say Normal.
        severity = None
    else:
        severity = top

    if severity is None:
        driver = None
        detail = "cannot resolve stage: " + str(len(unhealthy)) + " of " + str(
            len(stage_rows)
        ) + " sources unreadable"
    elif severity == 0:
        # KAN-210. Nothing is driving anything at Clear, but the loop
        # above will have named whichever key sits first in TIEBREAK,
        # purely because `top is None` on its first pass. A driver at
        # severity 0 is a name with no finding behind it — it is what
        # makes sensor.home_threat_posture read
        # "alarm_control_panel.alarmo" whenever the house is armed and
        # idle. There is no driver at Clear.
        driver = None
        detail = "no active local, state, weather, or perimeter threats"

    # Confidence is separate from the value. A positive severity read
    # from a partial source set is still actionable — it just is not a
    # complete picture, and saying so is cheaper than withholding it.
    if not unhealthy:
        confidence = "full"
    elif severity is None:
        confidence = "none"
    else:
        confidence = "partial"

    # --- INTEGRITY ---------------------------------------------------
    # §7.3: `unknown` is first-class and OUTRANKS `degraded`. There is
    # no severity on this axis (RULE 4) and adding one is the bug.
    integ_state = INTEGRITY_OK
    integ_detail = "all monitoring paths healthy"
    integ_affected = 0
    integ_driver = None

    unknown_rows = [r for r in integ_rows if r["disposition"] != DISP_OK]
    degraded_rows = [
        r
        for r in integ_rows
        if r["disposition"] == DISP_OK and r.get("integrity") == INTEGRITY_DEGRADED
    ]

    if unknown_rows:
        integ_state = INTEGRITY_UNKNOWN
        integ_driver = unknown_rows[0]["key"]
        integ_detail = "cannot read " + str(len(unknown_rows)) + " integrity source(s)"
        integ_affected = len(unknown_rows)
    elif degraded_rows:
        integ_state = INTEGRITY_DEGRADED
        integ_driver = degraded_rows[0]["key"]
        integ_detail = degraded_rows[0].get("integrity_detail") or "degraded"
        integ_affected = sum(int(r.get("affected") or 0) for r in degraded_rows)

    # KAN-343: PER-SOURCE BREAKDOWN, for integrity-card.js parity with the
    # retired packages/household_integrity.yaml `sources_detail` attribute.
    # label~state~detail rows, same idiom that file used. Built across
    # EVERY integrity row, not just the first degraded one integ_detail
    # names above: the aggregate axis only ever needs ONE driver to decide
    # ok/degraded/unknown, but an operator reading the card needs to see
    # all of them.
    #
    # ROWS ARE NEWLINE-JOINED, NOT PIPE-JOINED, AND THAT IS A DELIBERATE
    # FIX, NOT A COSMETIC CHOICE (LAW 4: a value joined into a delimited
    # channel must not be able to contain the delimiter). `detail` bodies
    # already use " | " as their OWN internal part-separator throughout
    # this codebase (detector_detail, lock_detail, sensor_detail, and this
    # ticket's own fire_life_safety_detail/security_detail) -- a bare `|`
    # row separator would silently tear a single multi-part detail into
    # two rows. Caught by this file's own hand-run self-test (no
    # homeassistant.* dependency, so it needed only a plain python3, per
    # this module's whole reason for existing) before it ever reached a
    # card. `~` never collides: label is a const.py string, state is a
    # fixed enum, and no detail body in this codebase uses it.
    # NAMES PREFIXED row_ ON PURPOSE: this function's STAGE section above
    # already owns bare `detail` (and `severity`, `driver`, `top`) as
    # function-scope locals -- Python has no block scoping, so a same-named
    # loop variable here would silently overwrite the STAGE section's value
    # for the rest of the function. It did, once: a first draft used bare
    # `detail`/`state` and the STAGE sensor's own `detail` attribute came
    # back live reading Critical Networking's text instead of "no active
    # local, state, weather, or perimeter threats" -- caught by reading the
    # deployed entity back (LAW 9), not by this file's own hand-run
    # self-test, which only exercised resolve() with integrity rows and
    # never noticed a STAGE row's output changing underneath it.
    integ_sources_detail_rows = []
    for r in integ_rows:
        if r["disposition"] != DISP_OK:
            integ_sources_detail_rows.append(r["name"] + "~unreadable~monitor unavailable")
            continue
        row_state = r.get("integrity") or "unreadable"
        row_detail = r.get("integrity_detail") or (
            "ok" if row_state == "ok" else "no detail reported"
        )
        integ_sources_detail_rows.append(r["name"] + "~" + str(row_state) + "~" + str(row_detail))
    integ_sources_detail = "\n".join(integ_sources_detail_rows)

    # --- DIRECTIVE ---------------------------------------------------
    # 0.3.0: a real source, so `none` is now a finding rather than a
    # synthesised all-clear. It is only ever returned when the CAP field
    # was read and nothing in it mapped.
    directive, directive_reason, directive_driver, directive_suppressed = resolve_directive(
        dir_rows
    )

    return {
        "severity": severity,
        "stage": stage_for(severity),
        "band": band_for(severity),
        "driver": driver,
        "detail": detail,
        "confidence": confidence,
        "sources_total": len(stage_rows),
        "sources_healthy": len(healthy),
        "sources_unhealthy": [r["key"] for r in unhealthy],
        "integrity": integ_state,
        "integrity_detail": integ_detail,
        "integrity_driver": integ_driver,
        "integrity_affected": integ_affected,
        "integrity_sources": len(integ_rows),
        "integrity_sources_detail": integ_sources_detail,
        "directive": directive,
        "directive_reason": directive_reason,
        "directive_driver": directive_driver,
        "directive_suppressed": directive_suppressed,
        "directive_sources": len(dir_rows),
    }


def alarm_severity(state, open_sensors):
    """§7 alarm ladder. Returns None for states that do not escalate."""
    if state == "triggered":
        from .const import ALARM_TRIGGERED_SEV

        return ALARM_TRIGGERED_SEV
    if state in ("armed_home", "armed_away", "armed_night", "armed_vacation"):
        if open_sensors:
            return ALARM_ARMED_OPEN_SEV
    return 0
