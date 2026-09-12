<p align="center">
  <img src="brand/logo@2x.png" alt="Household State" width="420">
</p>

# Household State

Resolves what a home already knows about hazards and readiness — weather and
CAP alerts, public advisories, an alarm panel, device-health sensors — into a
small set of answers a display or an automation can act on, and publishes them
as entities.

It **reads only**. It writes nothing, calls no service, creates no helper and
modifies no entity it reads. Every source is an entity you already have; this
integration is the resolution layer over them.

## Why it is not one alert level

A single `normal / elevated / critical` number collapses three questions that
need different answers, and the collapse is not recoverable downstream. So this
publishes them separately:

| entity | values | answers |
|---|---|---|
| `sensor.household_state_stage` | `normal`, `elevated`, `critical`, `unknown` | **how bad is it** — a severity ramp over every source on the stage axis |
| `sensor.household_state_directive` | `none`, `secure`, `shelter`, `evacuate`, `boil_water` | **what should people do** — an instruction, not an intensity |
| `sensor.household_state_integrity` | `ok`, `degraded`, `unknown` | **can this layer be trusted** — whether the sources behind the two answers above are readable |
| `binary_sensor.household_state_quiet` | `on` / `off` | whether the house is asleep. A modifier, not a severity: it suppresses nothing on any axis |
| `binary_sensor.household_state_feed_health` | problem | any source unhealthy, with `sources_healthy` / `sources_total` / `confidence` |
| `sensor.household_state_<source>` | per source | diagnostic, one per bound source — where a dead feed becomes visible instead of becoming a zero |

Severity and instruction are genuinely independent: a CAP alert can be
`Moderate` and still say *evacuate*, and a `Severe` one can ask for nothing at
all. Integrity is a third audience again — it addresses whoever maintains the
system, not the household, which is why it never moves stage.

Each axis carries `driver` (which source drove it), `severity`, `since` and the
directive's `reason` and `suppressed` list as attributes, so a surface can say
*which* rather than *that*.

## The rules that make the answers trustworthy

These are the invariants; `resolver.py` holds them and imports nothing from
`homeassistant`, so they are testable without Home Assistant running.

- **`unknown` is not `normal`, and never green.** A source that could not be
  read reports `absent` loudly rather than as a quiet zero.
- **`ok at zero` and `could not read` do not collapse**, on any source, at any
  layer. A per-source sensor's state is the *worse* of the two — the read
  succeeding is not the source being healthy.
- **Integrity never moves stage.** There is no `severity` on the integrity
  axis.
- **Fall dwell, never rise dwell.** A rise in severity publishes immediately; a
  fall is held for a dwell so a flap does not read as an all-clear. Losing
  sight of a source counts as a fall.
- **The coordinator never raises `UpdateFailed`** and every entity stays
  available. A monitor that disappears with its subject cannot report the
  subject down.
- **Nothing is named at severity zero.** A declined signal is stated on the
  entity (`suppressed`), never silently dropped.

## What it creates

Platforms: `sensor`, `binary_sensor`.

## Configuration

Config flow, single entry. Setup asks for nothing — there is no host, token
or endpoint. One option, changed under *Configure* on the entry:

| option | default | range | what it does |
|---|---|---|---|
| `scan_interval` | `3` seconds | `1`–`300` | How often every source is re-read. |

**Three seconds is deliberate and lowering it buys nothing.** Each poll is a
state-machine read — the state machine and the entity, config-entry and
service registries — with no network or disk IO, so the interval is set by
what a display needs rather than by a remote API's rate limit. It keeps stage
rise and fall latency under ten seconds, so a panel rendering the state does
not lag the house.

**Do not raise it past 8 seconds without reading `const.py` first.** Per the
fall-dwell rule above, a drop in severity is held for a dwell before it
publishes. A poll interval longer than that dwell makes the dwell meaningless —
the flap it exists to absorb lands between two polls and publishes as a real
fall.

### Which entities supply each source

The rest of the options bind a source to an entity in *your* installation.
A `SOURCES` row says what a source **means** — its axis, its kind, how its
severity is read. Which entity supplies it is yours to say.

