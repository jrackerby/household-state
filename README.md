# Household State

The resolver half of the estate's directive layer, plus the QUIET modifier
derived from sleep mode.

It runs **beside** `sensor.home_threat_posture`, not instead of it. It writes
nothing, calls no service, and touches no card — it resolves state and exposes
it. `const.py` carries the resolution rules and the list of things `0.1.0`
deliberately does not do.

## What it creates

Platforms: `sensor`, `binary_sensor`.

## Configuration

Config flow, single entry. The only option is `scan_interval`.

GH-454 cut STAGE rise and fall latency to under ten seconds so a tablet
rendering the state does not lag the house.

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

> **That path has two owners today.** `jrackerby/HA` also submodules this repo
> as `custom_components/household_state` and writes the same directory on deploy. Until
> that cutover is settled (jrackerby/HA#483), a HACS install and a `git push ha
> master` will fight over it — install here only if you are not deploying this
> component from `jrackerby/HA`.

## Development

Issues and the work queue live in **[jrackerby/HA](https://github.com/jrackerby/HA/issues)**,
not here — one queue for the whole estate.

CI runs [hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest)
and HACS validation on every push. hassfest scans `custom_components/*` and
takes no path argument, so `.github/workflows/validate.yml` stages this repo
into that layout before invoking it; the repo itself stays root-layout because
`jrackerby/HA` submodules it at that path.

Pushing a `manifest.json` whose `version` has changed tags and publishes a
release automatically — that is the only supported way to cut one.
