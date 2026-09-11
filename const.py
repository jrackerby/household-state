"""Constants and the source registry for household_state.

household_state 0.2.0 — 2026-08-08 (as household_alert; renamed 0.5.0)

0.9.0 — 2026-09-10, GH-717, Joel's ruling. THE INTEGRITY AXIS WAS
INVERTED AND THIS IS THE HALF OF THE FIX THAT LIVES HERE. `kiosk_live_page`
raised INTEGRITY when a pikiosk was on the wrong page; the dashboard server, the
server feeding every screen in the house, could be hard down for hours and
reach this registry not at all. The row is REMOVED, along with the
`live_page` kind, `_read_live_page` and `_live_page_entity_ids`. kiosk_pi
still publishes sensor.<host>_live_page and still dwells both facts -- the
signal did not die, it stopped being a household integrity fault. The other
half is packages/network_client_monitoring.yaml, which wires
binary_sensor.the dashboard server_health into Critical Networking Device Health.
tests/test_sources_unique.py pins the row gone so it is not re-added by a
later reading of KAN-260. No other row, dwell or disposition moved.

0.8.0 — 2026-09-06, GH-623. TWO ROWS STOP PUBLISHING A COUNT WHERE THEY
HOLD A NAME. The perimeter row named `sustained[0] + " +2 more"`, and the
alarm row scored itself off Alarmo's `open_sensors` and then published the
bare state — so a wall could say "something has been left open" while the
reading in hand knew exactly which door. Both now carry every id they
know, comma-joined; the surface does the humanising, because the raw name
belongs on the entity for the next diagnosis (LAW 10). No severity, dwell
or disposition moved.

0.5.0 — 2026-08-22, Joel. Renamed household_alert -> household_state: the
domain had stopped describing the scope once QUIET (a household activity
modifier, not a threat) joined STAGE/DIRECTIVE/INTEGRITY. Same change adds
QUIET itself — a read-only binary_sensor mirroring the bound sleep-mode helper
(binary_sensor.py's Quiet class). READ-ONLY, DELIBERATELY: no axis or
notification path is suppressed or rerouted by it yet; that is a separate,
future ruling. Kept OUT of SOURCES below on purpose — SOURCES feeds the
three threat axes and QUIET is not a threat input, so folding it in would
put a household-activity boolean through RULE 2/RULE 4's severity-
aggregation machinery, which it was never meant to pass through.

0.3.0 — KAN-208. DIRECTIVE stops being a placeholder and becomes an
axis with a real source and a real disposition model. The CAP `response`
field is projected onto the bound CAP sensor as raw pairs; the
vocabulary map and the suppression list live here, and the resolution
lives in resolver.py where it can be tested.

0.2.0 — KAN-209 + KAN-210, one edit, one restart.
  * PERIMETER OPEN, SUSTAINED joins the stage axis (§7's sev-2 driver
    with a 5-minute dwell). It is resolved from the fls_device LABEL at
    runtime, never from a pinned id list.
  * THE FLS TAMPER PAIR BECOMES ITS OWN INTEGRITY ROW. §7.3 has always
    specified two sources on the FLS health sensor — device liveness
    and perimeter tamper. 0.1.0 read tamper_integrity into a key nothing
    consumed, which is the same defect in a quieter costume.
  * NO DRIVER IS NAMED AT SEVERITY 0. The tiebreak loop named whichever
    key sat first in TIEBREAK simply because `top is None` on the first
    pass.
====================================================================
WHAT THIS IS. The resolver half of the household directive layer
specified in LAW §11. IT IS THAT LAYER NOW, not a second opinion beside
one: the comparison reference it shipped alongside is DELETED (LAW §3,
GH-663), deliberately, once its last consumer moved to
sensor.household_state_stage. Nothing backstops this component and
there is nothing left to diff it against.

IT HAS LIVE CONSUMERS, and has since KAN-343 (0.4.0): integrity-card.js
and room-panel.js's ring both default to
sensor.household_state_integrity, and
packages/household_state_integrity_notify.yaml wires it to the operator
phone-notification automation. THE WEAK LINK, stated where it will be
read: an entity id changed here reaches a wall. The "zero card edits,
zero dashboard edits, zero consumers" claim this header carried until
GH #7 was true at 0.1.0 and had been false for five releases.

WHY IT IS PYTHON AND NOT A TEMPLATE SENSOR. packages/home_posture.yaml
duplicates one computation across SIX lockstep blocks, each guarded by
`fls > 0`. That duplication is why §11.5 step 3b has been blocked for a
week — the severity cannot be changed without also editing six branches
and re-keying a card. One function replaces six blocks and is testable
without touching live state (§11.18's conflict table).

THE FOUR DEFECTS THIS SHAPE EXISTS TO KILL
  KAN-139  a driver going unavailable reads severity 0, so a dead feed
           renders green. Here EVERY source carries a disposition and
           an unreadable source can never contribute 0. See RULE 1.
  KAN-182  16 of 19 feedparser sensors never set up. A source that was
           never created is `absent`, which is a distinct disposition
           from `ok` with severity 0. See RULE 2.
  KAN-206  posture flapped Normal<->Elevated 23 times in 6 days for
           0-4s each. FALL_DWELL holds a fall, never a rise. See RULE 3.
  KAN-207  swpc reads Storm (G1) at severity 0 — display state and ramp
           disagree. Every source records BOTH its raw state string and
           its severity so the disagreement is an attribute, not a
           silent loss. See RULE 4.

RULES BAKED IN — DO NOT UNDO THEM (the kiosk_pi convention)
  1. THE COORDINATOR NEVER RAISES UpdateFailed. Raising takes every
     entity unavailable and attributes on an unavailable entity vanish,
     which is exactly how a broken collector comes to read green. It
     always returns a dict; an individual source returns None.
  2. UNKNOWN IS NOT NORMAL, AND NEVER GREEN (§11.3 rule 5). If any
     stage source is unhealthy and no healthy source reports a positive
     severity, stage is `unknown` — not `normal`. §7.3 already rules
     this way for the integrity axis; this mirrors it onto stage.
  3. FALL DWELL, NEVER RISE DWELL. A rise publishes on the first
     reading. A fall is held FALL_DWELL seconds. Dwelling on a rise
     would delay a tornado warning to suppress a cosmetic flap.
  4. INTEGRITY NEVER MOVES STAGE (§11.3 rule 6, §7.3). There is no
     severity on the integrity axis and adding one reintroduces the bug
     §11.5 exists to remove.
  5. AGE IS PERSISTED, NEVER DERIVED FROM last_changed (Playbook
     §15.3). HA resets last_changed to restart time for restored
     entities, which under-reports age — the direction that hides the
     problem.
  6. FLS IS ON THE INTEGRITY AXIS ONLY. This is §11.5 step 3b, done
     here rather than in home_posture.yaml so the old sensor keeps its
     severity-4 stopgap and the two can be compared on a real event.

WHAT THIS DELIBERATELY DOES NOT DO
  - It owns no fetches. It reads the same entities home_posture.yaml
    reads, so any divergence between the two is attributable to the
    resolver rather than to a different feed (Playbook §14.7).
  - DIRECTIVE HAS A LIVE INPUT, and the claim this bullet carried until
    GH #7 — "there is no directive input on this estate today" — was
    true at 0.1.0 and is now the opposite of the record. The CAP row
    reads `cap_responses` off the threat sensor, a boil-water advisory
    resolves its own directive (GH-583), and LAW §11's hard gate is
    satisfied: deterministic EVACUATE/SHELTER/SECURE classification
    tests plus a live-observed input path (GH #38/KAN-240). What
    survives from the original bullet is the SHAPE and it still governs:
    an axis with no readable source reports `unknown` with a reason,
    never `null`, because `null` synthesises an all-clear on an axis
    that has no sensor — the household-banner-card v38 defect.
  - It renders nothing. §11.18's hard gate — no directive surface ships
    until EVACUATE has a verified input — gates the SURFACE, not this.
"""

