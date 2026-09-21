"""Constants and the source registry for household_state.

WHAT THIS IS. One coordinator that reads every entity the household's
posture depends on, resolves three axes from them — STAGE, DIRECTIVE,
INTEGRITY — and publishes the result as sensors. Nothing backstops it:
the template-sensor arrangement it replaced is deleted, so there is no
second opinion to diff against and no fallback if this reads wrong.

IT HAS LIVE CONSUMERS. Dashboards read sensor.household_state_integrity
directly, and a notification automation pages a phone off it. Stated
here because it is the weak link: an entity id changed in this file
reaches a wall.

WHY IT IS PYTHON AND NOT A TEMPLATE SENSOR. The YAML it replaced
duplicated one severity computation across six lockstep blocks, each
guarded by `fls > 0`. Changing the severity meant editing six branches
and re-keying a card, so it did not get changed. One function replaces
six blocks and is testable without touching live state.

THE FOUR DEFECTS THIS SHAPE EXISTS TO KILL. Each was observed on a
running instance, and each has a rule below that forbids it.

  A driver going unavailable read severity 0, so a dead feed rendered
  green. Here EVERY source carries a disposition and an unreadable
  source can never contribute 0. See RULE 1.

  16 of 19 feed sensors never set up at all. A source that was never
  created is `absent`, a disposition distinct from `ok` at severity 0,
  because the two need different handling and reading alike is how the
  first one hid. See RULE 2.

  Posture flapped Normal<->Elevated 23 times in 6 days, for 0-4s each.
  FALL_DWELL holds a fall and never a rise. See RULE 3.

  A space-weather source read "Storm (G1)" at severity 0 — the display
  state and the ramp disagreed and nothing noticed. Every source records
  BOTH its raw state string and its severity, so a disagreement is an
  attribute rather than a silent loss. See RULE 4.

RULES BAKED IN — DO NOT UNDO THEM
  1. THE COORDINATOR NEVER RAISES UpdateFailed. Raising takes every
     entity unavailable, and attributes on an unavailable entity
     vanish — which is exactly how a broken collector comes to read
     green. It always returns a dict; an individual source returns None.
  2. UNKNOWN IS NOT NORMAL, AND NEVER GREEN. If any stage source is
     unhealthy and no healthy source reports a positive severity, stage
     is `unknown`, not `normal`. The integrity axis has always resolved
     this way; this mirrors it onto stage.
  3. FALL DWELL, NEVER RISE DWELL. A rise publishes on the first
     reading. A fall is held FALL_DWELL seconds. Dwelling on a rise
     would delay a tornado warning in order to suppress a cosmetic flap.
  4. INTEGRITY NEVER MOVES STAGE. There is no severity on the integrity
     axis, and adding one reintroduces the bug this component exists to
     remove: an offline screen is not a household threat.
  5. AGE IS PERSISTED, NEVER DERIVED FROM last_changed. Home Assistant
     resets last_changed to restart time for restored entities, which
     under-reports age — the direction that hides the problem.
  6. FIRE/LIFE-SAFETY DEVICE HEALTH IS ON THE INTEGRITY AXIS ONLY. A
     smoke detector that has stopped reporting is an integrity fault,
     not a fire.
  7. A MACRO STATE MOVES NO AXIS. User-defined modifiers — QUIET and
     everything the options flow adds beside it — carry no severity and
     are counted in no axis. RULE 4's reasoning one layer out: a
     modifier that could move stage would let an installation raise its
     own household to Critical from a form.

WHAT THIS DELIBERATELY DOES NOT DO
  - It owns no fetches. It reads entities other integrations publish,
    so a divergence is attributable to this resolver rather than to a
    different copy of the feed.
  - It renders nothing, and it writes nothing: no service call, no card,
    no state set on another entity. It is a read-only projection.
  - An axis with no readable source reports `unknown` with a reason,
    never `null`. `null` synthesises an all-clear on an axis that has no
    sensor, which is how a banner card once showed calm during an
    outage.

Release history is in `git log`, not here; a changelog in a docstring
goes stale the release after it is written.
"""

import json
from pathlib import Path

DOMAIN = "household_state"
PLATFORMS = ["sensor", "binary_sensor"]


