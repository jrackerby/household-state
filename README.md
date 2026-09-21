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
| `binary_sensor.household_state_<macro>` | `on` / `off` | one per [custom macro state](docs/migrating-from-input-boolean-helpers.md) you define — Guest, Vacation, Away. Modifiers too, on the same terms |
| `binary_sensor.household_state_feed_health` | problem | any source unhealthy, with `sources_healthy` / `sources_total` / `confidence` |
| `sensor.household_state_<source>` | per source | diagnostic, one per bound source — where a dead feed becomes visible instead of becoming a zero |

Severity and instruction are genuinely independent: a CAP alert can be
`Moderate` and still say *evacuate*, and a `Severe` one can ask for nothing at
all. Integrity is a third audience again — it addresses whoever maintains the
system, not the household, which is why it never moves stage.

Each axis carries `driver` (which source drove it), `severity`, `since` and the
directive's `reason` and `suppressed` list as attributes, so a surface can say
*which* rather than *that*.

The directive entity also carries **the resolved banner cell**: `cell`,
`gate` (`none` / `banner` / `evacuate` — what a surface mounts), `imperative`
and `action` (the words), `tone` and `stage_tone`, `status` (the status
line's parts) and `hazard_driver` / `hazard_source` / `hazard_name` /
`hazard_window` (what is driving the stage, named). The rendering matrix is
resolved once, in `banner.py`, so a wall, a phone and a voice surface all
give the same answer — including the one rule that takes the banner away: a
macro state may declare that it silences the cell while it is on (`masked` /
`masked_by`), and an evacuation is never silenced. The rules are in
[docs/DESIGN_CONTRACT.md](docs/DESIGN_CONTRACT.md#the-rendering-matrix-30).

## The rules that make the answers trustworthy

The invariants — unknown is never normal, integrity never moves stage, fall
dwell only, the coordinator never raises `UpdateFailed`, nothing is named at
zero, a modifier moves no axis — and the directive vocabulary, its two
classifiers and the hard gate are the design contract in
[docs/DESIGN_CONTRACT.md](docs/DESIGN_CONTRACT.md). `resolver.py` holds them
and imports nothing from `homeassistant`, so they are testable without Home
Assistant running.

## What it creates

Platforms: `sensor`, `binary_sensor`.

## Configuration

Config flow, single entry. Setup asks for nothing — there is no host, token
or endpoint. Everything else is under *Configure* on the entry, which opens on
a menu:

- **Poll interval and source bindings** — the settings below.
- **Define / Edit / Delete a macro state** — the custom household modifiers,
  documented in [docs/migrating-from-input-boolean-helpers.md](docs/migrating-from-input-boolean-helpers.md)
  and summarised below.

One setting is not a binding:

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
| `outside_person.entity_id` | person seen by an outside camera overnight (STAGE, severity 2 — a door left open). Its `cameras` attribute, a list of entity ids, is forwarded as `seen: …` | `binary_sensor` |
| `fire_life_safety.entity_id` | fire/life-safety health | `sensor` |
| `security_device_health.entity_id` | security health | `sensor` |
| `critical_networking_device_health.entity_id` | networking health | `sensor` |
| `notify_health.service_domain` | notify service domain | text |
| `notify_health.service` | notify service name | text |
| `notify_health.last_sent_entity_id` | last successful send | `sensor` |
| `quiet.entity_id` | sleep-mode helper (QUIET) | `input_boolean` |
| `perimeter.label` | label whose members are the perimeter | text |
| `config_entry_health.label` | label that puts a device or entity **in scope** for the config-entry integrity check (opt-in — unlabelled is not watched); defaults to `integrity_watched`; a label that does not resolve or that nothing carries reads `absent` | text |
| `banner.text_prefix` | your own wording per banner cell, read from `input_text.<prefix>_<cell>_imperative` / `_action` (for example `directive` → `input_text.directive_crit_shelter_imperative`); a helper reading `unknown` or empty is not set and the built-in default stands; unbound, only the defaults are used | text |
| `banner.jurisdiction` | the place the weather wording names for an event the matrix has no line for ("*Rip Current Statement* is in effect for *Union County*."); unbound, the line names no place | text |

**Leaving one blank is not the same as pointing it at nothing.** A blank
binding falls through to the row's own default; an id that does not resolve
reports `absent`, loudly, because a source this layer cannot read must never
read as a quiet zero.

Two rows may share one entity on purpose — `local_nws` and `nws_cap` read the
same threat sensor on different axes, as do the two boil-water rows, and the
fire/life-safety and security rows are told apart only by which attribute
triple they read. Bind them independently.

### Custom macro states

A macro state is a named household modifier — `Guest`, `Vacation`, `Away` —
resolved from an entity you already have and published as
`binary_sensor.household_state_<name>` on the same device as the axes. It is
QUIET's shape with the name and the source moved into the options flow, so a
second modifier is a form rather than a release.

*Configure → Define a macro state* asks for four things:

| field | | |
|---|---|---|
| **Name** | required | Becomes the entity id, **once**. Frozen after creation — see below. |
| **Entity to read** | required | Any entity: an `input_boolean` helper, a `schedule`, a `person`, an `input_select`. |
| **State that means on** | defaults to `on` | Matched exactly and case-sensitively against that entity's state. |
| **Icon** | optional | An `mdi:` icon. |

**It creates nothing writable.** A macro state mirrors the entity you name; it
does not become a switch, because this integration does not own the fact — the
bound entity does. A household that wants something flippable still wants an
`input_boolean`. What it stops needing is the template-sensor layer on top of
one, which is the actual migration.

**It moves no axis.** No severity, absent from `sources_total` and
`confidence`, and it cannot make the feed-health sensor report a problem. Guest
mode is not a hazard.

**Unreadable is `unknown`, never `off`.** The same refusal as every other read
here: `is_state()` in a template returns `false` for a helper that was deleted,
which is a positive claim about the household manufactured out of an absence. A
macro publishes `unknown` and states why in its `disposition` attribute
(`absent`, `unreachable`, `unknown`).

**The name sets the entity id and is frozen at creation.** Home Assistant never
reclaims an id, so a slug that tracked the name would mint a second entity on
every rename and orphan the one your dashboards read. The edit form changes the
friendly name, the bound entity, the state string and the icon — never the id.
`Quiet` and `Feed health` are refused because they collide with entities this
integration already publishes; `Stage`, `Directive` and `Integrity` are refused
because a binary sensor beside the sensor of the same name, answering a
different question, is a trap.

**Deleting one removes its registry row**, rather than leaving a permanently
unavailable entity holding the id — which is why that form asks for a
confirmation, and why re-adding the same macro later gets the same id back
instead of a `_2` suffix.

Each macro publishes `slug`, `source_entity_id`, `raw_state`, `on_state`,
`disposition` and `since` as attributes. `raw_state` and `on_state` are both
there on purpose: a macro stuck at `off` because the entity says `Home` and the
form says `home` is diagnosable from those two and from nothing else.

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
no helpers, calls no service, and modifies no entity it reads. Helpers a macro
state was bound to are untouched — a macro reads an `input_boolean`, it does
not own one.

## Development

Issues and feature requests: **[jrackerby/household-state/issues](https://github.com/jrackerby/household-state/issues)**.

CI runs [hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest)
and HACS validation on every push. `validate.yml` stages the repo into the
layout hassfest scans (`jrackerby/HA` `tools/work_docs/TOOLS.md` carries why);
the repo itself stays root-layout because `hacs.json` declares
`content_in_root: true`.

Pushing a `manifest.json` whose `version` has changed tags and publishes a
release automatically — that is the only supported way to cut one.
