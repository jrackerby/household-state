# household_state design contract

The resolver contract for this integration. Moved here from `jrackerby/HA`
`tools/work_docs/LAW.md` §11 (jrackerby/HA#802); LAW §11 points back at this
file. Rulings carry their citation; a change to one is a ruling, never a
refactor. Rendering rules for the surfaces that consume these axes live in
`jrackerby/ha-dashboard-kit/docs/DESIGN_CONTRACT.md`.

## Three axes, not one ramp

`household_state` (renamed from `household_alert`).

- **STAGE** (normal/elevated/critical) and **DIRECTIVE**
  (none/secure/shelter/evacuate/boil_water) address the household.
- **INTEGRITY** (ok/degraded/unknown) addresses the operator - a different
  audience, not a lower intensity.
- **QUIET** is a boolean modifier, `binary_sensor.household_state_quiet` -
  READ-ONLY, mirrors `input_boolean.sleep_mode`, suppresses nothing on any axis
  and **OWNS NO WORDS ON ANY SURFACE**. It renders as the shell field and ring
  and as a tint, never as a row of text (Joel: "I don't need the sleep mode
  text").

### DIRECTIVE vocabulary

Precedence, most urgent first: EVACUATE > SHELTER > SECURE > BOIL_WATER > none.

- `secure`, `shelter`, `evacuate` say where the household should BE.
- `boil_water` (Joel, ruling, GH-583) says what it must not DRINK - the one
  directive that is not a movement instruction, and the LOWEST precedence
  deliberately: water you must boil is not a reason to stay out of the closet.
  Its source is the water utility's boil-water advisory (`SOURCES` row
  `boil_water_directive`).
- Adding a word to this axis is a ruling, not a config change.

## Cross-component invariants

- Precedence is over **directives**, never severities. **Unknown is not Normal
  and never green. INTEGRITY never moves STAGE** - no `severity` key on the
  integrity entity.
- **INTEGRITY SURFACES ON THE OPERATOR BOARD ONLY, never on a household control
  wall** (Joel, ruling). `IntegrityBadge` mounts on the operator surface alone;
  which app that is, is inventory - read it live.
- **INTEGRITY ANSWERS FOR WHAT THE HOUSEHOLD DEPENDS ON, NEVER FOR WHAT ONE
  SCREEN IS SHOWING** (Joel, ruling, jrackerby/HA#717). The board SERVER dark is
  an integrity fault; a panel on the wrong page is its own integration's
  finding, published there.
- **INTEGRITY'S CONFIG-ENTRY SCOPE IS OPT-IN** (Joel, ruling, #28, reversing
  #26's opt-out): a label (`integrity_watched`, bindable) puts a device or
  entity IN scope; anything unlabelled is not the row's business under any
  shape. A label that does not resolve, or that nothing carries, is `absent`,
  never `ok` - a monitor with no scope must not read green.
- **Fall dwell, never rise dwell. Losing sight of a source counts as a fall.**
- **`ok at zero` and `could not read` are different values at the source**;
  `absent` and `unreachable` do not collapse.
- **The coordinator never raises `UpdateFailed`**; every entity overrides
  `available` to true - a monitor that disappears with its subject cannot
  report the subject down. The quality scale's `entity-unavailable` example
  does not govern here (LAW §15): a coordinator reading other entities has no
  service to lose.
- **Name nothing at zero. A declined signal is stated on the entity**
  (`suppressed`, always present).
- **The resolver imports nothing from `homeassistant`** - a pure, testable
  function.
- `SOURCES` in `const.py` is one list; a source is one row with an `axis`.

## The hard gate (RULED BY JOEL, supersedes the prior wording)

A directive surface may ship on `resolver.py`'s deterministic
EVACUATE/SHELTER/SECURE classification tests (event names verified live against
`api.weather.gov/alerts/types`, KAN-336) plus a live-observed input path
(jrackerby/HA#38, KAN-240: real non-zero severity, real CAP payload and a real
FLS fault each independently reached the resolver through the live estate). A
live evacuate-classified CAP alert is NOT required - the gate was never that
one specific alert, only that some verified path to the axis exists and its
classifier is provably correct.

## Two classifiers, both run on every alert

- `responseType` (KAN-208): `Shelter`/`Evacuate` promote; every other CAP
  response resolves to `none` and moves STAGE alone - a ruling made on live
  national distribution, not an oversight.
- Event NAME (KAN-336): NWS relays non-weather event types through the same
  feed and their meaning lives in the name. `secure` cites Law Enforcement
  Warning / Civil Danger Warning / Civil Emergency Message; `shelter` cites
  Shelter In Place Warning and the seal-up hazards (HazMat / Nuclear /
  Radiological); `evacuate` cites Evacuation Immediate.
- **Neither classifier suppresses the other on the same alert** - precedence
  picks the most urgent finding across both, so an event-name default can never
  downgrade a more urgent alert-specific `response`.
- An event in the suppression list is declined regardless of which classifier
  would have promoted it - response read and recorded, never silent (KAN-211).
  The list itself is a LAW §3 ruling (Severe Thunderstorm Warning).

## Severity is a declared extension layered on CAP, not CAP itself

Measured KAN-336 against 236 live alerts: one CAP severity maps to five
different `responseType`s, and `Moderate->Execute` outranks `Severe->Avoid` in
required action. CAP severity does not determine what the household should do,
which is why STAGE keeps its own local ramp instead of reading CAP's. Non-CAP
sources (CDC, CISA, NTAS) carry no CAP severity at all, which bounds the ramp's
scope the same way.

## The rendering matrix (#30)

The household banner's cell — which words, which tone, what is driving it —
is resolved ONCE, in `banner.py`, and published as attributes of
`sensor.household_state_directive`. A surface renders the cell it is handed
and proves the display only; a companion app or a voice surface reads the
same attributes and gives the same answer. This moved here from
ha-dashboard-kit's `directive.ts` / `hazard.ts` (jrackerby/estate#6 §4.2);
parity with the kit's resolver at the commit it left is recorded in
`tests/fixtures/banner_parity.json` and asserted by
`tests/test_banner_parity.py`.

- **The cell is copy; the directive is the contract.** `banner.py` decides how
  a (STAGE, DIRECTIVE) pair is worded and coloured and can promote or demote
  nothing. It runs after `resolve()` and the fall dwell, off the PUBLISHED
  stage word, so the cell and the stage entity can never disagree.
- **The cells:** `alert` (elevated, no directive), `elev_secure`,
  `elev_shelter`, `boil_water` (either stage), `crit_none` (critical, no
  directive), `crit_secure`, `crit_shelter`, `evacuate` and `unavailable`.
  `normal` with no directive is no cell at all (`cell: null`, `gate: none`).
  EVACUATE is checked first and is reachable from any stage; an axis that
  cannot be read is `unavailable`, never the empty row (unknown is not Normal
  and never green).
- **The gate verdict** (`gate`): `evacuate` mounts the exclusive inverted
  face and nothing else; `banner` mounts the persistent row; `none` mounts
  nothing.
- **Tone** is the kit's status ramp — `watch` at elevated, `crit` at critical,
  `stale` unreadable, `neutral` when QUIET tints. **QUIET tints, never
  suppresses, and never at critical.** `stage_tone` is the stage's own colour
  and QUIET does not move it.
- **The two generic cells are worded from the named hazard where one is
  known**, ahead of the operator's helper; the instruction cells are the
  operator's, always — hazard wording never displaces a location instruction.
  Only the shelter cells name the closet, and the suite asserts it across every
  default and every guidance line.
- **Names which, never that, and nothing machine-shaped reaches a line.** The
  alarm, perimeter and outside-camera rows carry their entity ids structured
  (`ids`) beside the raw detail string; the matrix words them off the state
  machine's `friendly_name` (the id's own words as a fallback, never a slug on
  glass). The raw identity stays on the source row and the stage's `detail`
  for the next diagnosis.
- **Two installation facts are bindings, not code:** `banner.text_prefix`
  (an operator's own wording per cell, read from
  `input_text.<prefix>_<cell>_imperative` / `_action`; a helper reading
  `unknown` or empty is not set) and `banner.jurisdiction` (the place the
  weather fallback line names; unbound, the line names no place rather than a
  wrong one).
- **Every attribute is always present** so a consumer can tell "no cell" from
  "no matrix": `cell`, `gate`, `imperative`, `action`, `tone`, `stage_word`,
  `stage_on`, `stage_tone`, `quiet`, `evacuate`, `status` (the status line's
  parts — reason, source, duration — deduplicated against the stage word and
  each other), `hazard_driver`, `hazard_source`, `hazard_name`,
  `hazard_window`.