def _manifest_version() -> str:
    """The component's version, read from the ONE file that declares it.

    #10: entity.py restated it as a literal and the device registry
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
# that 3s costs nothing extra over 30s. Lowered from 30 so a
# rise publishes within one poll instead of up to 30s late. Do not raise
# this without measuring — a poll interval longer than the fall dwell
# makes the dwell meaningless.
DEFAULT_SCAN_INTERVAL = 3

# RULE 3. Seconds a fall in stage severity is held before it publishes.
# A rise is never held. Lowered from 120 to 8 to cut
# tablet-visible clear-down lag under the DEFAULT_SCAN_INTERVAL=3 poll.
# Still 2x the observed 0-4s flaps, but nowhere near the old two
# orders of magnitude of margin — a flap that lands late in this window,
# or repeats, can now slip through as a real fall. Accepted trade
#: under-10s clear-down over near-total flap immunity.
FALL_DWELL = 8

# Storage. RULE 5.
STORE_KEY = "household_state.ages"
STORE_VERSION = 1

# ---------------------------------------------------------------------
# Dispositions. The whole point of the layer: `ok` with severity 0 and
# "I could not read this" are different facts and must never collapse.
# ---------------------------------------------------------------------
DISP_OK = "ok"                  # entity exists, answered, value parsed
DISP_ABSENT = "absent"          # entity does not exist at all
DISP_UNREACHABLE = "unreachable"  # entity exists, state unavailable
DISP_UNKNOWN = "unknown"        # entity exists, state unknown
DISP_UNPARSED = "unparsed"      # answered, severity did not parse

HEALTHY = (DISP_OK,)

# Bands. DO NOT RENUMBER, and the reason has CHANGED. These were
# kept identical to a comparison reference so the two could be diffed
# directly, and that reference is deleted. There is nothing
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

# THE DIRECTIVE AXIS.
DIRECTIVE_NULL = "none"
DIRECTIVE_SECURE = "secure"
DIRECTIVE_SHELTER = "shelter"
DIRECTIVE_EVACUATE = "evacuate"

# A FOURTH DIRECTIVE WORD, and the first that is not a
# movement instruction: secure/shelter/evacuate all say where the household
# should BE, this one says what it must not DRINK. It was initially built as
# STAGE-only awareness on the argument that the vocabulary had three words and
# adding one was a ruling — which was true, and which was then made. The
# household axis exists to tell people what to do; a boil-water advisory is
# one of the most literal instructions this installation will ever carry, and
# elevating a banner without saying "boil it" is half a surface.
#
# LOWEST PRECEDENCE, DELIBERATELY. It is checked after secure, so a tornado
# or an evacuation order always wins the instruction row. Water you must boil
# is not a reason to stay out of the closet.
DIRECTIVE_BOIL_WATER = "boil_water"
DIRECTIVE_UNKNOWN = "unknown"

# THE INTEGRITY AXIS. `unknown` outranks `degraded` — "I cannot tell
# whether I am degraded" is worse than knowing.
INTEGRITY_OK = "ok"
INTEGRITY_DEGRADED = "degraded"
INTEGRITY_UNKNOWN = "unknown"

AXIS_STAGE = "stage"
AXIS_INTEGRITY = "integrity"
AXIS_DIRECTIVE = "directive"

# ---------------------------------------------------------------------
# THE DIRECTIVE AXIS — the vocabulary map.
#
# THE RAW CAP FIELD IS NOT THE DIRECTIVE. Measured live 2026-08-08
# against api.weather.gov: 249 of 249 active alerts nationally carried
# `response`, and the distribution was Execute 110 / Monitor 60 /
# Avoid 53 / Prepare 18 / Shelter 7 / "None" 1. Only two values promote
# THROUGH THIS MAP. A later audit measured 236 more alerts and found Execute/
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

# NWS relays 17 non-weather event types through the
# SAME api.weather.gov feed this integration already polls — Law Enforcement
# Warning, Civil Danger Warning, an active shelter-in-place order, and so on
# are not a separate system, they are event names inside the identical CAP
# payload the alert feed already captures. Their real household meaning
# lives in the EVENT NAME, not in CAP's generic `responseType` — which is
# exactly the reasoning the local severity ramp already applies to Tornado
# Warning. `secure` was dead vocabulary precisely because nothing
# in `DIRECTIVE_RESPONSE_MAP` could ever produce it; these three give it a
# real, cited producer.
#
# Every string below is verified against the LIVE api.weather.gov/alerts/types
# endpoint, not guessed from NWS's descriptive SAME-code names — "Shelter In
# Place Warning" capitalizes "In", and "911 Telephone Outage" carries no
# "Emergency" suffix. Either mismatch would silently never match, which is
# the failure the rule that counting is not checking calls "counting is not checking."
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

# A RULING, and the reason it is not a preference:
#
# NWS tags Severe Thunderstorm Warning as `response: Shelter`; all seven
# live Shelter alerts nationally at the time of the ruling were STWs.
# On this installation an STW MUST NOT send anyone to the main closet. It
# fires several times a summer, and a directive that fires routinely is
# the severity inversion wearing a different costume — a red that never
# clears teaches everyone to ignore red.
#
# IT STILL REACHES GLASS, AND THAT WAS THE POINT OF THE RULING. STW
# carries severity 5 in the threat sensor's own map, so it drives STAGE
# to critical on its own. What is suppressed is the closet instruction,
# not the alert.
#
# EXTENDED, a later audit of the alert vocabulary, RULED BY JOEL: four more event types NWS itself
# describes as not household-actionable — Local Area Emergency is
# explicitly defined as NOT by itself posing a significant threat, Child
# Abduction Emergency (AMBER) calls for awareness rather than locking a
# door, 911 Telephone Outage and Administrative Message are informational.
# None of the four appear in DIRECTIVE_EVENT_MAP; this entry is a backstop
# against the rare case one of them also carries a promotable `response`.
#
# SUPPRESSION IS RECORDED, NEVER SILENT. The directive entity reports
# every event it suppressed and the response it suppressed. A silent
# suppression is the same defect class as a silent zero — the
# difference between "no directive applies" and "a directive applied and
# we declined it" has to survive to the attribute.
DIRECTIVE_EVENT_SUPPRESS = (
    "Severe Thunderstorm Warning",
    "Local Area Emergency",
    "Child Abduction Emergency",
    "911 Telephone Outage",
    "Administrative Message",
)

# The sentinel the alert feed writes when the CAP field is
# absent from an alert entirely. NWS ALSO emits the literal string
# "None" as a value, and the two are different facts: one is a feed we
# could not read, the other is a feed telling us nothing applies.
CAP_ABSENT = "__absent__"

# ---------------------------------------------------------------------
# PERIMETER OPEN, SUSTAINED — the severity-2 stage driver.
#
# DISCOVER, DO NOT PIN. The set is label_entities('fls_device') filtered
# by domain, exactly as the YAML this replaced resolved it
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

# THE LABEL THAT PUTS A DEVICE OR ENTITY IN SCOPE FOR INTEGRITY (#28).
# OPT-IN, RULED BY JOEL, REVERSING #26'S OPT-OUT: the config-entry row
# watches ONLY what carries this label, or sits on a device that does.
# Anything unlabelled is not this row's business. The earlier premise --
# every config entry, generically, with an opt-out for devices whose off
# state reads `unavailable` -- meant a powered-off TV faulted until somebody
# labelled it out, and the set of things to label out grows forever; the
# set of things the household DEPENDS ON is the shorter list and the one
# the contract names. Discovered the way the perimeter and the security
# cameras are: a relabel, never a code change. Matched against the label
# id first and the name second, like PERIMETER_LABEL. Bindable.
#
# A label that does not resolve, or resolves to nothing, is `absent`, not
# `ok`: a monitor with no scope is a blind spot that reads green.
INTEGRITY_SCOPE_LABEL = "integrity_watched"   # bind: config_entry_health.label

# ------------------------------------------------------------------ BINDINGS
#
# WHICH ENTITIES THIS HOUSEHOLD READS IS CONFIGURATION, NOT SOURCE (#16).
# A SOURCES row says what a source MEANS — its axis, its kind, how its severity
# is read. Which entity supplies it is an installation detail, and hardcoding
# that made this component readable by exactly one household: every id below
# resolves to `absent` anywhere else, and `absent` is the state this component
# exists to make loud.
#
# The shape of SOURCES is unchanged (one list, one row per source,
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
# #30. The rendering matrix's two installation facts: where an operator's
# own cell wording lives, and which jurisdiction the weather wording names.
# Neither is a source row — the matrix reads the axes, not an entity.
BIND_BANNER = "banner"

BINDABLE = (
    ("local_nws", "entity_id", "sensor", "Local NWS threat sensor"),
    ("ntas", "entity_id", "sensor", "NTAS advisory level sensor"),
    ("space_weather", "entity_id", "sensor", "Space weather sensor"),
    ("alarm", "entity_id", "alarm_control_panel", "Alarm panel"),
    ("boil_water", "entity_id", "binary_sensor", "Boil-water advisory (stage)"),
    ("boil_water_directive", "entity_id", "binary_sensor",
     "Boil-water advisory (directive)"),
    ("outside_person", "entity_id", "binary_sensor",
     "Person outside overnight (stage)"),
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
    ("config_entry_health", "label", "Integrity scope label (devices watched)"),
    # #30. With a prefix bound, a cell's wording is read from
    # input_text.<prefix>_<cell>_imperative / _action and overrides the code
    # default when set; unbound, the defaults stand. A helper whose state is
    # unknown or empty is "not set", never a blank line.
    (BIND_BANNER, "text_prefix",
     "Directive text helper prefix (input_text.<prefix>_<cell>_imperative)"),
    # The place the weather wording names for an event the matrix has no
    # line for ("<event> is in effect for <jurisdiction>."). Unbound, the
    # line names no place rather than a wrong one.
    (BIND_BANNER, "jurisdiction", "Jurisdiction the weather feed covers"),
)


# THE PUBLISHED SLUG IS BINDABLE, AND THIS EXISTS FOR EXACTLY ONE REASON
# (#19): a source row's key becomes the tail of its entity's unique_id, so
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
    Getting this wrong costs a restart, which is why it is stated here."""
    return source_key + "." + field


