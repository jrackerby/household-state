<img src="https://raw.githubusercontent.com/jrackerby/household-state/master/brand/logo%402x.png" alt="Household State" width="240" align="right">

# household_state

> **Front-end consumers below are HISTORICAL.** Every `www/*.js` card and
> every `dashboards/*.yaml` board this document names was deleted — the card
> fleet and its 54 `/local/` resource registrations by GH-564, the 41 dead
> board files and the card-era tooling by GH-575. Verified live: the Lovelace
> resource registry holds no `/local/` entry and `lovelace/dashboards/list`
> returns `[]`.
>
> What that does and does not invalidate: **the entity, platform and
> resolution content is unaffected** and is still the reference for this
> integration. Only the consumer claims are stale, and they are stale in one
> direction — a card named here as a consumer no longer exists, so "who reads
> this entity" reads as *nobody in this repo* until a dashboard app claims it.
> Those apps live in their own repos (CLAUDE.md §5) and are not greppable from
> here, so absence of a consumer in this document is not evidence there is
> none. A "no consumer found" conclusion reached by grepping `www/` or
> `dashboards/` still holds; the directories it names simply no longer exist.

Siblings: `household_state_abstract.md` (what this is for, no jargon) ·
`household_state_process_flow.md` (what happens, in what order) ·
`household_state_data_flow.md` (which value came from where) ·
`household_state_architecture.md` (the static modules and how they fit
together) · `household_alert_patent_disclosure.md` (patent-disclosure
draft, pinned to the pre-rename name/version — see its own footer).

`custom_components/household_state` — version 0.5.0. Resolves three
independent household-threat axes from a fixed source registry, plus a
read-only QUIET modifier sourced from sleep mode. Runs **beside**
`sensor.home_threat_posture`; touches no card, no automation service
call, no dashboard for the three axes (QUIET is likewise read-only and
suppresses/reroutes nothing — see §1.1).

Renamed from `household_alert` 2026-08-22: the domain had stopped
describing the scope once QUIET (a household-activity modifier, not a
threat) joined STAGE/DIRECTIVE/INTEGRITY. Behaviour of the three axes
is unchanged by the rename — only the domain, entity ids and storage
key moved.

Source of truth for anything below is `custom_components/household_state/`
itself (`const.py` carries the rules and changelog in its module
docstring). This file is a reader's map onto that code, not a
replacement for it — if the two disagree, the code is right and this
file is stale.

## 1. What it's for

Three axes, not one ramp (LAW §11):

| Axis | Values | Audience | Question it answers |
|---|---|---|---|
| **STAGE** | normal / elevated / critical / unknown | Household | How urgent is it right now? |
| **DIRECTIVE** | none / secure / shelter / evacuate / unknown | Household | What do I physically do? |
| **INTEGRITY** | ok / degraded / unknown | Operator (Joel) | Can I trust the other two axes? |

INTEGRITY is a different audience, not a lower intensity — it never
moves STAGE, and there is no severity number on that axis by construction.

### 1.1 QUIET — the fourth signal, added 0.5.0

QUIET is a boolean modifier (LAW §11), not an axis: it carries no
severity and moves none of the three above. It is a read-only mirror of
`input_boolean.sleep_mode`, exposed as `binary_sensor.household_state_quiet`
so a consumer can read the household's QUIET state from this integration
instead of reaching into `input_boolean.sleep_mode` directly.

**Deliberately inert.** `is_on` is `None`, never `False`, when the
source cannot be read — the same KAN-139 shape every other entity here
uses, so an unreadable `sleep_mode` never silently claims the house is
NOT quiet. No STAGE/DIRECTIVE/INTEGRITY behavior, notification routing
or suppression logic reads this entity today. Any future suppression
behavior is a separate, future ruling — not an extension of what this
entity means.

## 2. Requirements to run

- HA core only — `manifest.json` declares `dependencies: []`,
  `requirements: []`. No PyPI package, no third-party service.
- `integration_type: service`, `iot_class: local_polling`,
  `single_config_entry: true` — one config entry, added once via
  **Settings → Devices & Services → Add Integration → Household State**.
  The config flow form is empty; there is nothing to fill in.