import json
from pathlib import Path

DOMAIN = "household_state"
PLATFORMS = ["sensor", "binary_sensor"]


def _manifest_version() -> str:
    """The component's version, read from the ONE file that declares it.

    GH #10: entity.py restated it as a literal and the device registry
    published 0.5.1 through four releases, because release.yml cuts a release
    on a manifest.json version CHANGE and nothing in that path touches a
    second copy. A second copy of a version is a copy that goes stale on the
    one action guaranteed not to update it.

    Read at import, which HA performs in an executor thread when it loads the
    component, so this is off the event loop.
    """
    manifest = Path(__file__).parent / "manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8"))["version"]


VERSION = _manifest_version()

# 0.5.0. QUIET's one source — see the module docstring for why it is a
# read-only mirror and not a SOURCES row.
QUIET_SOURCE_ENTITY = None      # bind: quiet.entity_id

# Every source is a state-machine read — the state machine, the entity
# and config-entry registries, the service registry — with no network
# or disk IO at poll time. Cheap enough
# that 3s costs nothing extra over 30s. Lowered from 30 (GH-437) so a
# rise publishes within one poll instead of up to 30s late. Do not raise
# this without measuring — a poll interval longer than the fall dwell
# makes the dwell meaningless.
DEFAULT_SCAN_INTERVAL = 3

# RULE 3. Seconds a fall in stage severity is held before it publishes.
# A rise is never held. Lowered from 120 to 8 (GH-437) to cut
# tablet-visible clear-down lag under the DEFAULT_SCAN_INTERVAL=3 poll.
# Still 2x KAN-206's observed 0-4s flaps, but nowhere near the old two
# orders of magnitude of margin — a flap that lands late in this window,
# or repeats, can now slip through as a real fall. Accepted trade
# (Joel, GH-437): under-10s clear-down over near-total flap immunity.
FALL_DWELL = 8

# Storage. RULE 5.
STORE_KEY = "household_state.ages"
STORE_VERSION = 1