| option | binds | domain |
|---|---|---|
| `local_nws.entity_id` | local NWS threat sensor (STAGE) | `sensor` |
| `nws_cap.entity_id` | CAP directive sensor (DIRECTIVE) | `sensor` |
| `ntas.entity_id` | NTAS advisory level | `sensor` |
| `space_weather.entity_id` | space weather | `sensor` |
| `alarm.entity_id` | alarm panel | `alarm_control_panel` |
| `boil_water.entity_id` | boil-water advisory (STAGE) | `binary_sensor` |
| `boil_water_directive.entity_id` | boil-water advisory (DIRECTIVE) | `binary_sensor` |
| `fire_life_safety.entity_id` | fire/life-safety health | `sensor` |
| `security_device_health.entity_id` | security health | `sensor` |
| `critical_networking_device_health.entity_id` | networking health | `sensor` |
| `notify_health.service_domain` | notify service domain | text |
| `notify_health.service` | notify service name | text |
| `notify_health.last_sent_entity_id` | last successful send | `sensor` |
| `quiet.entity_id` | sleep-mode helper (QUIET) | `input_boolean` |
| `perimeter.label` | label whose members are the perimeter | text |

**Leaving one blank is not the same as pointing it at nothing.** A blank
binding falls through to the row's own default; an id that does not resolve
reports `absent`, loudly, because a source this layer cannot read must never
read as a quiet zero.

Two rows may share one entity on purpose — `local_nws` and `nws_cap` read the
same threat sensor on different axes, as do the two boil-water rows, and the
fire/life-safety and security rows are told apart only by which attribute
triple they read. Bind them independently.

### Keeping a published id across a rename (advanced)

Each source also accepts a `<source>.slug` override. **A fresh install should
leave every one of these blank.**

It exists for one situation. A source's key becomes the tail of its entity's
unique id — `sensor.household_state_<slug>` — so if a key is ever renamed in a
release, Home Assistant mints a *new* entity and orphans the old one, because
it never reclaims an id. Every dashboard still reading the old id would then be
reading something that belongs to nothing.

Binding the slug to the previous key keeps the published id exactly where it
was. The stage sensor's `driver` attribute reports the same slug, so a surface
that joins `driver` to a per-source entity keeps matching.

## One implementation rule worth not breaking

Entity ages load **before** the first refresh. Skip that and every age clock
restarts at zero on every Home Assistant restart, which reads as a house that
just changed state rather than one that has been stable for a week.

## Install

**Via HACS.** HACS → ⋮ → *Custom repositories* → `https://github.com/jrackerby/household-state`,
category **Integration**. Install, restart Home Assistant, then add it under
*Settings → Devices & Services → Add Integration → "Household State"*.

The integration lives at the repository **root**, not under
`custom_components/`. `hacs.json` declares `content_in_root: true`, so HACS
copies the root into `/config/custom_components/household_state/`.

## Remove

*Settings → Devices & Services → Household State → ⋮ → Delete*, then remove the
repository from HACS.

**Read this before you reinstall.** Home Assistant never reclaims an entity id.
Deleting the entry frees the ids in the UI but not in the registry, so a
reinstall assigns `_2` suffixes — `sensor.household_state_stage_2` — and every
dashboard, automation and template still points at the originals, which now
belong to nothing.

So if you intend to reinstall, delete the old entity rows in *Settings →
Devices & Services → Entities* — filter on `household_state`, including the
ones shown as unavailable — before adding the integration back.

Nothing else is left behind. The integration writes no files outside its own
`.storage` ledger of entity ages, which goes with the config entry; it creates
no helpers, calls no service, and modifies no entity it reads.

## Development

Issues and feature requests: **[jrackerby/household-state/issues](https://github.com/jrackerby/household-state/issues)**.

CI runs [hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest)
and HACS validation on every push. hassfest scans `custom_components/*` and
takes no path argument, so `.github/workflows/validate.yml` stages this repo
into that layout before invoking it; the repo itself stays root-layout because
`hacs.json` declares `content_in_root: true`.

Pushing a `manifest.json` whose `version` has changed tags and publishes a
release automatically — that is the only supported way to cut one.