- Options flow exposes one value: `scan_interval` (10–300s, default 30).
  Do not raise it past `FALL_DWELL` (120s, `const.py`) without re-reading
  that constant — a poll slower than the dwell makes the dwell meaningless.
- **Upstream entities it reads** (none of these are declared as HA
  dependencies; a missing one degrades a source, it does not stop
  startup — see §5 Failure modes):
  - `sensor.nws_union_threat` (`packages/nws_alerts.yaml`) — `severity`,
    `headline`, `cap_responses` attributes. Feeds STAGE and, via
    `cap_responses`, DIRECTIVE.
  - `sensor.ntas_advisory_level` (`packages/ntas_national.yaml`) — `severity`.
  - `sensor.swpc_space_weather` — `severity`.
  - `alarm_control_panel.alarmo` — state ladder + `open_sensors`.
  - Entities carrying the **label** `fls_device`, domains `binary_sensor`
    (state `on` = open) and `cover` (state `open`) — resolved at every
    poll via the label registry, never a pinned id list.
  - `sensor.fls_device_status` (`packages/fls_monitoring.yaml`) — read
    **twice**, once per integrity category, off two attribute triples on
    the same entity: `fire_life_safety_integrity/_detail/_affected` and
    `security_integrity/_detail/_affected`.
  - `sensor.critical_networking_device_health`
    (`packages/network_client_monitoring.yaml` + `kiosk_wifi.yaml`
    combine) — `integrity/integrity_detail/integrity_affected`.
  - `input_boolean.sleep_mode` (`packages/sleep_mode.yaml`) — QUIET's one
    source, read raw (on/off), never through the SOURCES registry — it
    is not a threat input (§1.1).
  - **GH-55/KAN-311 (2026-08-24), three more `entity_id: None` INTEGRITY
    rows** — same "resolve fresh every poll off a registry, never a
    pinned list" idiom the perimeter row already used, not a new pattern:
    - `kiosk_live_page` — every `sensor.<host>_live_page` entity
      discovered off the entity registry (`platform == "kiosk_pi"`,
      `unique_id` ending `_live_page`). Reads the `diverged` /
      `read_unreachable` booleans that entity's own attrs already carry —
      both pre-dwelled by `kiosk_pi`'s own coordinator
      (`LIVE_PAGE_DIVERGE_DWELL`, `TRANSPORT_FAIL_DWELL`); this row does
      no re-thresholding of its own.
    - `config_entry_health` — the config entries the operator put IN
      SCOPE (#28, opt-in): an entry is watched when it owns an entity
      carrying the `integrity_watched` label (bindable,
      `config_entry_health.label`) or sitting on a device that does, and
      only those entities form the ratio. Two shapes, generic across every
      domain: `setup_retry` outright, or `loaded` with 100% of in-scope
      entities unavailable (never a partial ratio). A label that does not
      resolve, or that nothing carries, reads `absent` — never a hollow
      `ok`. `CONFIG_ENTRY_DWELL` (300s, `const.py`) holds a fresh bad
      reading before it counts — the one INTEGRITY row with no upstream
      dwell of its own, so without this a normal ~60-90s restart window
      would page Joel before HA finished starting. `affected_entries`
      carries the full finding list (`integrity_detail` is only its
      headline); `watched_count` / `unwatched_count` state the scope's size.
    - `notify_health` — `services.has_service("notify",
      "mobile_app_joels_iphone")`, the notify target
      `packages/household_state_integrity_notify.yaml` hardcodes. Catches
      a device re-pair silently orphaning that target. `notify.joels_iphone`'s
      state (last successful send) rides along as an informational
      attribute, never judged against a threshold — HA gets no APNs
      delivery receipt, and staleness during a quiet week is not evidence
      of anything. A delivery-freshness heartbeat was considered and
      rejected (Apple throttles silent pushes to ~5/device/day; a visible
      one means a recurring banner on Joel's phone forever) — see
      `const.py`'s `SOURCES` comment on this row for the full reasoning.
- **Storage**: `.storage/household_state.ages` (HA `Store` helper,
  version 1; `household_alert.ages` before the rename — the store key
  changed, so age clocks reset once on the first post-rename restart) —
  persists the "since" timestamp for stage/integrity/directive/quiet and
  for each perimeter member's own open-since. Must load **before** the
  first coordinator refresh (`async_setup_entry`) or every age clock
  resets to zero on restart.
- No restart is required to pick up an upstream entity that starts
  reporting later — the coordinator re-reads `hass.states.get()` every
  poll. A restart **is** required after editing `custom_components/`
  itself (TOOLS.md: `homeassistant.reload_core_config` does not
  re-import a custom component), and after the domain rename itself:
  the old `household_alert` config entry must be removed and a new
  `household_state` entry added — HA does not migrate entries across a
  domain change, and new entity ids are assigned (TOOLS.md: recreating
  an integration does not reuse old ids).

## 3. Process / dataflow

Every poll, the coordinator reads each `SOURCES` row plus the QUIET
source, hands the readings to the pure `resolve()` function in
`resolver.py`, applies a fall-only dwell to the resulting STAGE severity,
persists the "since" timestamps, and publishes a complete dict that six
entities read — never raising `UpdateFailed` even when a source is
unreadable. See `household_state_process_flow.md` for the full
control-flow diagram (poll → read → resolve → dwell → publish →
downstream triggers) including the five-step resolution order inside
`resolve()`, and `household_state_data_flow.md` for the data-lineage
diagram tracing each source entity's attribute through its resolving
function to its output entity attribute and consumer.

## 4. Entities produced

One device, "Household State" (`custom_components/household_state`,
`entity.py`). `_attr_has_entity_name = True`, so ids are
`sensor.household_state_<x>`, not device-name-doubled.

| Entity | Purpose | Key attributes |
|---|---|---|
| `sensor.household_state_stage` | STAGE axis | `severity`, `raw_severity`, `band`, `driver`, `detail`, `confidence`, `sources_total/healthy/unhealthy`, `fall_dwell_holding/since` |
| `sensor.household_state_directive` | DIRECTIVE axis, plus the resolved banner cell (#30) | `reason`, `driver`, `suppressed` (always present, never omitted empty), `source_count`; the cell: `cell`, `gate`, `imperative`, `action`, `tone`, `stage_word`, `stage_on`, `stage_tone`, `quiet`, `evacuate`, `status`, `hazard_driver`, `hazard_source`, `hazard_name`, `hazard_window` — always present, resolved in `banner.py` after the fall dwell (see `DESIGN_CONTRACT.md`, "The rendering matrix") |
| `sensor.household_state_integrity` | INTEGRITY axis | `detail`, `driver`, `affected_count`, `source_count`, `sources_detail` (newline-joined per-category breakdown) |
| `sensor.household_state_<source_key>` | One diagnostic entity per `SOURCES` row (`EntityCategory.DIAGNOSTIC`) | `entity_id`, `axis`, `severity`, `raw_state`, `detail` — this is where a dead feed becomes visible instead of a silent zero |
| `binary_sensor.household_state_feed_health` | Fleet-wide "can I trust the axes above" flag | `device_class: problem`, `unhealthy`, `confidence`, `sources_healthy/total` |
| `binary_sensor.household_state_quiet` | QUIET modifier (0.5.0), read-only mirror of `input_boolean.sleep_mode` | `source_entity_id`, `raw_state`, `since` |

**Every entity overrides `available` to `True`.** A monitor that goes
unavailable when its subject does is the exact failure this integration
exists to refuse (KAN-139) — an unreadable source shows as a
`disposition` attribute (or, for QUIET, `is_on: None`), never as the
entity disappearing.

## 5. Failure modes — by design, not by omission

| Situation | What happens | Why |
|---|---|---|
| Upstream entity never created | `disposition: absent` | KAN-182 — "never existed" ≠ "answered all-clear" |
| Upstream entity `unavailable` | `disposition: unreachable` | distinct from `unknown` |
| Upstream entity state `unknown`/empty | `disposition: unknown` | — |
| Severity attribute present but non-numeric | `disposition: unparsed` | KAN-207 — display and ramp must be able to disagree visibly, not silently collapse |
| All healthy STAGE sources idle, ≥1 source unreadable | `stage: unknown`, not `normal` | RULE 2 — an unhealthy source can never contribute an implicit 0 |
| `fls_device` label does not resolve | Perimeter row `disposition: absent` | label lookup failure ≠ "house has no doors" |
| Perimeter member unreadable | Row `unknown` **unless** a different member is already sustained-open | a positive finding doesn't need full visibility; a negative one does |
| Coordinator's own read logic throws | **Never raises `UpdateFailed`** — always returns a dict | RULE 1: raising takes every entity unavailable and their attributes vanish, which is how a broken collector reads green |
| CAP `response` missing on an alert | Directive `unknown`, reason `cap_response_absent_on_N_alert` — **unless** a positive directive was already found on another alert | KAN-139 applied to the directive axis |
| `input_boolean.sleep_mode` missing/unavailable/unknown | `binary_sensor.household_state_quiet` reads `is_on: None`, never `False` | same KAN-139 shape — an unreadable source must never read as a real negative |
| A config entry sits in `setup_retry`, or `loaded` with 100% of owned entities unavailable, for < `CONFIG_ENTRY_DWELL` (300s) | Not yet counted | avoids paging Joel during a normal ~60-90s restart window |
| A config entry's outage is partial (some but not all owned entities unavailable) | Never counted, even past the dwell | a deliberate choice to avoid false positives — "some entities down" is common and often benign |
| A kiosk's live_page diverges from kiosk.sh, or DevTools stops answering | `kiosk_live_page` row degrades **only** once `kiosk_pi`'s own pre-dwelled `diverged`/`read_unreachable` booleans say so | no re-thresholding here — one accessor, owned by the component that polls the host |
| `notify.mobile_app_joels_iphone` is no longer a registered service (device re-paired) | `notify_health` row degrades | the real, previously-uncaught failure mode this row exists for |
| `notify.joels_iphone`'s last-send timestamp is old | **Never** treated as degraded on its own | staleness during a quiet week with no alerts is not evidence of anything — see `const.py`'s `SOURCES` comment |

## 6. Current consumers (as of 2026-08-24)

- `sensor.household_state_integrity` — **live**: `packages/
  household_state_integrity_notify.yaml` (operator push, time-sensitive
  iff Fire Life Safety Device Health is the degraded category; the
  automation's internal `id:` stayed `household_alert_integrity_
  operator_notification` across the rename — deliberate, see the
  package file's own header), `www/integrity-card.js`, `www/
  room-panel.js`'s opt-in integrity ring. GH-55/KAN-311's three new
  INTEGRITY rows (`kiosk_live_page`, `config_entry_health`,
  `notify_health`) feed this SAME entity and therefore this same
  consumer chain — no new consumer was added, the existing operator
  channel just got three more sources.
- `sensor.household_state_stage` — **not yet wired**. `www/
  today-banner-card.js` still reads the older
  `sensor.home_threat_posture` (KAN-287 tracks the repoint).
- `sensor.household_state_directive` — **no consumer**. LAW §11's hard
  gate blocks any directive surface until EVACUATE has a verified input;
  KAN-308 (open) is the end-to-end drill that would clear it.
- `binary_sensor.household_state_quiet` — **no consumer yet**. Added
  0.5.0 as a read-only signal; nothing reads it today. It exists so a
  future card or automation has one place to read QUIET instead of
  `input_boolean.sleep_mode` directly — see §1.1 for what it
  deliberately does not do.
- `sensor.home_threat_posture` (the older, six-block template sensor this
  integration was written to replace) is **frozen** per LAW §3 — kept
  only as the comparison reference, will-not-fix.

## 7. Open tickets touching this integration

Query live before trusting this list — issues move. At time of writing:
KAN-308 (end-to-end drill, blocks the directive hard-gate), KAN-314
(presence-aware directive routing), KAN-347/348/349 (three integrity-axis
source gaps named directly in `const.py`'s `SOURCES` comments: camera/NVR,
Starlink, Spectrum — each stated permanently in its category's `*_detail`
attribute rather than silently absent). GH-55/KAN-311 (operator channel
consolidation) closed 2026-08-24 — see §2's three new SOURCES rows.