# --------------------------------------------------------- CUSTOM MACRO STATES
#
# WHAT A MACRO STATE IS. A named household modifier — GUEST, VACATION, AWAY,
# COOKING — resolved from an entity this installation already has, published as
# `binary_sensor.household_state_<slug>`, and defined entirely in the options
# flow. QUIET is the built-in instance of exactly this shape (0.5.0, a
# read-only mirror of a sleep-mode helper); this generalises it so a second
# modifier is a form, not a release.
#
# IT IS STILL READ-ONLY, AND THAT IS THE WHOLE POINT. Defining a macro state
# here does NOT create a helper, a toggle or anything writable: it names a
# source and a state string, and publishes what that source says. Nothing here
# can be turned on from a dashboard, because nothing here owns the fact — the
# bound entity does. An installation that wants a flippable switch still wants
# an `input_boolean`; what it no longer wants is the template sensor stack ON
# TOP of that helper, which is what this replaces. See
# docs/migrating-from-input-boolean-helpers.md.
#
# RULE 7. A MACRO STATE MOVES NO AXIS. It carries no severity, contributes to
# no stage/directive/integrity resolution, and is absent from `sources_total`
# and `confidence`. This is RULE 4's reasoning applied one layer out: the moment
# a user-defined modifier can move stage, an installation can raise its own
# household to Critical from a form, and the ramp stops meaning what const.py
# says it means. A macro that ought to move an axis is a SOURCES row and a
# ruling, not a config change.
#
# UNREADABLE IS NOT `off`. A macro whose source is missing, unavailable or
# unknown publishes `None`, never False, and carries its disposition — the same
# refusal as every other read in this component. A modifier that quietly reads
# `off` because its helper was deleted is the dead-feed-reads-green defect
# wearing a different name.
#
# `masks` (#30). A macro may declare that WHILE IT IS ON THE BANNER SAYS
# NOTHING — no cell, no instruction, no status line — except an evacuation,
# which is never masked. PARTY is the instance this exists for: a household
# that has people over does not want the wall announcing its own security
# posture to the room, and Joel's ruling of 2026-09-19 is that a party wall
# says nothing from the household axes but an evacuation.
#
# THIS IS NOT RULE 7 BEING BENT, and the distinction is the whole reason it
# can live here. A masking macro moves NO axis: stage, directive and
# integrity resolve exactly as they would with the macro off, keep their
# severities, their drivers and their `suppressed` record, and every
# automation reading them sees no difference. What the flag changes is the
# RENDERING of the banner cell — the same class of fact as QUIET's tint —
# and it changes it HERE rather than in each surface, because a mask
# resolved per surface is a mask that one surface forgets (it was
# ha-dashboard-kit's `party.ts`, on the walls only; the companion app and a
# voice surface would each have needed their own copy).
OPT_MACROS = "macros"