# ---------------------------------------------------------------------
# Dispositions. The whole point of the layer: `ok` with severity 0 and
# "I could not read this" are different facts and must never collapse.
# ---------------------------------------------------------------------
DISP_OK = "ok"                  # entity exists, answered, value parsed
DISP_ABSENT = "absent"          # entity does not exist at all (KAN-182)
DISP_UNREACHABLE = "unreachable"  # entity exists, state unavailable
DISP_UNKNOWN = "unknown"        # entity exists, state unknown
DISP_UNPARSED = "unparsed"      # answered, severity did not parse (KAN-207)

HEALTHY = (DISP_OK,)

# Bands — §7. DO NOT RENUMBER, and the reason has CHANGED. These were
# kept identical to a comparison reference so the two could be diffed
# directly, and that reference is deleted (LAW §3). There is nothing
# left to keep them in sync WITH; what binds them now is that they are a
# published vocabulary — every consumer of the stage sensor reads these
# exact words off it. Stability is owed to the surface, not to a twin.
BAND_CLEAR = "Clear"
BAND_ELEVATED = "Elevated"
BAND_CRITICAL = "Critical"
BAND_UNKNOWN = "Unknown"

STAGE_NORMAL = "normal"
STAGE_ELEVATED = "elevated"
STAGE_CRITICAL = "critical"
STAGE_UNKNOWN = "unknown"

# §11.1 DIRECTIVE axis.
DIRECTIVE_NULL = "none"
DIRECTIVE_SECURE = "secure"
DIRECTIVE_SHELTER = "shelter"
DIRECTIVE_EVACUATE = "evacuate"

# GH-583, RULED BY JOEL. A fourth directive word, and the first that is not a
# movement instruction: secure/shelter/evacuate all say where the household
# should BE, this one says what it must not DRINK. It was initially built as
# STAGE-only awareness on the argument that the vocabulary had three words and
# adding one was a ruling — which was true, and which Joel then made. The
# household axis exists to tell people what to do; a boil-water advisory is
# one of the most literal instructions this estate will ever carry, and
# elevating a banner without saying "boil it" is half a surface.
#
# LOWEST PRECEDENCE, DELIBERATELY. It is checked after secure, so a tornado
# or an evacuation order always wins the instruction row. Water you must boil
# is not a reason to stay out of the closet.
DIRECTIVE_BOIL_WATER = "boil_water"
DIRECTIVE_UNKNOWN = "unknown"

# §7.3 INTEGRITY axis. `unknown` outranks `degraded` — "I cannot tell
# whether I am degraded" is worse than knowing.
INTEGRITY_OK = "ok"
INTEGRITY_DEGRADED = "degraded"
INTEGRITY_UNKNOWN = "unknown"

AXIS_STAGE = "stage"
AXIS_INTEGRITY = "integrity"
AXIS_DIRECTIVE = "directive"

# ---------------------------------------------------------------------
# THE DIRECTIVE AXIS — §11.9's vocabulary map. Added 0.3.0, KAN-208.
#
# THE RAW CAP FIELD IS NOT THE DIRECTIVE. Measured live 2026-08-08
# against api.weather.gov: 249 of 249 active alerts nationally carried
# `response`, and the distribution was Execute 110 / Monitor 60 /
# Avoid 53 / Prepare 18 / Shelter 7 / "None" 1. Only two values promote
# THROUGH THIS MAP. KAN-336 measured 236 more alerts and found Execute/
# Avoid too generic and too common (89% combined) to mean anything
# household-actionable on their own -- promoting either would make a
# directive fire on most alerts instead of the rare, real ones. That
# does NOT mean everything else stays silent: DIRECTIVE_EVENT_MAP below
# gives eight specific non-weather event NAMES their own promotion path,
# independent of what `response` says on that same alert.
# ---------------------------------------------------------------------
DIRECTIVE_RESPONSE_MAP = {
    "Shelter": DIRECTIVE_SHELTER,
    "Evacuate": DIRECTIVE_EVACUATE,
}

# KAN-336, RULED BY JOEL. NWS relays 17 non-weather event types through the
# SAME api.weather.gov feed this integration already polls — Law Enforcement
# Warning, Civil Danger Warning, an active shelter-in-place order, and so on
# are not a separate system, they are event names inside the identical CAP
# payload nws_alerts.yaml already captures. Their real household meaning
# lives in the EVENT NAME, not in CAP's generic `responseType` — which is
# exactly the reasoning the local severity ramp already applies to Tornado
# Warning. `secure` was dead vocabulary (KAN-336) precisely because nothing
# in `DIRECTIVE_RESPONSE_MAP` could ever produce it; these three give it a
# real, cited producer.
#
# Every string below is verified against the LIVE api.weather.gov/alerts/types
# endpoint, not guessed from NWS's descriptive SAME-code names — "Shelter In
# Place Warning" capitalizes "In", and "911 Telephone Outage" carries no
# "Emergency" suffix. Either mismatch would silently never match, which is
# the failure LAW 6 calls "counting is not checking."
#
# Consulted ALONGSIDE DIRECTIVE_RESPONSE_MAP in resolve_directive(), never
# instead of it — this supplies a default finding for the event name, but
# does not suppress a more urgent response-based finding on the same alert.
# An event-name default must never be able to downgrade an alert-specific
# CAP signal; only the precedence loop decides which finding wins.
DIRECTIVE_EVENT_MAP = {
    # secure — something dangerous nearby, no specific instruction yet.
    # Civil Danger Warning explicitly outranks Local Area Emergency in NWS's
    # own hierarchy, which is why LAE is suppressed below rather than mapped.
    "Law Enforcement Warning": DIRECTIVE_SECURE,
    "Civil Danger Warning": DIRECTIVE_SECURE,
    "Civil Emergency Message": DIRECTIVE_SECURE,
    # shelter — the event name says so, or the standard guidance for the
    # hazard is seal-up-and-stay-inside regardless of what `response` says.
    "Shelter In Place Warning": DIRECTIVE_SHELTER,
    "Hazardous Materials Warning": DIRECTIVE_SHELTER,
    "Nuclear Power Plant Warning": DIRECTIVE_SHELTER,
    "Radiological Hazard Warning": DIRECTIVE_SHELTER,
    # evacuate — "immediate evacuation is recommended or ordered" is not a
    # judgment call, unlike Severe Thunderstorm Warning's Shelter tag below.
    "Evacuation Immediate": DIRECTIVE_EVACUATE,
}

