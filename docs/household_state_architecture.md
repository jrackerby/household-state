# household_state — architecture

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

Siblings: [`household_state_abstract.md`](household_state_abstract.md) (what
this is for, no jargon) · [`household_state_process_flow.md`](household_state_process_flow.md)
(what triggers, in what order) · [`household_state_data_flow.md`](household_state_data_flow.md)
(which value came from where) · [`household_state.md`](household_state.md)
(full technical reference) · [`household_alert_patent_disclosure.md`](household_state_patent_disclosure.md)
(patent-disclosure draft, pinned to the pre-rename name/version — see its
own footer).

This file answers **what the static pieces are and how they compose** —
modules, files, entities, the system boundary. Nothing in this diagram
moves; for control flow and data lineage see the two flow files instead.

## Module diagram

```mermaid
flowchart TB
    subgraph EXT["System context — outside household_state"]
        direction TB
        HACORE["HA core: state machine, entity/label registry,\nStore helper, DataUpdateCoordinator base class"]
        SRC5["Upstream entity sources (8-plus):\nsensor.nws_union_threat, sensor.ntas_advisory_level,\nsensor.swpc_space_weather, alarm_control_panel.alarmo,\nfls_device-labeled binary_sensor/cover,\nsensor.fls_device_status, sensor.critical_networking_device_health,\ninput_boolean.sleep_mode"]
        SRC6["KAN-311 sources (GH-55), entity_id None,\ndiscovered/checked live every poll:\nkiosk_pi live_page entities (registry,\nplatform+unique_id tail), config_entries\nregistry (every domain, generic shape),\nnotify.mobile_app_joels_iphone service\nregistration + notify.joels_iphone state"]
        AUTOPKG["packages/household_state_integrity_notify.yaml\n(automation package)"]
        INTCARD["www/integrity-card.js"]
        ROOMPANEL["www/room-panel.js\n(integrityEntity, opt-in)"]
        BANNER["www/today-banner-card.js\nNOT YET WIRED to this integration — KAN-287\nstill reads sensor.home_threat_posture"]
    end

    subgraph MOD["custom_components/household_state/ — this integration's modules"]
        direction TB

        CONST["const.py\nSOURCES registry (one row per source, axis-tagged),\nTIEBREAK order, DIRECTIVE_RESPONSE_MAP /\nDIRECTIVE_EVENT_MAP / DIRECTIVE_EVENT_SUPPRESS,\ndisposition + band + stage constants,\nQUIET_SOURCE_ENTITY (outside SOURCES)"]

        RESOLVER["resolver.py\nPURE — imports nothing from homeassistant.*.\nresolve(), resolve_directive(), alarm_severity(),\nband_for(), stage_for().\nArchitecturally significant: testable by plain\npython3 with no HA, no live state, no restart —\nthe conflict table (fire+tornado, evacuate+degraded,\nall-inputs-unavailable, ...) runs against this file\ndirectly."]

        COORD["coordinator.py\nHouseholdStateCoordinator(DataUpdateCoordinator).\nOwns: per-source reads (_read_source/_read_perimeter/\n_read_quiet, plus KAN-311's _read_live_page/\n_read_config_entries/_read_notify_health, GH-55),\nthe fall-dwell state machine (_apply_fall_dwell),\nthe persisted 'since' clock (_mark, incl.\nCONFIG_ENTRY_DWELL), the .storage Store handle.\nCalls resolver.py; resolver.py never calls back\ninto this file."]

        ENTITY["entity.py\nHouseholdStateEntity(CoordinatorEntity) base class.\nOne DeviceInfo for the whole layer\n(_attr_has_entity_name = True)."]

        SENSORPY["sensor.py\nStageSensor, DirectiveSensor, IntegritySensor,\nSourceSensor (one per SOURCES row, DIAGNOSTIC category).\nEvery entity overrides available -> True."]

        BSENSORPY["binary_sensor.py\nFeedHealth (problem device_class),\nQuiet (0.5.0 — read-only mirror of\ninput_boolean.sleep_mode).\nEvery entity overrides available -> True."]

        CONFIGFLOW["config_flow.py\nHouseholdStateConfigFlow — single instance, empty form.\nHouseholdStateOptionsFlow — scan_interval (10-300s)."]

        INITPY["__init__.py\nasync_setup_entry: loads ages BEFORE first refresh\n(RULE 5), forwards to PLATFORMS,\nregisters update-listener for reload on options change."]

        STORE[(".storage/household_state.ages"\nHA Store helper, version 1\npersists since-timestamps for\nstage/integrity/directive/quiet\nand each perimeter member)]

        CONST --> RESOLVER
        CONST --> COORD
        RESOLVER --> COORD
        COORD --> STORE
        STORE --> COORD
        CONST --> SENSORPY
        ENTITY --> SENSORPY
        ENTITY --> BSENSORPY
        COORD --> SENSORPY
        COORD --> BSENSORPY
        CONFIGFLOW --> INITPY
        INITPY --> COORD
        INITPY --> SENSORPY
        INITPY --> BSENSORPY
    end

    subgraph ENTITIES["Entities published (device: 'Household State')"]
        direction TB
        E_STAGE["sensor.household_state_stage"]
        E_DIR["sensor.household_state_directive"]
        E_INT["sensor.household_state_integrity"]
        E_SRC["sensor.household_state_&lt;source_key&gt;\n(one per SOURCES row, diagnostic)"]
        E_FH["binary_sensor.household_state_feed_health"]
        E_QUIET["binary_sensor.household_state_quiet"]
    end

    SENSORPY --> E_STAGE
    SENSORPY --> E_DIR
    SENSORPY --> E_INT
    SENSORPY --> E_SRC
    BSENSORPY --> E_FH
    BSENSORPY --> E_QUIET

    HACORE -.->|"is the system boundary:\nDataUpdateCoordinator, Store,\nentity/label registry APIs"| COORD
    SRC5 -->|"hass.states.get() reads,\nlabel registry query for\nfls_device"| COORD
    SRC6 -->|"entity registry query\n(platform+unique_id tail),\nconfig_entries.async_entries(),\nservices.has_service()"| COORD

    E_INT --> AUTOPKG
    E_INT --> INTCARD
    E_INT --> ROOMPANEL
    E_STAGE -.->|"no consumer wired"| BANNER
    E_DIR -.->|"hard-gated, LAW §11:\nno directive surface until\nEVACUATE has a verified input\n(KAN-308 open)"| GATE["(no consumer — blocked by design)"]
    E_QUIET -.->|"no consumer yet, 0.5.0"| QNONE["(no consumer — read-only signal,\nfuture cards/automations may read it)"]

    style CONST fill:#2a2a1a,stroke:#c9a22b,color:#eee
    style RESOLVER fill:#1a2a3a,stroke:#2b7ac9,color:#eee
    style COORD fill:#1a2a1a,stroke:#2b9c4a,color:#eee
    style ENTITY fill:#2a1a3a,stroke:#8a4ac9,color:#eee
    style SENSORPY fill:#2a1a3a,stroke:#8a4ac9,color:#eee
    style BSENSORPY fill:#2a1a3a,stroke:#8a4ac9,color:#eee
    style CONFIGFLOW fill:#1a1a2a,stroke:#5a5a9c,color:#eee
    style INITPY fill:#1a1a2a,stroke:#5a5a9c,color:#eee
    style STORE fill:#2a2a2a,stroke:#888,color:#eee
    style GATE fill:#3a1a1a,stroke:#c0392b,color:#eee
    style BANNER fill:#3a2a1a,stroke:#c98a2b,color:#eee
    style QNONE fill:#1a2a3a,stroke:#2b7ac9,color:#eee
```