# Option keys that are NOT source bindings. __init__.py splits entry.options on
# this set; a new non-binding option that forgets to land here is silently
# handed to the coordinator as a binding for a source named after itself.
NON_BINDING_OPTIONS = frozenset({"scan_interval", OPT_MACROS})

# The state string a macro reads as `on` when the form leaves it blank.
MACRO_DEFAULT_ON_STATE = "on"

# A slug longer than this is not refused for a technical reason — it is refused
# because it becomes an entity id somebody has to type into a template.
MACRO_SLUG_MAX = 40

# THE SLUG IS FROZEN AT CREATION AND THE EDIT FORM WILL NOT OFFER IT. Same
# reasoning as #19 one level down: the slug is the tail of the macro's
# unique_id AND, at first registration, of its published entity id, and Home
# Assistant never reclaims an id. If the slug tracked the name, renaming
# "Guest" to "Guests" would mint a second entity and orphan the one every
# dashboard reads. So a rename changes the friendly name and nothing else.
MACRO_RENAMEABLE_FIELDS = ("name", "entity_id", "on_state", "icon", "masks")

# Slugs this integration already publishes on its own device, plus the three
# axis names.
#
# `quiet` and `feed_health` are HARD collisions: they are binary_sensors on the
# same device, so a macro slugged either one lands on `_2` and every surface
# reading the original keeps reading the original. The three axis names are
# reserved for a softer reason — `binary_sensor.household_state_stage` sitting
# beside `sensor.household_state_stage`, answering a different question with a
# different vocabulary, is a trap for whoever reads the dashboard next.
RESERVED_MACRO_SLUGS = frozenset(
    {"quiet", "feed_health", "stage", "directive", "integrity"}
)


