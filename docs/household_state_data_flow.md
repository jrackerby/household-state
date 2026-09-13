# household_state — data flow

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
(what triggers, in what order) · [`household_state_architecture.md`](household_state_architecture.md)
(the static modules) · [`household_state.md`](household_state.md) (full
technical reference) · [`household_alert_patent_disclosure.md`](household_state_patent_disclosure.md)
(patent-disclosure draft, pinned to the pre-rename name/version — see its
own footer).

This file answers **which value came from where**: source entity attribute,
through which pure function, to which output entity attribute, to which
consumer. For **what triggers, in what order**, see
`household_state_process_flow.md` instead.

## Data lineage, by axis

```mermaid
flowchart LR
    subgraph STAGE_LINE["STAGE axis lineage"]
        direction LR
        SA1["sensor.nws_union_threat<br/>.severity attr"] --> SF1["_read_source()<br/>int(severity) or DISP_UNPARSED"]
        SA2["sensor.ntas_advisory_level<br/>.severity attr"] --> SF1
        SA3["sensor.swpc_space_weather<br/>.severity attr"] --> SF1
        SA4["alarm_control_panel.alarmo<br/>.state + .open_sensors"] --> SF2["alarm_severity()<br/>resolver.py — state ladder"]
        SA5["fls_device label members<br/>(binary_sensor 'on' / cover 'open')"] --> SF3["_read_perimeter()<br/>+ persisted open-since -> PERIMETER_SEV<br/>after 300s dwell"]

        SF1 --> RES1["resolve(): TIEBREAK walk,<br/>highest severity among healthy rows"]
        SF2 --> RES1
        SF3 --> RES1

        RES1 -->|"severity, driver, detail, confidence"| DW["_apply_fall_dwell()<br/>fall held 120s, rise immediate"]
        DW -->|"severity, raw_severity, stage, band"| SEO["sensor.household_state_stage<br/>attrs: severity/raw_severity/band/driver/<br/>detail/confidence/sources_total/healthy/<br/>unhealthy/fall_dwell_holding/since"]
    end

    subgraph DIR_LINE["DIRECTIVE axis lineage"]
        direction LR
        DA1["sensor.nws_union_threat<br/>.cap_responses attr — SAME entity as SA1,<br/>different attribute"] --> DF1["_read_source(kind='cap')<br/>-> list of {response, event} pairs"]
        DF1 --> RES2["resolve_directive():<br/>response-field classifier +<br/>event-name classifier, both run<br/>on every pair; suppression list;<br/>precedence EVACUATE>SHELTER>SECURE"]
        RES2 -->|"directive, reason, driver, suppressed"| DEO["sensor.household_state_directive<br/>attrs: reason/driver/suppressed/source_count/since"]
    end

    subgraph INTEG_LINE["INTEGRITY axis lineage"]
        direction LR
        IA1["sensor.fls_device_status<br/>.fire_life_safety_integrity/_detail/_affected"] --> IF1["_read_source(kind='fls')<br/>reads the named attribute triple<br/>off the SOURCES row, not a hardcoded name"]
        IA2["sensor.fls_device_status<br/>.security_integrity/_detail/_affected<br/>— SAME entity as IA1, different triple"] --> IF1
        IA3["sensor.critical_networking_device_health<br/>.integrity/_detail/_affected"] --> IF1
        IA4["kiosk_pi entity registry (platform+tail)<br/>-> each sensor.&lt;host&gt;_live_page's<br/>.diverged/.read_unreachable (pre-dwelled<br/>by kiosk_pi itself)"] --> IF4["_read_live_page(kind='live_page')<br/>GH-55/KAN-311 — no dwell of its own,<br/>aggregates across every discovered host"]
        IA5["config_entries.async_entries() (every domain)<br/>+ entity registry per entry"] --> IF5["_read_config_entries(kind='config_entries')<br/>GH-55/KAN-311 — setup_retry OR loaded+all-<br/>entities-dead; CONFIG_ENTRY_DWELL (300s)"]
        IA6["services.has_service('notify',<br/>'mobile_app_joels_iphone')<br/>+ notify.joels_iphone state (informational)"] --> IF6["_read_notify_health(kind='notify_health')<br/>GH-55/KAN-311 — target registered or not;<br/>staleness never judged"]
        IF4 --> RES3
        IF5 --> RES3
        IF6 --> RES3
        IF1 --> RES3["resolve(): unknown outranks degraded;<br/>else any degraded row -> degraded; else ok.<br/>Builds sources_detail (label~state~detail,<br/>newline-joined) across every row"]
        RES3 -->|"integrity, detail, driver, affected_count,<br/>sources_detail"| IEO["sensor.household_state_integrity<br/>attrs: detail/driver/affected_count/<br/>source_count/sources_detail/since<br/>— NO severity key, by design"]
    end

    subgraph QUIET_LINE["QUIET lineage — outside SOURCES, outside resolve()"]
        direction LR
        QA1["input_boolean.sleep_mode<br/>raw on/off state"] --> QF1["_read_quiet()<br/>coordinator.py — bypasses SOURCES/resolve()<br/>entirely; None (never False) if unreadable"]
        QF1 -->|"quiet, quiet_source_entity_id,<br/>quiet_raw_state, quiet_since"| QEO["binary_sensor.household_state_quiet<br/>attrs: source_entity_id/raw_state/since"]
    end

    SEO --> C1["automation: none —<br/>no state-change trigger reads this entity today"]
    SEO -.->|"KAN-287: not repointed"| C2["today-banner-card.js's postureEntity<br/>still defaults to, and reads,<br/>sensor.home_threat_posture (different integration)"]

    DEO -.->|"LAW §11 hard gate: no directive<br/>surface until EVACUATE has a<br/>verified input (KAN-308 open)"| C3["no consumer"]

    IEO --> C4["packages/household_state_integrity_notify.yaml<br/>reads .detail + .sources_detail -><br/>notify.mobile_app_joels_iphone"]
    IEO --> C5["www/integrity-card.js<br/>parses .sources_detail for its<br/>per-source breakdown table"]
    IEO --> C6["www/room-panel.js<br/>integrityEntity config (opt-in) reads<br/>.state for the integrity ring"]

    QEO -.->|"no consumer yet, 0.5.0"| C7["future: any card/automation reads this<br/>entity instead of input_boolean.sleep_mode<br/>directly"]

    style STAGE_LINE fill:#1a2a1a,stroke:#2b9c4a,color:#eee
    style DIR_LINE fill:#3a1a1a,stroke:#c0392b,color:#eee
    style INTEG_LINE fill:#1a2a3a,stroke:#2b7ac9,color:#eee
    style QUIET_LINE fill:#2a1a3a,stroke:#8a4ac9,color:#eee
    style C2 fill:#3a2a1a,stroke:#c98a2b,color:#eee
    style C3 fill:#3a1a1a,stroke:#c0392b,color:#eee
    style C7 fill:#1a2a3a,stroke:#2b7ac9,color:#eee
```

