/** THE PARITY FIXTURE GENERATOR (#30).
 *
 *  banner.py is a port of ha-dashboard-kit's `directive.ts` + `hazard.ts`,
 *  and a port proven by reading two files side by side is a port proven by
 *  nobody. This file runs the KIT'S OWN resolver over every state map its
 *  preview harness, its design-sync previews and its unit suite draw, and
 *  writes what the kit rendered to tests/fixtures/banner_parity.json.
 *  tests/test_banner_parity.py then asserts banner.py says the same thing
 *  for every case. The kit's directive.ts is the oracle and the fixture is
 *  its recorded verdict at one commit; the kit deletes those files once its
 *  banner reads the attribute instead.
 *
 *  Regenerate (only while the kit still carries directive.ts):
 *    cp tools/banner_parity_fixture.ts <kit>/src/__parity.test.ts
 *    cd <kit> && OUT=<this repo>/tests/fixtures/banner_parity.json \
 *      npx vitest run src/__parity.test.ts
 *    rm <kit>/src/__parity.test.ts
 */
import { it } from 'vitest';
import { execSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { directiveNow, statusParts } from './directive';
import type { HassEntity } from './types';

type State = Pick<HassEntity, 'state' | 'attributes'>;
const s = (state: string, attributes: Record<string, unknown> = {}): State => ({ state, attributes });
const hass = (entries: Record<string, State>) => ({ states: new Map(Object.entries(entries)) });

const STAGE = 'sensor.household_state_stage';
const DIRECTIVE = 'sensor.household_state_directive';
const QUIET = 'binary_sensor.household_state_quiet';
const NWS = 'sensor.household_state_nws_union';
const PERIM = 'sensor.household_state_perimeter_open_sustained';
const ALARM = 'sensor.household_state_alarm';

const HEAT_ADVISORY: Record<string, State> = {
  [STAGE]: s('elevated', {
    severity: 2, band: 'Elevated', driver: 'nws_union',
    detail: 'Heat Advisory issued September 2 at 3:29AM EDT until September 2 at 8:00PM EDT by NWS',
  }),
  [DIRECTIVE]: s('none', { reason: 'no_directive_response', suppressed: [] }),
  [QUIET]: s('off'),
  [NWS]: s('ok', { raw_state: 'Heat Advisory', detail: 'Heat Advisory issued...' }),
  'input_text.directive_alert_imperative': s('Be on alert'),
  'input_text.directive_alert_action': s('Something may be developing — stay reachable'),
};

const SHELTER: Record<string, State> = {
  [STAGE]: s('critical', { severity: 7, driver: 'nws_union' }),
  [DIRECTIVE]: s('shelter', { reason: 'cap_response', driver: 'Tornado Warning', suppressed: [] }),
  [QUIET]: s('off'),
  [NWS]: s('ok', { raw_state: 'Tornado Warning' }),
};

const boil = (stage: string, directive: string): Record<string, State> => ({
  [STAGE]: s(stage, { severity: 4, driver: 'Boil Water Advisory' }),
  [DIRECTIVE]: s(directive),
  [QUIET]: s('off'),
});

const CASES: { title: string; states: Record<string, State> }[] = [
  // ---- tools/preview/main.tsx SCENARIOS ---------------------------------
  {
    title: 'preview: ELEVATED · Heat Advisory',
    states: {
      [STAGE]: s('elevated', {
        severity: 2, band: 'Elevated', driver: 'nws_union',
        detail: 'Heat Advisory issued September 2 at 3:29AM EDT until September 2 at 8:00PM EDT by NWS Greenville-Spartanburg SC',
      }),
      [DIRECTIVE]: s('none', { reason: 'no_directive_response', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Heat Advisory' }),
      'input_text.directive_alert_action': s('Something may be developing — stay reachable'),
    },
  },
  {
    title: 'preview: CRITICAL · Severe Thunderstorm Warning (directive suppressed)',
    states: {
      [STAGE]: s('critical', { severity: 5, driver: 'nws_union', detail: 'Severe Thunderstorm Warning until 6:00PM EDT' }),
      [DIRECTIVE]: s('none', { reason: 'suppressed_by_policy', suppressed: ['Severe Thunderstorm Warning -> Shelter'] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Severe Thunderstorm Warning' }),
    },
  },
  {
    title: 'preview: CRITICAL · Tornado Warning → SHELTER',
    states: {
      [STAGE]: s('critical', { severity: 7, driver: 'nws_union', detail: 'Tornado Warning until 3:15PM EDT' }),
      [DIRECTIVE]: s('shelter', { reason: 'cap_response', driver: 'Tornado Warning', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Tornado Warning' }),
    },
  },
  {
    title: 'preview: ELEVATED · Perimeter open, sustained',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'perimeter_open', detail: 'binary_sensor.front_door_sensor_door_sensor, cover.garage_door open over 300s' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [PERIM]: s('ok', {
        raw_state: '2 open of 8',
        detail: 'binary_sensor.front_door_sensor_door_sensor, cover.garage_door open over 300s',
      }),
      'binary_sensor.front_door_sensor_door_sensor': s('on', { friendly_name: 'Front Door Sensor' }),
      'cover.garage_door': s('open', { friendly_name: 'Garage Door' }),
    },
  },
  {
    title: 'preview: ELEVATED · Perimeter open — four doors, bounded',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'perimeter_open' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [PERIM]: s('ok', {
        raw_state: '4 open of 8',
        detail: 'binary_sensor.front_door_sensor_door_sensor, cover.garage_door, binary_sensor.rear_gate_sensor_intrusion, binary_sensor.lan_room_door_sensor_contact open over 300s',
      }),
      'binary_sensor.front_door_sensor_door_sensor': s('on', { friendly_name: 'Front Door Sensor' }),
      'cover.garage_door': s('open', { friendly_name: 'Garage Door' }),
      'binary_sensor.rear_gate_sensor_intrusion': s('on', { friendly_name: 'Rear Gate Sensor Intrusion' }),
      'binary_sensor.lan_room_door_sensor_contact': s('on', { friendly_name: 'LAN Room Door Sensor Contact' }),
    },
  },
  {
    title: 'preview: CRITICAL · Armed with a door open',
    states: {
      [STAGE]: s('critical', { severity: 6, driver: 'alarm' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [ALARM]: s('ok', { raw_state: 'armed_away', detail: 'alarm armed_away, open: binary_sensor.north_gate_sensor_intrusion' }),
      'binary_sensor.north_gate_sensor_intrusion': s('on', { friendly_name: 'North Gate Contact' }),
    },
  },
  {
    title: 'preview: ELEVATED · Wind Advisory, with QUIET on',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'nws_union', detail: 'Wind Advisory issued September 3 at 6:02AM EDT until September 3 at 8:00PM EDT by NWS Greenville-Spartanburg SC' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('on'),
      [NWS]: s('ok', { raw_state: 'Wind Advisory' }),
      'input_text.directive_quiet_imperative': s('Sleep Mode'),
      'input_text.directive_quiet_action': s('Keep it down upstairs'),
    },
  },
  {
    title: 'preview: ELEVATED · NTAS (the stutter case)',
    states: {
      [STAGE]: s('elevated', { severity: 3, driver: 'ntas' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      'sensor.household_state_ntas_advisory': s('ok', { raw_state: 'Elevated' }),
    },
  },
  {
    title: 'preview: UNAVAILABLE',
    states: {
      [STAGE]: s('unknown', { severity: null }),
      [DIRECTIVE]: s('unknown', { suppressed: [] }),
      [QUIET]: s('off'),
    },
  },
  {
    title: 'preview: ELEVATED · hazard unnamed (helper still owns the line)',
    states: {
      [STAGE]: s('elevated', { severity: 3, driver: 'some_future_source' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      'input_text.directive_alert_imperative': s('Be on alert'),
      'input_text.directive_alert_action': s('Something may be developing — stay reachable'),
    },
  },
  {
    title: 'preview: EVACUATE',
    states: {
      [STAGE]: s('critical', { severity: 7, driver: 'nws_union' }),
      [DIRECTIVE]: s('evacuate', { reason: 'cap_response', driver: 'Evacuation Immediate', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Evacuation Immediate' }),
    },
  },
  {
    title: 'preview header: cell=none',
    states: {
      [STAGE]: s('normal', { severity: 0 }),
      [DIRECTIVE]: s('none', { reason: 'no_directive_response', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Heat Advisory' }),
    },
  },
  {
    title: 'preview header: cell=quiet',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'nws_union', detail: 'Heat Advisory issued September 3 at 3:29AM EDT until September 3 at 8:00PM EDT by NWS Greenville-Spartanburg SC' }),
      [DIRECTIVE]: s('none', { reason: 'no_directive_response', suppressed: [] }),
      [QUIET]: s('on'),
      [NWS]: s('ok', { raw_state: 'Heat Advisory' }),
    },
  },
  // ---- .design-sync/previews/DirectiveBanner.tsx + EvacuateOverlay.tsx --
  {
    title: 'design-sync: Elevated',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'nws_union', detail: 'Heat Advisory issued September 9 at 3:29AM EDT until September 10 at 8:00PM EDT by NWS Greenville-Spartanburg SC' }),
      [DIRECTIVE]: s('none', { reason: 'no_directive_response', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Heat Advisory' }),
    },
  },
  {
    title: 'design-sync: SecureCells (elevated)',
    states: {
      [STAGE]: s('elevated', { severity: 3, driver: 'nws_union', detail: 'Law Enforcement Warning until 9:45PM' }),
      [DIRECTIVE]: s('secure', { reason: 'cap_response', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Law Enforcement Warning' }),
    },
  },
  {
    title: 'design-sync: SecureCells (critical)',
    states: {
      [STAGE]: s('critical', { severity: 6, driver: 'nws_union', detail: 'Civil Danger Warning until 11:00PM' }),
      [DIRECTIVE]: s('secure', { reason: 'cap_response', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Civil Danger Warning' }),
    },
  },
  {
    title: 'design-sync: ShelterCells (elevated)',
    states: {
      [STAGE]: s('elevated', { severity: 4, driver: 'nws_union', detail: 'Tornado Watch until 8:00PM EDT' }),
      [DIRECTIVE]: s('shelter', { reason: 'cap_response', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Tornado Watch' }),
    },
  },
  {
    title: 'design-sync: ShelterCells (critical)',
    states: {
      [STAGE]: s('critical', { severity: 7, driver: 'nws_union', detail: 'Tornado Warning until 3:15PM EDT' }),
      [DIRECTIVE]: s('shelter', { reason: 'cap_response', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Tornado Warning' }),
    },
  },
  {
    title: 'design-sync: QuietTint',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'nws_union', detail: 'Wind Advisory issued September 9 at 6:02AM EDT until September 10 at 8:00PM EDT by NWS Greenville-Spartanburg SC' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('on'),
      [NWS]: s('ok', { raw_state: 'Wind Advisory' }),
    },
  },
  {
    title: 'design-sync: Suppressed',
    states: {
      [STAGE]: s('critical', { severity: 5, driver: 'nws_union', detail: 'Severe Thunderstorm Warning until 6:00PM' }),
      [DIRECTIVE]: s('none', { reason: 'suppressed_by_policy', suppressed: ['Severe Thunderstorm Warning -> Shelter'] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Severe Thunderstorm Warning' }),
    },
  },
  {
    title: 'design-sync: Unavailable',
    states: {
      [STAGE]: s('unknown', { severity: null }),
      [DIRECTIVE]: s('unknown', { suppressed: [] }),
      [QUIET]: s('off'),
    },
  },
  {
    title: 'design-sync: Evacuate / HazardUnnamed',
    states: {
      [STAGE]: s('critical', { severity: 7 }),
      [DIRECTIVE]: s('evacuate', { reason: 'operator_override', suppressed: [] }),
      [QUIET]: s('off'),
    },
  },
  // ---- src/directive.test.ts fixtures ------------------------------------
  { title: 'test: HEAT_ADVISORY', states: HEAT_ADVISORY },
  { title: 'test: HEAT_ADVISORY quiet', states: { ...HEAT_ADVISORY, [QUIET]: s('on') } },
  {
    title: 'test: normal renders nothing',
    states: { [STAGE]: s('normal', { severity: 0, driver: null }), [DIRECTIVE]: s('none'), [QUIET]: s('off') },
  },
  {
    title: 'test: normal + quiet renders nothing',
    states: { [STAGE]: s('normal', { severity: 0, driver: null }), [DIRECTIVE]: s('none'), [QUIET]: s('on') },
  },
  {
    title: 'test: unheard-of stage word is unavailable',
    states: { [STAGE]: s('degraded', { severity: null }), [DIRECTIVE]: s('none'), [QUIET]: s('off') },
  },
  {
    title: 'test: helper owns the line when the hazard cannot be named',
    states: (() => {
      const { [NWS]: _dropped, ...rest } = HEAT_ADVISORY;
      return { ...rest, [STAGE]: s('elevated', { severity: 2, driver: 'ntas_gone' }) };
    })(),
  },
  {
    title: 'test: crit_none worded from the hazard',
    states: {
      [STAGE]: s('critical', { severity: 5, driver: 'nws_union', detail: 'STW until 6PM' }),
      [DIRECTIVE]: s('none', { reason: 'suppressed_by_policy', suppressed: ['Severe Thunderstorm Warning -> Shelter'] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Severe Thunderstorm Warning' }),
    },
  },
  { title: 'test: shelter keeps the house wording', states: SHELTER },
  {
    title: 'test: shelter helper override',
    states: { ...SHELTER, 'input_text.directive_crit_shelter_imperative': s('Everyone to the closet, now') },
  },
  {
    title: 'test: alarm triggered (no open list)',
    states: {
      [STAGE]: s('critical', { severity: 7, driver: 'alarm', detail: 'alarm triggered' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [ALARM]: s('ok', { raw_state: 'triggered', detail: 'alarm triggered' }),
    },
  },
  {
    title: 'test: perimeter names the doors',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'perimeter_open' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [PERIM]: s('ok', { raw_state: '2 open of 8', detail: 'binary_sensor.front_door_sensor_door_sensor, cover.garage_door open over 300s' }),
      'binary_sensor.front_door_sensor_door_sensor': s('on', { friendly_name: 'Front Door Sensor' }),
      'cover.garage_door': s('open', { friendly_name: 'Garage Door' }),
    },
  },
  {
    title: 'test: perimeter detail does not parse',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'perimeter_open' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [PERIM]: s('ok', { detail: 'something else entirely' }),
    },
  },
  {
    title: 'test: armed with the front door open',
    states: {
      [STAGE]: s('critical', { severity: 6, driver: 'alarm' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [ALARM]: s('ok', { raw_state: 'armed_away', detail: 'alarm armed_away, open: binary_sensor.front_door_sensor_door_sensor' }),
      'binary_sensor.front_door_sensor_door_sensor': s('on', { friendly_name: 'Front Door Sensor' }),
    },
  },
  {
    title: 'test: triggered, north gate tripped it',
    states: {
      [STAGE]: s('critical', { severity: 7, driver: 'alarm' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [ALARM]: s('ok', { raw_state: 'triggered', detail: 'alarm triggered, open: binary_sensor.north_gate_sensor_intrusion' }),
      'binary_sensor.north_gate_sensor_intrusion': s('on', { friendly_name: 'North Gate Contact' }),
    },
  },
  {
    title: 'test: armed, bare detail',
    states: {
      [STAGE]: s('critical', { severity: 6, driver: 'alarm' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [ALARM]: s('ok', { raw_state: 'armed_away', detail: 'alarm armed_away' }),
    },
  },
  {
    title: 'test: space weather',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'space_weather' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      'sensor.household_state_space_weather': s('ok', { raw_state: 'Storm (G1)' }),
    },
  },
  {
    title: 'test: unmapped weather event',
    states: {
      [STAGE]: s('elevated', { severity: 1, driver: 'nws_union' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Rip Current Statement' }),
    },
  },
  {
    title: 'test: quiet never tints a critical',
    states: {
      [STAGE]: s('critical', { severity: 5, driver: 'nws_union' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('on'),
      [NWS]: s('ok', { raw_state: 'Severe Thunderstorm Warning' }),
    },
  },
  {
    title: 'test: evacuate keeps its fixed imperative',
    states: {
      [STAGE]: s('critical', { severity: 7, driver: 'nws_union' }),
      [DIRECTIVE]: s('evacuate', { driver: 'Evacuation Immediate', suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Evacuation Immediate' }),
    },
  },
  {
    title: 'test: perimeter tagged by name, not tally',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'perimeter_open', detail: 'binary_sensor.drop_zone_door_contact open over 300s' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [PERIM]: s('ok', { raw_state: '1 open of 14', detail: 'binary_sensor.drop_zone_door_contact open over 300s' }),
      'binary_sensor.drop_zone_door_contact': s('on', { friendly_name: 'Drop Zone Door Sensor' }),
    },
  },
  {
    title: 'test: headline that is only the name',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'nws_union', detail: 'Heat Advisory' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [NWS]: s('ok', { raw_state: 'Heat Advisory' }),
    },
  },
  {
    title: 'test: critical shelter with quiet on',
    states: {
      [STAGE]: s('critical', { severity: 7, driver: 'nws_union' }),
      [DIRECTIVE]: s('shelter', { suppressed: [] }),
      [QUIET]: s('on'),
    },
  },
  {
    title: 'test: NTAS stutter',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'ntas' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      'sensor.household_state_ntas_advisory': s('ok', { raw_state: 'Elevated' }),
    },
  },
  {
    title: 'test: perimeter stutter (no friendly name)',
    states: {
      [STAGE]: s('elevated', { severity: 2, driver: 'perimeter_open' }),
      [DIRECTIVE]: s('none', { suppressed: [] }),
      [QUIET]: s('off'),
      [PERIM]: s('ok', { raw_state: '1 open of 14', detail: 'binary_sensor.drop_zone_door_contact open over 300s' }),
    },
  },
  { title: 'test: boil_water elevated', states: boil('elevated', 'boil_water') },
  { title: 'test: boil_water critical', states: boil('critical', 'boil_water') },
  { title: 'test: boil vs shelter elevated', states: boil('elevated', 'shelter') },
  { title: 'test: boil vs shelter critical', states: boil('critical', 'shelter') },
  { title: 'test: boil vs evacuate elevated', states: boil('elevated', 'evacuate') },
  { title: 'test: boil vs evacuate normal', states: boil('normal', 'evacuate') },
  { title: 'test: boil none elevated', states: boil('elevated', 'none') },
  { title: 'test: boil none critical', states: boil('critical', 'none') },
  { title: 'test: boil unknown directive', states: boil('elevated', 'unknown') },
];

it('records what the kit renders for every state map', () => {
  const kitCommit = execSync('git rev-parse HEAD').toString().trim();
  const cases = CASES.map(({ title, states }) => {
    const d = directiveNow(hass(states));
    return {
      title,
      states,
      expected: {
        cell: d.cell,
        imperative: d.imperative,
        action: d.action,
        tone: d.rag,
        evacuate: d.evacuate,
        stage_word: d.stage.word,
        stage_on: d.stage.on,
        stage_tone: d.stageRag,
        quiet: d.quiet,
        hazard_source: d.hazard.driverLabel,
        hazard_name: d.hazard.name,
        hazard_window: d.hazard.window,
        status: statusParts(d),
      },
    };
  });
  const out = process.env.OUT ?? 'banner_parity.json';
  writeFileSync(out, JSON.stringify({ kit_commit: kitCommit, generator: 'tools/banner_parity_fixture.ts', cases }, null, 2) + '\n');
});