def macro_slugify(value) -> str:
    """A name -> the slug its entity id is built from.

    Lowercase, every run of non-alphanumerics collapsed to one underscore,
    edges trimmed. Deliberately NOT homeassistant.util.slugify: this value is
    persisted in the config entry and compared against entity ids that already
    exist, so it must not change when core's slugify does.
    """
    out = []
    for ch in str(value or "").lower():
        out.append(ch if ch.isalnum() and ch.isascii() else "_")
    slug = "_".join(part for part in "".join(out).split("_") if part)
    return slug[:MACRO_SLUG_MAX].rstrip("_")


def normalize_macro(row) -> dict | None:
    """One stored row -> the shape every reader uses, or None if unusable.

    Returns None rather than a repaired row. The options flow is the only
    thing that writes here and it validates before it does, so an unusable row
    means the entry was hand-edited in `.storage`; guessing a slug for it would
    publish an entity under a name nobody chose.
    """
    if not isinstance(row, dict):
        return None
    slug = macro_slugify(row.get("slug"))
    if not slug or slug in RESERVED_MACRO_SLUGS:
        return None
    entity_id = row.get("entity_id")
    if not isinstance(entity_id, str) or not entity_id.strip():
        return None
    name = row.get("name")
    name = name.strip() if isinstance(name, str) and name.strip() else slug
    on_state = row.get("on_state")
    on_state = (
        on_state.strip()
        if isinstance(on_state, str) and on_state.strip()
        else MACRO_DEFAULT_ON_STATE
    )
    icon = row.get("icon")
    icon = icon.strip() if isinstance(icon, str) and icon.strip() else None
    # `is True`, not truthiness: a stored row that says "no", 0 or "" must
    # not silence a wall because a string is non-empty. Absent is False —
    # every macro written before #30 masks nothing, which is what those
    # installations already have.
    masks = row.get("masks") is True
    return {
        "slug": slug,
        "name": name,
        "entity_id": entity_id.strip(),
        "on_state": on_state,
        "icon": icon,
        "masks": masks,
    }