# §11.20 open decision 4 — RULED BY JOEL, 2026-08-08.
#
# NWS tags Severe Thunderstorm Warning as `response: Shelter`; all seven
# live Shelter alerts nationally at the time of the ruling were STWs.
# On this estate an STW MUST NOT send anyone to the main closet. It
# fires several times a summer, and a directive that fires routinely is
# the §11.5 failure wearing a different costume — a red that never
# clears teaches everyone to ignore red.
#
# IT STILL REACHES GLASS, AND THAT WAS THE POINT OF THE RULING. STW
# carries severity 5 in the threat sensor's own map, so it drives STAGE
# to critical on its own. What is suppressed is the closet instruction,
# not the alert.
#
# EXTENDED, KAN-336, RULED BY JOEL: four more event types NWS itself
# describes as not household-actionable — Local Area Emergency is
# explicitly defined as NOT by itself posing a significant threat, Child
# Abduction Emergency (AMBER) calls for awareness rather than locking a
# door, 911 Telephone Outage and Administrative Message are informational.
# None of the four appear in DIRECTIVE_EVENT_MAP; this entry is a backstop
# against the rare case one of them also carries a promotable `response`.
#
# SUPPRESSION IS RECORDED, NEVER SILENT. The directive entity reports
# every event it suppressed and the response it suppressed. A silent
# suppression is the same defect class as a silent zero (§16.3) — the
# difference between "no directive applies" and "a directive applied and
# we declined it" has to survive to the attribute.
DIRECTIVE_EVENT_SUPPRESS = (
    "Severe Thunderstorm Warning",
    "Local Area Emergency",
    "Child Abduction Emergency",
    "911 Telephone Outage",
    "Administrative Message",
)

# The sentinel packages/nws_alerts.yaml writes when the CAP field is
# absent from an alert entirely. NWS ALSO emits the literal string
# "None" as a value, and the two are different facts: one is a feed we
# could not read, the other is a feed telling us nothing applies.
CAP_ABSENT = "__absent__"

# ---------------------------------------------------------------------
# PERIMETER OPEN, SUSTAINED — §7's sev-2 driver. Added 0.2.0, KAN-209.
#
# DISCOVER, DO NOT PIN. The set is label_entities('fls_device') filtered
# by domain, exactly as packages/home_posture.yaml has resolved it since
# 2026-08-07. There is no hand-maintained id list here and there must
# never be one: the last hand-maintained copy silently stopped covering
# the front door and the drop zone after the Ring swap, because a
# missing entity read as 'off' and the remaining gates still resolved.
#
# PERIMETER_LABEL is matched against the label_id FIRST and the label
# NAME second. Jinja's label_entities() accepts either, so this file
# must not encode a guess about which one it is.
# ---------------------------------------------------------------------
PERIMETER_LABEL = None          # bind: perimeter.label

# ------------------------------------------------------------------ BINDINGS
#
# WHICH ENTITIES THIS HOUSEHOLD READS IS CONFIGURATION, NOT SOURCE (GH #16).
# A SOURCES row says what a source MEANS — its axis, its kind, how its severity
# is read. Which entity supplies it is an installation detail, and hardcoding
# that made this component readable by exactly one household: every id below
# resolves to `absent` anywhere else, and `absent` is the state this component
# exists to make loud.
#
# The shape of SOURCES is unchanged (LAW §11: one list, one row per source,
# each with an axis). Only the IDENTITY moves — entity ids, the notify service,
# the perimeter label. The attribute triples an `fls` row reads stay in the row
# because they ARE the row's contract with its sensor, not an installation
# choice; parameterising those is a separate question and is not in scope here.
#
# Each entry: the option key, the SOURCES key it binds (or a pseudo-key for the
# two reads that are not SOURCES rows), the spec field it overrides, and the
# selector domain the options flow offers.
BIND_QUIET = "quiet"
BIND_PERIMETER = "perimeter"

