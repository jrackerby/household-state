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