def normalize_macros(value) -> tuple:
    """Every stored macro, in order, deduplicated by slug.

    FIRST WINS on a duplicate slug, and the duplicate is dropped rather than
    merged: two rows claiming one entity id would publish one entity whose
    source depends on iteration order, which is the kind of fact that is only
    discovered during an incident.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    out = []
    seen = set()
    for row in value:
        macro = normalize_macro(row)
        if macro is None or macro["slug"] in seen:
            continue
        seen.add(macro["slug"])
        out.append(macro)
    return tuple(out)


def macros_from_options(options) -> tuple:
    """The macro states an entry declares."""
    return normalize_macros((options or {}).get(OPT_MACROS))


# The segment that tells a macro's registry row apart from every other entity
# this integration publishes. `_quiet`, `_feed_health`, `_stage` and `_src_<x>`
# carry no such segment, so a cleanup keyed on it cannot reach them.
MACRO_UNIQUE_ID_PREFIX = "_macro_"


def macro_unique_id(entry_id: str, slug: str) -> str:
    """The unique_id one macro publishes under.

    Defined HERE and not inline in binary_sensor.py because __init__.py reads
    the same format to find the registry rows of macros that have been deleted.
    Two copies of an id format is one copy that goes stale, and the failure it
    produces — orphaned entities that are never cleaned up — is silent.
    """
    return entry_id + MACRO_UNIQUE_ID_PREFIX + slug


PERIMETER_DWELL = 300  # seconds — the specified 5-minute dwell.

# Same 300s this file already uses for PERIMETER_DWELL, and the same
# dwell the YAML it replaced used — this codebase's standing answer
# to "how long before a restart-window blip counts as a real fault," not a
# new number. Covers config_entries, which reads raw HA
# framework state with no upstream dwell of its own (unlike every other
# INTEGRITY row, which reads an already-dwelled custom sensor), so without
# this a setup_retry entry still resolving 90s into a restart would page
# an operator before HA finished starting (a core restart takes about a
# minute").
CONFIG_ENTRY_DWELL = 300  # seconds.
PERIMETER_SEV = 2      # the stage bands: "Perimeter Open, Sustained" -> sev 2

# A person seen by an outside camera overnight (#13). THE SAME LEVEL AS A
# DOOR LEFT OPEN, by ruling: it is a thing to go and look at, not an
# intruder — the alarm row owns the critical band for that. Which cameras
# count as "outside", which hours count as "overnight" and how long the
# finding holds after the last sighting are the installation's, on the
# bound binary_sensor; this row reads its `on` and names what it saw.
# RULE 3 keeps every dwell out of this file: a 5-minute hold on one row
# would be a rise dwell on the fall side of a different sensor, which is
# the sensor's own `delay_off` to declare.
OUTSIDE_PERSON_SEV = PERIMETER_SEV

# A boil-water advisory covering THIS service address. Top of the elevated
# band (1-4), deliberately:
#   - it is a household-wide do-not-drink instruction, so it outranks
#     perimeter-open (2) in the tiebreak and gets NAMED as the driver;
#   - it can never reach the critical band (5-7) on its own, which would
#     equate "boil your water" with an intruder or a triggered alarm.
# STAGE ONLY. It is NOT on the directive axis: DIRECTIVE's vocabulary is
# secure/shelter/evacuate and none of them is "boil the water" -- inventing a
# fourth word there is a ruling, not a config change.
BOIL_ADVISORY_SEV = 4

# Domain -> the state that means "open". A domain absent from this map
# is not part of the perimeter set even while carrying the label; that
# is how the 8 Nest Protects, the Ting tracker, the two locks and alarmo
# stay out of it without any of them being named here.
PERIMETER_OPEN_STATES = {"binary_sensor": "on", "cover": "open"}

# ---------------------------------------------------------------------
# THE SOURCE REGISTRY — ONE LIST, ONE PLACE TO EXTEND.
#
# This is the integrity axis idiom applied to the whole layer. Adding a source is
# one row here. Do not scatter entity ids into the coordinator.
#
# kind:
#   severity_attr  read attributes.severity off entity_id
#   alarm          alarm_control_panel state ladder
#   fls            FLS rollup, integrity axis only (RULE 6)
#
# axis: which axis the row feeds. A row on AXIS_INTEGRITY can never
# move stage, by construction rather than by remembering.
#
# PERIMETER OPEN, SUSTAINED IS NOW HERE. It is the one
# row with no entity_id: it is not an entity, it is a rollup over the
# fls_device label filtered by domain, resolved at every poll. The
# coordinator owns the clock and the persisted open-since; this row only
# says which label to resolve and what a sustained open is worth.
#
# THE ADJACENT-STATE THREAT ROW WAS REMOVED, from SOURCES
# and from TIEBREAK together. The rollup it read aggregated four ncdps
# RSS paths that all answer HTTP 404 - measured from the host, against a
# control feed that answered 200 - plus one weather term this integration
# ALREADY reads as its own row. So the row contributed no independent
# signal and counted the weather driver twice into sources_healthy,
# sources_total and confidence. A confidence of full computed over a
# duplicated source is a false completeness reading: the gate says it saw
# everything when what it actually saw was one thing twice.
#
# The rollup sensor itself survives as a retired stub because
# the YAML this replaced is frozen and still references it. Re-add
# this row only when that sensor has a live NC agency input again.
#
# TWO ROWS SHARE ONE FLS SENSOR ON THE INTEGRITY AXIS, and
# that is the integrity axis's own shape rather than a duplicate. Each row names its
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
        # The water utility's own boil-water advisory table, matched
        # against this service address including house-number ranges, by
        # the water-utility feed. A binary hazard, not a severity
        # feed -- there is no scale to read, it either covers this house or
        # it does not.
        #
        # ITS UNAVAILABLE IS LOAD-BEARING. That entity goes unavailable when
        # the advisory table cannot be read OR when the feed goes stale,
        # rather than answering `off`. This row therefore resolves to
        # DISP_UNREACHABLE and severity None, never 0 -- RULE 1's requirement,
        # arriving here for free because the producer refuses to guess.
        "key": "boil_water",
        "name": "Boil Water Advisory",
        "entity_id": None,          # bind: boil_water.entity_id
        "kind": "binary_hazard",
        "axis": AXIS_STAGE,
        "severity_when_on": BOIL_ADVISORY_SEV,
    },
    {
        # THE SAME ENTITY ON A SECOND AXIS, which is the shape the integrity axis already
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
        # reclaims the id, leaving two entities with identical
        # friendly names that no surface can tell apart. That is the
        # indistinguishable-entity defect exactly, and it shipped here once.
        "name": "Boil Water Directive",
        "entity_id": None,          # bind: boil_water_directive.entity_id
        "kind": "binary_hazard",
        "axis": AXIS_DIRECTIVE,
        "severity_when_on": BOIL_ADVISORY_SEV,
        "directive_when_on": DIRECTIVE_BOIL_WATER,
    },
    {
        # A person seen by an outside camera overnight (#13). A binary
        # hazard like boil_water, with one difference that is the whole
        # point of it: the bound sensor carries `cameras`, the entity ids
        # of the person-detection sensors that saw someone, and this row
        # forwards them RAW into its detail — "seen: binary_sensor.x, ..."
        # — the way the alarm row forwards Alarmo's open_sensors. A
        # directive names WHICH, never THAT: "someone is outside" over a
        # reading that knows it was the driveway is the unnamed-opening
        # defect again. The surface humanises the ids at the render
        # boundary; nothing here prettifies them.
        "key": "outside_person",
        "name": "Person Outside Overnight",
        "entity_id": None,          # bind: outside_person.entity_id
        "kind": "binary_hazard",
        "axis": AXIS_STAGE,
        "severity_when_on": OUTSIDE_PERSON_SEV,
        "seen_attr": "cameras",
    },
    {
        # The directive axis's only source, DELIBERATELY. Reads the SAME
        # entity the stage axis reads — one more attribute off it, not a
        # new fetch — so a divergence stays attributable to this resolver.
        #
        # A LATER AUDIT TRIED TO ADD AN ADJACENT-JURISDICTION CAP SENSOR HERE AS
        # A SECOND ROW AND WAS WRONG TO. That sensor was never on the STAGE
        # axis either — the alert feed's own header calls it awareness-only,
        # for the same reason the stage axis never reads it. THE DIRECTIVE
        # AXIS SPEAKS FOR EXACTLY ONE JURISDICTION, the one the household
        # sits in, because DIRECTIVE issues instructions naming that
        # household's own rooms — directive text names the location. A CAP
        # alert scoped to a neighbouring jurisdiction has
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
    # THREE CATEGORIES, NOT FIVE (supersedes the
    # 0.2.0/0.15 five-row layout above). The old rows were named after
    # WHICH ATTRIBUTE PAIR a check happened to live on
    # (the FLS sensor's integrity/tamper_integrity/
    # detector_integrity/lock_integrity/sensor_integrity), not after what an
    # operator actually needs to go and act on. The regrouping is by
    # ACTION: fire, break-in, or "the network/server is down" are three
    # different things to go and look at, and the old split cut across that
    # (a failing smoke buzzer and a dead Ring gate contact both surfaced
    # under two different names neither of which said "life safety" or
    # "perimeter").
    #
    # LABEL-DRIVEN, PER JOEL'S ASK. Every device in Fire Life Safety and
    # Security is still discovered off the `fls_device` label at render time
    # in the fire/life-safety package (fire_life_safety_*/security_*
    # attributes) -- adding a device is still a relabel, never a code
    # change here. This file only names which ATTRIBUTE TRIPLE on which
    # ENTITY answers for a category; it does not itself enumerate devices.
    #
    # STILL TWO ROWS SHARING ONE FLS SENSOR, same shape the integrity axis has
    # always used: each names its own (integrity_attr, detail_attr,
    # affected_attr) triple, so a fourth category on the same entity is one
    # more row and no new code.
    #
    # DEDUPLICATION, THE OTHER HALF OF THE TICKET. A YAML template
    # computed this same axis a second time, independently, and it was
    # that copy — not this one — that the dashboards and the operator
    # phone-notification automation were actually wired to --
    # while this registry, the one specified as canonical, had zero
    # consumers. That file is retired; every consumer now points at
    # sensor.household_state_integrity (household_alert_integrity before
    # the 0.5.0 rename), and resolve() in resolver.py grew a
    # `sources_detail` breakdown across every AXIS_INTEGRITY row so the card
    # loses nothing in the move.
    {
        # Nest Protect reachability + self-health, Ting reachability AND
        # its own self-reported hazard state (fire/electrical-
        # fault/unsafe-frequency/frozen-pipe), Ring Smoke/CO Listener
        # battery and software fault. See the fire/life-safety package
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
        # battery AND functional status (jammed -- nothing checked this
        # before), perimeter battery/software fault, and the cameras and
        # recorder via
        # the `security_camera_device` label -- UniFi network presence
        # (device_tracker, home/away), the same mechanism
        # network_infra_device already uses, chosen over the unifiprotect
        # `camera.*` entities for uniformity across all 17 devices. See
        # the package's security_integrity/security_detail for the
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
        # Network infrastructure, the HA server itself, and each WAN
        # uplink, combined onto ONE entity upstream of this registry
        # because kind:"fls" reads one triple off one entity_id and the
        # requirement was one row per category, not one per source. The
        # combine happens in the monitoring package that owns those
        # devices; this row reads only its verdict.
        #
        # A NOTE ON WHAT COUNTS AS AN UPLINK SIGNAL, because it is the
        # mistake worth not repeating. A modem that answers on the LAN is
        # NOT evidence that its uplink passes traffic, and reading it as
        # one is the dead-feed problem in a different costume. Prefer a
        # probe that leaves the building: a dual-WAN gateway integration
        # may already ship per-port external latency sensors, disabled by
        # default, which measure exactly that and cost nothing to enable.
        # Look for the probe that already runs unread before building a
        # new one.
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
    # Two more INTEGRITY rows, both entity_id None —
    # same shape as perimeter_open: not one entity, a set resolved fresh
    # every poll, DISCOVERED off the entity registry rather than a
    # hand-maintained host list, for the same reason the perimeter set is
    # never pinned.
    #
    # THERE WERE THREE. A `kiosk_live_page` row was REMOVED, and the reason
    # is the inversion rather than any fault in the row itself: a wall panel
    # showing the wrong page is not a household integrity fault. That row
    # held this axis `degraded` over one panel's browser port while the
    # dashboard server feeding every screen in the house could be hard down
    # and reach this registry not at all. The signal still exists on the
    # panel fleet's own per-host entities; it simply no longer reaches this
    # axis. Do not re-add it here — a wall on the wrong page is the fleet's
    # finding to publish, not this component's.
    # -----------------------------------------------------------------
    {
        # A config entry can read `loaded` while
        # every entity it owns reads unavailable (one live case ran 2h25m,
        # 2026-08-13 — found only because an unrelated restart moved a
        # count elsewhere), OR sit in `setup_retry` outright, which HA
        # reports directly. THE SIGNAL KEYS ON THE SHAPE, NEVER ONE
        # INTEGRATION — a watched entry's in-scope unavailable ratio is
        # computed generically off the entity registry, and a watched
        # entry already in setup_retry is read directly off
        # config_entries. Neither path names a domain.
        #
        # THE SCOPE IS THE OPERATOR'S, NOT THIS FILE'S (#28, opt-in,
        # reversing #26): an entry is watched when it owns an entity
        # carrying INTEGRITY_SCOPE_LABEL or on a device that does, and the
        # ratio runs over those entities alone. No label, no scope, and no
        # scope is `absent` -- never a hollow `ok`.
        "key": "config_entry_health",
        "name": "Config Entry Health",
        "entity_id": None,
        "kind": "config_entries",
        "axis": AXIS_INTEGRITY,
    },
    {
        # A buildable third check: does the hardcoded notify TARGET
        # the integrity-notification automation calls still
        # exist. THE HONEST CEILING, named rather than glossed over: HA
        # gets no APNs delivery receipt, so this can never confirm a push
        # reached the phone. What IS knowable for certain: a device re-pair issues
        # a NEW mobile_app device_id and silently orphans the OLD
        # notify.mobile_app_<slug> target — every future call to it fails,
        # and nothing caught that failure mode before this row.
        #
        # A synthetic heartbeat to manufacture a true delivery-freshness
        # signal was considered and rejected: Apple throttles silent
        # (content-available) pushes to ~5/device/day, so a periodic
        # heartbeat frequent enough to be useful self-throttles and reads
        # as a false failure — the "monitor whose blind spot correlates
        # with what it monitors" trap — and a VISIBLE heartbeat
        # means a recurring banner on an operator's phone forever, a standing
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

# Tiebreak, label only — it never changes the severity, only which
# driver gets named. FLS is absent from this list because RULE 6 puts it
# on a different axis entirely.
#
# EVERY AXIS_STAGE ROW MUST BE HERE, AND THE SUITE ASSERTS IT (#12).
# resolve() walks THIS tuple, not SOURCES, so a stage row whose key is
# missing from it is read every poll, publishes its own severity on its
# own source sensor, and never moves STAGE at all. boil_water shipped that
# way: severity 4 on its sensor, STAGE normal, for as long as it was live.
TIEBREAK = (
    "alarm",
    "boil_water",
    # Ties perimeter_open at 2; named first because a person seen is the
    # more specific finding of the two, and the one to go and look at.
    "outside_person",
    "perimeter_open",
    "local_nws",
    "ntas",
    "space_weather",
)

# The alarm ladder. Read as: state -> severity.
ALARM_TRIGGERED_SEV = 7
ALARM_ARMED_OPEN_SEV = 6