## Why `resolver.py`'s import-freedom is architecturally significant

`resolver.py` imports nothing from `homeassistant.*` — verified against
the file's own import block, which pulls only from `.const`. This is not
an incidental style choice; it is the property that makes the module
testable without a running HA instance, without live state, and without a
restart: `resolve()` and `resolve_directive()` are plain functions over
plain dicts, so the safety-relevant conflict table (fire + tornado
simultaneously, evacuate + degraded integrity, every input unavailable at
once) can be exercised by calling the function directly. `coordinator.py`
is the only module in this tree that touches `hass.states`, the label
registry, or the `Store` helper — every HA-coupled concern is
concentrated there, one layer above the pure logic.

## System boundary

- **Into `household_state`**: `hass.states.get()` reads against the
  upstream entities named in `const.py`'s `SOURCES` registry (none
  declared as HA `dependencies` — a missing one degrades a source, it
  does not block startup), a label-registry query for the `fls_device`
  label (perimeter row), and a raw state read of
  `input_boolean.sleep_mode` (QUIET, outside `SOURCES`). GH-55/KAN-311
  added three more entity_id-None rows on the same "resolve fresh every
  poll, never a pinned list" idiom the perimeter row already used: an
  entity-registry query for `kiosk_pi` live_page sensors (platform +
  unique_id tail, never a host list — `kiosk_live_page`), a
  `config_entries.async_entries()` walk plus per-entry entity-registry
  reads (`config_entry_health`, generic across every domain), and
  `services.has_service()` against the hardcoded notify target plus a
  raw state read of `notify.joels_iphone` (`notify_health`).
- **Out of `household_state`**: six entity classes under one device,
  read by consumers via normal HA entity state (`hass.states`), never a
  direct Python import — `www/*.js` cards and `packages/*.yaml`
  automations are decoupled from this integration's internals by that
  boundary.
- **This integration calls no service and renders no card of its own** —
  confirmed by `__init__.py` (`async_setup_entry` only sets up the
  coordinator and forwards platforms) and by grep across `packages/*.yaml`
  and `www/*.js` finding no `household_state.*` service definition.
