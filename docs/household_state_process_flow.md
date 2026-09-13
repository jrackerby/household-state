# household_state — process flow

Siblings: [`household_state_abstract.md`](household_state_abstract.md) (what
this is for, no jargon) · [`household_state_data_flow.md`](household_state_data_flow.md)
(which value came from where) · [`household_state_architecture.md`](household_state_architecture.md)
(the static modules) · [`household_state.md`](household_state.md) (full
technical reference) · [`household_alert_patent_disclosure.md`](household_state_patent_disclosure.md)
(patent-disclosure draft, pinned to the pre-rename name/version — see its
own footer).

This file answers **what happens, in what order**, from one poll tick to a
published entity and whatever reads it next. For **what value came from
which source**, see `household_state_data_flow.md` instead — the two are
deliberately separate diagrams per `jrackerby/HA` `docs/PROCESS.md`.

## Control flow, in execution order

```mermaid
flowchart TD
    TICK["Poll tick<br/>DataUpdateCoordinator, every scan_interval<br/>(10-300s, default 30s)"] --> READ

    subgraph READ["Per-source read — coordinator._read_source() / _read_perimeter() / _read_quiet() / GH-55's _read_live_page() / _read_config_entries() / _read_notify_health()"]
        direction TB
        R1["Look up each SOURCES row's entity_id<br/>via hass.states.get()"]
        R2["Perimeter row: resolve fls_device label<br/>live via label/entity registry, never a pinned list"]
        R3["QUIET: read input_boolean.sleep_mode raw,<br/>outside SOURCES entirely"]
        R5["GH-55/KAN-311, entity_id None rows:<br/>kiosk_pi live_page entities (registry query),<br/>config_entries (every domain, CONFIG_ENTRY_DWELL),<br/>notify.mobile_app_joels_iphone service check"]
        R1 --> R4["Assign one disposition per source:<br/>ok / absent / unreachable / unknown / unparsed<br/>— never severity 0 for a source that couldn't be read"]
        R2 --> R4
        R5 --> R4
    end

    READ --> RESOLVE["resolve() — resolver.py, pure, no HA imports"]

    subgraph RESORDER["Resolution order inside resolve()"]
        direction TB
        ST1["1. STAGE — walk TIEBREAK (alarm, perimeter_open,<br/>nws_union, ntas, space_weather) in fixed order;<br/>take highest severity among healthy rows.<br/>Any unhealthy row present while healthy rows are<br/>idle forces severity=None -> unknown, not normal.<br/>No driver named at severity 0."]
        ST2["2. DIRECTIVE — resolve_directive() runs two<br/>independent classifiers per CAP pair (response-field<br/>map, event-name map), checks the suppression list,<br/>then picks the most urgent finding by fixed<br/>precedence EVACUATE > SHELTER > SECURE.<br/>A suppression is always recorded, never silent."]
        ST3["3. INTEGRITY — any unreadable integrity row -><br/>unknown (outranks degraded); else any row degraded<br/>-> degraded; else ok. Builds a per-source<br/>sources_detail breakdown across every integrity row."]
        ST4["4. QUIET — read straight off input_boolean.sleep_mode,<br/>outside resolve() entirely (not a resolve() input).<br/>None when source missing/unavailable/unknown;<br/>else the literal on/off state."]
        ST1 --> ST2 --> ST3 --> ST4
    end

    RESOLVE --> RESORDER

    RESORDER --> DWELL["5. coordinator._apply_fall_dwell()<br/>applies to the resolved STAGE severity ONLY —<br/>never to directive, integrity or quiet.<br/>Rise: publishes immediately.<br/>Fall (including losing a source): held FALL_DWELL<br/>(120s) before it takes effect."]

    DWELL --> PERSIST["Persist 'since' timestamps for<br/>stage/integrity/directive/quiet, and each perimeter<br/>member's own open-since, to .storage<br/>(household_state.ages) — RULE 5, ages loaded BEFORE<br/>first refresh or every clock resets on restart"]

    PERSIST --> PUBLISH["Coordinator returns a complete dict —<br/>NEVER raises UpdateFailed (RULE 1).<br/>An individual unreadable source shows as a<br/>disposition attribute, not a missing entity."]

    PUBLISH --> ENTITIES["Entities read coordinator.data<br/>(sensor.py / binary_sensor.py) —<br/>every entity overrides available=True"]

    ENTITIES --> E3["sensor.household_state_integrity changes"]
    ENTITIES --> E1["sensor.household_state_stage changes"]
    ENTITIES --> E2["sensor.household_state_directive changes"]
    ENTITIES --> E6["binary_sensor.household_state_quiet changes"]

    E3 --> AUTO["State-change trigger:<br/>automation household_alert_integrity_operator_notification<br/>(id kept stable across the rename)"]
    AUTO --> PUSH["notify.mobile_app_joels_iphone<br/>time-sensitive iff Fire Life Safety row degraded"]

    E3 --> RING["room-panel.js re-renders its<br/>integrity ring (opt-in, integrityEntity config)"]
    E3 --> CARD["integrity-card.js re-renders<br/>sources_detail breakdown"]

    E1 -.->|"NOT YET wired to any trigger — KAN-287"| BANNER["today-banner-card.js's posture pill still<br/>triggers off sensor.home_threat_posture,<br/>a different entity from a different integration"]

    E2 -.->|"NO trigger exists — hard-gated"| GATE["LAW §11: no directive surface ships<br/>until EVACUATE has a verified input (KAN-308 open)"]

    E6 -.->|"NO trigger exists yet — read-only signal, 0.5.0"| QCONS["future: a card or automation would need its own<br/>state-change trigger on this entity; none registered today"]

    style RESORDER fill:#1a2a3a,stroke:#2b7ac9,color:#eee
    style GATE fill:#3a1a1a,stroke:#c0392b,color:#eee
    style BANNER fill:#3a2a1a,stroke:#c98a2b,color:#eee
    style QCONS fill:#1a2a3a,stroke:#2b7ac9,color:#eee
```

## Notes on the ordering above

- **Steps 1-4 inside `resolve()` are sequential in the source, not
  independent.** They read the same `readings` list but write to disjoint
  output keys, so nothing downstream depends on the order in which STAGE,
  DIRECTIVE, INTEGRITY and QUIET are computed within a single call — the
  order shown mirrors `resolver.py`'s actual top-to-bottom layout
  (`resolve()`'s STAGE block, then `resolve_directive()`, then the
  INTEGRITY block; QUIET is computed by the coordinator separately,
  outside `resolve()`, and merged into the same output dict afterward).
- **The fall dwell (step 5) runs after `resolve()` returns, in the
  coordinator, not inside the pure resolver** — `resolver.py` has no
  clock and cannot be, by its own docstring's design intent (a function
  that needs a clock can't be exercised by inspection alone).
- **Persistence and publication are the same poll cycle.** There is no
  separate "commit" step; `_async_update_data()` returns once, and that
  return value is what `coordinator.data` becomes for every entity.
- **QUIET's read has no dependency on STAGE/DIRECTIVE/INTEGRITY and no
  consumer trigger exists yet** — it publishes on the same poll cycle
  but nothing in the diagram above currently reacts to it changing.