## Cross-axis fact: two rows, one entity, disjoint attributes

`sensor.nws_union_threat` feeds **two different axes** off two different
attributes of the same entity read (`.severity` into STAGE, `.cap_responses`
into DIRECTIVE) — one HA state read, two independent data lineages. The
same shape repeats for `sensor.fls_device_status`, which feeds **two
INTEGRITY rows** (`fire_life_safety_*` and `security_*` attribute triples)
off one entity. Both are deliberate per `const.py`'s SOURCES comments, not
duplication — `resolve()` never conflates the two lineages because each
row names its own attribute keys, and neither axis's output value is
computed from the other's.

## What never crosses a lineage boundary

- **QUIET's value never enters `resolve()`** and cannot contribute to
  STAGE/DIRECTIVE/INTEGRITY — `const.py`'s module docstring states this is
  deliberate: folding QUIET into `SOURCES` would run a household-activity
  boolean through RULE 2/RULE 4's severity-aggregation machinery, which it
  was never built for.
- **INTEGRITY's inputs never reach STAGE's output.** RULE 4: there is no
  `severity` key on the integrity entity's attributes at all, by
  construction — not by omission in the sensor code, but because
  `resolve()`'s INTEGRITY block never computes one.
- **The fall dwell applies only to the STAGE lineage.** DIRECTIVE and
  INTEGRITY values published each poll are whatever `resolve()` computed
  that cycle, undelayed.