BINDABLE = (
    ("local_nws", "entity_id", "sensor", "Local NWS threat sensor"),
    ("ntas", "entity_id", "sensor", "NTAS advisory level sensor"),
    ("space_weather", "entity_id", "sensor", "Space weather sensor"),
    ("alarm", "entity_id", "alarm_control_panel", "Alarm panel"),
    ("boil_water", "entity_id", "binary_sensor", "Boil-water advisory (stage)"),
    ("boil_water_directive", "entity_id", "binary_sensor",
     "Boil-water advisory (directive)"),
    ("nws_cap", "entity_id", "sensor", "CAP directive sensor"),
    ("fire_life_safety", "entity_id", "sensor", "Fire/life-safety health sensor"),
    ("security_device_health", "entity_id", "sensor", "Security health sensor"),
    ("critical_networking_device_health", "entity_id", "sensor",
     "Critical networking health sensor"),
    ("notify_health", "last_sent_entity_id", "sensor",
     "Notify last-successful-send sensor"),
    (BIND_QUIET, "entity_id", "input_boolean", "Sleep-mode helper (QUIET)"),
)

# Not entity selectors: free text, because a service name and a label are not
# entities and HA offers no selector that resolves them the same way.
BINDABLE_TEXT = (
    ("notify_health", "service_domain", "Notify service domain"),
    ("notify_health", "service", "Notify service name"),
    (BIND_PERIMETER, "label", "Perimeter label"),
)


# THE PUBLISHED SLUG IS BINDABLE, AND THIS EXISTS FOR EXACTLY ONE REASON
# (GH #19): a source row's key becomes the tail of its entity's unique_id, so
# RENAMING A KEY MINTS A NEW ENTITY and orphans the old one — HA never reclaims
# an id. An installation that has been running since before a rename would find
# its dashboards reading an entity that now belongs to nothing.
#
# Binding the slug lets the repo carry a neutral key while an existing
# installation keeps the id it already publishes. Almost nobody needs it: it
# defaults to the key, and a fresh install should leave it alone.
SLUG_FIELD = "slug"


def slug_bindings():
    """One optional slug override per source row."""
    return tuple(
        (spec["key"], SLUG_FIELD,
         "Published id suffix for " + spec["name"] + " (advanced; leave blank)")
        for spec in SOURCES
    )


def bind_key(source_key: str, field: str) -> str:
    """The options key for one binding. Flat and stable: a nested structure
    here would be one more thing an options flow has to merge correctly, and
    TOOLS.md already records what that costs when a step gets it wrong."""
    return source_key + "." + field
PERIMETER_DWELL = 300  # seconds. §7: "5-min dwell"

# KAN-311 (GH #55). Same 300s this file already uses for PERIMETER_DWELL,
# and fls_state.jinja's own dwell_seconds — this codebase's standing answer
# to "how long before a restart-window blip counts as a real fault," not a
# new number. Covers config_entries, which reads raw HA
# framework state with no upstream dwell of its own (unlike every other
# INTEGRITY row, which reads an already-dwelled custom sensor), so without
# this a setup_retry entry still resolving 90s into a restart would page
# Joel before HA finished starting (TOOLS.md: "a core restart takes about a
# minute").
CONFIG_ENTRY_DWELL = 300  # seconds.
PERIMETER_SEV = 2      # §7: "Perimeter Open, Sustained" -> sev 2

# A boil-water advisory covering THIS service address. Top of the elevated
# band (1-4), deliberately:
#   - it is a household-wide do-not-drink instruction, so it outranks
#     perimeter-open (2) in the tiebreak and gets NAMED as the driver;
#   - it can never reach the critical band (5-7) on its own, which would
#     equate "boil your water" with an intruder or a triggered alarm.
# STAGE ONLY. It is NOT on the directive axis: DIRECTIVE's vocabulary is
# secure/shelter/evacuate and none of them is "boil the water" -- inventing a
# fourth word there is a ruling, not a config change (LAW 11, GH-583).
BOIL_ADVISORY_SEV = 4

# Domain -> the state that means "open". A domain absent from this map
# is not part of the perimeter set even while carrying the label; that
# is how the 8 Nest Protects, the Ting tracker, the two locks and alarmo
# stay out of it without any of them being named here.
PERIMETER_OPEN_STATES = {"binary_sensor": "on", "cover": "open"}

