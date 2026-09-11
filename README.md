# Household State

The resolver half of a household directive layer, plus the QUIET modifier
derived from sleep mode.

It reads only: it writes nothing, calls no service, and touches no card — it
resolves state and publishes it. `sensor.household_state_stage` is the surface
consumers read. `const.py` carries the resolution rules and the scope
decisions behind them.

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
what a wall display needs rather than by a remote's rate limit. It keeps STAGE
rise and fall latency under ten seconds so a tablet rendering the state does
not lag the house.

**Do not raise it past 8 seconds without reading `const.py` first.** A fall in
severity is held for a dwell before it publishes (a rise never is). A poll
interval longer than that dwell makes the dwell meaningless — the flap it
exists to absorb lands between two polls and publishes as a real fall.

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

## One rule worth not breaking

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
belong to nothing. This integration already carries one live scar of exactly
that (`sensor.household_state_boil_water_advisory_2`, GH-565).

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