# ---------------------------------------------------------------------
# THE SOURCE REGISTRY — ONE LIST, ONE PLACE TO EXTEND.
#
# This is the §7.3 idiom applied to the whole layer. Adding a source is
# one row here. Do not scatter entity ids into the coordinator.
#
# kind:
#   severity_attr  read attributes.severity off entity_id
#   alarm          alarm_control_panel state ladder (§7)
#   fls            FLS rollup, integrity axis only (RULE 6)
#
# axis: which axis the row feeds. A row on AXIS_INTEGRITY can never
# move stage, by construction rather than by remembering.
#
# PERIMETER OPEN, SUSTAINED IS NOW HERE (0.2.0, KAN-209). It is the one
# row with no entity_id: it is not an entity, it is a rollup over the
# fls_device label filtered by domain, resolved at every poll. The
# coordinator owns the clock and the persisted open-since; this row only
# says which label to resolve and what a sustained open is worth.
#
# THE NC THREAT ROW WAS REMOVED 2026-08-08 (Joel's ruling), from SOURCES
# and from TIEBREAK together. The rollup it read aggregated four ncdps
# RSS paths that all answer HTTP 404 - measured from the host, against a
# control feed that answered 200 - plus one weather term this integration
# ALREADY reads as its own row. So the row contributed no independent
# signal and counted the weather driver twice into sources_healthy,
# sources_total and confidence. A confidence of full computed over a
# duplicated source is a false completeness reading (Playbook 16.10,
# turned on the resolver instead of the gate).
#
# The rollup sensor itself survives as a retired stub because
# packages/home_posture.yaml is frozen and still references it. Re-add
# this row only when that sensor has a live NC agency input again.
#
# TWO ROWS SHARE ONE FLS SENSOR ON THE INTEGRITY AXIS, and
# that is §7.3's shape rather than a duplicate. Each row names its own
# (integrity_attr, detail_attr, affected_attr) triple, so a third
# integrity signal on the same entity is one more row and no code.
# ---------------------------------------------------------------------
SOURCES = (
    {
        "key": "local_nws",
        "name": "Local NWS",
        "entity_id": None,          # bind: local_nws.entity_id
        "kind": "severity_attr",
        "axis": AXIS_STAGE,
    },
    {
        "key": "ntas",
        "name": "NTAS Advisory",
        "entity_id": None,          # bind: ntas.entity_id
        "kind": "severity_attr",
        "axis": AXIS_STAGE,
    },
    {
        "key": "space_weather",
        "name": "Space Weather",
        "entity_id": None,          # bind: space_weather.entity_id
        "kind": "severity_attr",
        "axis": AXIS_STAGE,
    },
    {
        "key": "alarm",
        "name": "Alarm",
        "entity_id": None,          # bind: alarm.entity_id
        "kind": "alarm",
        "axis": AXIS_STAGE,
    },
    {
        # The only row with entity_id None. See the note above.
        "key": "perimeter_open",
        "name": "Perimeter Open, Sustained",
        "entity_id": None,
        "kind": "perimeter",
        "axis": AXIS_STAGE,
        "label": PERIMETER_LABEL,
        "dwell": PERIMETER_DWELL,
        "open_severity": PERIMETER_SEV,
    },
    {
        # GH-583. The water utility's own boil-water advisory table, matched
        # against this service address including house-number ranges, by
        # packages/uc_water_alerts.yaml. A binary hazard, not a severity
        # feed -- there is no scale to read, it either covers this house or
        # it does not.
        #
        # ITS UNAVAILABLE IS LOAD-BEARING. That entity goes unavailable when
        # the advisory table cannot be read OR when the feed goes stale,
        # rather than answering `off`. This row therefore resolves to
        # DISP_UNREACHABLE and severity None, never 0 -- KAN-139's rule,
        # arriving here for free because the producer refuses to guess.
        "key": "boil_water",
        "name": "Boil Water Advisory",
        "entity_id": None,          # bind: boil_water.entity_id
        "kind": "binary_hazard",
        "axis": AXIS_STAGE,
        "severity_when_on": BOIL_ADVISORY_SEV,
    },
    {
        # THE SAME ENTITY ON A SECOND AXIS, which is the shape §7.3 already
        # uses for the FLS sensor rather than a duplicate: one
        # fact the household needs stated two ways. The STAGE row above
        # elevates the house and names the driver; this row produces the
        # INSTRUCTION, because "boil your water" is a thing to do and the
        # directive axis is where things to do live.
        #
        # It is the only directive source that is not CAP, and it is the
        # lowest-precedence finding in resolve_directive() — a shelter or
        # evacuate order always takes the instruction row from it.
        "key": "boil_water_directive",
        # DISTINCT FROM THE STAGE ROW'S NAME, and that is not cosmetic. Each
        # row publishes a diagnostic entity whose id is a slug of `name`, so
        # two rows sharing a name collide: the second takes `_2` and NEVER
        # reclaims the id (TOOLS), leaving two entities with identical
        # friendly names that no surface can tell apart. That is GH-565's
        # defect exactly, and 0.7.0 shipped it here before this fix.
        "name": "Boil Water Directive",
        "entity_id": None,          # bind: boil_water_directive.entity_id
        "kind": "binary_hazard",
        "axis": AXIS_DIRECTIVE,
        "severity_when_on": BOIL_ADVISORY_SEV,
        "directive_when_on": DIRECTIVE_BOIL_WATER,
    },
    {
        # The directive axis's only source, DELIBERATELY. Reads the SAME
        # entity home_posture.yaml reads — one more attribute off it, not a
        # new fetch — so §16.4's attribution property survives 0.3.0.
        #
        # KAN-336 TRIED TO ADD AN ADJACENT-JURISDICTION CAP SENSOR HERE AS
        # A SECOND ROW AND WAS WRONG TO. That sensor was never on the STAGE
        # axis either — nws_alerts.yaml's own header calls it awareness-only,
        # for the same reason home_posture.yaml never reads it. THE DIRECTIVE
        # AXIS SPEAKS FOR EXACTLY ONE JURISDICTION, the one the household
        # sits in, because DIRECTIVE issues instructions naming that
        # household's own rooms (LAW 11's "Directive text: name the
        # location"). A CAP alert scoped to a neighbouring jurisdiction has
        # no bearing on those rooms, so giving it equal power to say EVACUATE
        # or SHELTER would have been a real, live safety-instruction defect,
        # caught before the restart that would have shipped it. The adjacent
        # sensor stays awareness-only, same as it always was on STAGE.
        "key": "nws_cap",
        "name": "CAP Directive",
        "entity_id": None,          # bind: nws_cap.entity_id
        "kind": "cap",
        "axis": AXIS_DIRECTIVE,
        "pairs_attr": "cap_responses",
    },
    # ---------------------------------------------------------------------
    # THREE CATEGORIES, NOT FIVE (KAN-343, Joel, 2026-08-19; supersedes the
    # 0.2.0/0.15 five-row layout above). The old rows were named after
    # WHICH ATTRIBUTE PAIR a check happened to live on
    # (the FLS sensor's integrity/tamper_integrity/
    # detector_integrity/lock_integrity/sensor_integrity), not after what an
    # operator actually needs to go and act on. Joel's ruling regroups by
    # ACTION: fire, break-in, or "the network/server is down" are three
    # different things to go and look at, and the old split cut across that
    # (a failing smoke buzzer and a dead Ring gate contact both surfaced
    # under two different names neither of which said "life safety" or
    # "perimeter").
    #
    # LABEL-DRIVEN, PER JOEL'S ASK. Every device in Fire Life Safety and
    # Security is still discovered off the `fls_device` label at render time
    # in packages/fls_monitoring.yaml (fire_life_safety_*/security_*
    # attributes) -- adding a device is still a relabel, never a code
    # change here. This file only names which ATTRIBUTE TRIPLE on which
    # ENTITY answers for a category; it does not itself enumerate devices.
    #
    # STILL TWO ROWS SHARING ONE FLS SENSOR, same shape §7.3 has
    # always used: each names its own (integrity_attr, detail_attr,
    # affected_attr) triple, so a fourth category on the same entity is one
    # more row and no new code.
    #
    # DEDUPLICATION, THE OTHER HALF OF THE TICKET. packages/
    # household_integrity.yaml computed this same axis a second time,
    # independently, as the sensor actually wired to integrity-card,
    # room-panel's ring and the operator phone-notification automation --
    # while this registry, the LAW-designated canonical one, had zero
    # consumers. KAN-343 retires that file; every consumer now points at
    # sensor.household_state_integrity (household_alert_integrity before
    # the 0.5.0 rename), and resolve() in resolver.py grew a
    # `sources_detail` breakdown across every AXIS_INTEGRITY row so the card
    # loses nothing in the move.
    {
        # Nest Protect reachability + self-health, Ting reachability AND
        # (GH-435) its own self-reported hazard state (fire/electrical-
        # fault/unsafe-frequency/frozen-pipe), Ring Smoke/CO Listener
        # battery and software fault. See fls_monitoring.yaml's own header
        # on fire_life_safety_integrity for exactly which macro call
        # answers which piece and how each member set is discovered.
        "key": "fire_life_safety",
        "name": "Fire Life Safety Device Health",
        "entity_id": None,          # bind: fire_life_safety.entity_id
        "kind": "fls",
        "axis": AXIS_INTEGRITY,
        "integrity_attr": "fire_life_safety_integrity",
        "detail_attr": "fire_life_safety_detail",
        "affected_attr": "fire_life_safety_affected",
    },
    {
        # Perimeter contact/cover reachability, perimeter tamper, lock
        # battery AND functional status (jammed -- new, KAN-343; nothing
        # checked this before), Ring perimeter battery/software fault, and
        # (wired 2026-08-23, KAN-347) 16 UniFi Protect cameras + the NVR via
        # the `security_camera_device` label -- UniFi network presence
        # (device_tracker, home/away), the same mechanism
        # network_infra_device already uses, chosen over the unifiprotect
        # `camera.*` entities for uniformity across all 17 devices. See
        # fls_monitoring.yaml's security_integrity/security_detail for the
        # tier() call.
        "key": "security_device_health",
        "name": "Security Device Health",
        "entity_id": None,          # bind: security_device_health.entity_id
        "kind": "fls",
        "axis": AXIS_INTEGRITY,
        "integrity_attr": "security_integrity",
        "detail_attr": "security_detail",
        "affected_attr": "security_affected",
    },
    {
        # UniFi network infrastructure (packages/network_client_monitoring
        # .yaml's network_infra_device_status, unchanged) + the HA server
        # (packages/kiosk_wifi.yaml's ha_server_health_reason, unchanged) +
        # Starlink (binary_sensor.starlink_connectivity, wired 2026-08-22,
        # KAN-348) + Spectrum (sensor.home_network_cloudflare_wan_latency,
        # wired 2026-08-23, KAN-349), combined onto one entity because
        # kind:"fls" reads one triple off one entity_id and Joel's ask was
        # one row per category, not one per source. See
        # network_client_monitoring.yaml's "Critical Networking Device
        # Health" sensor for the combine.
        #
        # SPECTRUM (KAN-349) HAD NO DEDICATED ENTITY, NOT NO SIGNAL: the UDM
        # Pro ("the home network") is dual-WAN and the `unifi` integration
        # already probes each WAN port's real uplink with Microsoft/Google/
        # Cloudflare latency pings -- disabled-by-default diagnostics nobody
        # had turned on. WAN1's tracked public IP reverse-resolves to
        # res.spectrum.com (AS11426 Charter), confirming WAN1 is Spectrum
        # and WAN2 is Starlink. Enabled the Cloudflare WAN1 sensor rather
        # than build a ping platform or scrape the modem: it is the
        # external-reachability probe the ticket asked whether one existed,
        # and it already ran, unread. The "Cable Internet" UCI modem device
        # in network_infra_device_status is a different signal -- it proves
        # the modem answers on the LAN, not that Spectrum's uplink passes
        # traffic -- so it stayed in that tier rather than standing in here.
        "key": "critical_networking_device_health",
        "name": "Critical Networking Device Health",
        "entity_id": None,          # bind: critical_networking_device_health.entity_id
        "kind": "fls",
        "axis": AXIS_INTEGRITY,
        "integrity_attr": "integrity",
        "detail_attr": "integrity_detail",
        "affected_attr": "integrity_affected",
    },
    # -----------------------------------------------------------------
    # KAN-311 (GH #55). Two more INTEGRITY rows, both entity_id None —
    # same shape as perimeter_open: not one entity, a set resolved fresh
    # every poll, DISCOVERED off the entity registry rather than a
    # hand-maintained host list, for the same reason the perimeter set is
    # never pinned.
    #
    # THERE WERE THREE. `kiosk_live_page` was REMOVED 2026-09-10 (GH-717,
    # Joel's ruling): a pikiosk showing the wrong page is not a household
    # integrity fault, and while that row held this axis `degraded` over
    # one pi's DevTools port, the dashboard server — the server feeding every screen
    # in the house — was hard down and contributed nothing at all. The
    # inversion, not the row's own correctness, is what retired it; the
    # signal still exists on kiosk_pi's own sensor.<host>_live_page
    # entities and simply no longer reaches this axis. Do not re-add it
    # here: a wall on the wrong page is kiosk_pi's finding to publish.
    # -----------------------------------------------------------------
    {
        # KAN-285's general shape: a config entry can read `loaded` while
        # every entity it owns reads unavailable (the UPS, 2h25m,
        # 2026-08-13 — found only because an unrelated restart moved a
        # count in estate_snapshot), OR sit in `setup_retry` outright
        # (music_assistant and androidtv_remote, both live examples named
        # in the ticket). THE SIGNAL KEYS ON THE SHAPE, NEVER ONE
        # INTEGRATION — every loaded entry's owned-entity unavailable
        # ratio is computed generically off the entity registry, and
        # every entry already in setup_retry is read directly off
        # config_entries. Neither path names a domain.
        "key": "config_entry_health",
        "name": "Config Entry Health",
        "entity_id": None,
        "kind": "config_entries",
        "axis": AXIS_INTEGRITY,
    },
    {
        # KAN-309's buildable third: does the hardcoded notify TARGET
        # packages/household_state_integrity_notify.yaml calls still
        # exist. THE HONEST CEILING, named rather than glossed over: HA
        # gets no APNs delivery receipt, so this can never confirm a push
        # reached the phone (same known gap that file's own header already
        # accepts). What IS knowable for certain: a device re-pair issues
        # a NEW mobile_app device_id and silently orphans the OLD
        # notify.mobile_app_<slug> target — every future call to it fails,
        # and nothing caught that failure mode before this row.
        #
        # A synthetic heartbeat to manufacture a true delivery-freshness
        # signal was considered and rejected: Apple throttles silent
        # (content-available) pushes to ~5/device/day, so a periodic
        # heartbeat frequent enough to be useful self-throttles and reads
        # as a false failure — the "monitor whose blind spot correlates
        # with what it monitors" trap (LAW 10) — and a VISIBLE heartbeat
        # means a recurring banner on Joel's phone forever, a standing
        # behaviour change on his own device this file has no business
        # making unilaterally. last_sent_entity_id is carried as an
        # INFORMATIONAL attribute, never judged against a threshold —
        # staleness during a quiet week is not evidence of anything.
        "key": "notify_health",
        "name": "Operator Notify Path",
        "entity_id": None,
        "kind": "notify_health",
        "axis": AXIS_INTEGRITY,
        "service_domain": None,     # bind: notify_health.service_domain
        "service": None,            # bind: notify_health.service
        "last_sent_entity_id": None,  # bind: notify_health.last_sent_entity_id
    },
)

# §7 tiebreak, label only — it never changes the severity, only which
# driver gets named. FLS is absent from this list because RULE 6 puts it
# on a different axis entirely.
TIEBREAK = (
    "alarm",
    "perimeter_open",
    "local_nws",
    "ntas",
    "space_weather",
)

# §7 alarm ladder. Read as: state -> severity.
ALARM_TRIGGERED_SEV = 7
ALARM_ARMED_OPEN_SEV = 6
