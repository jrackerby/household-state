# Migrating from `input_boolean` helpers

A household that has been automated for a while accumulates a layer of named
modes: `input_boolean.guest_mode`, `input_boolean.vacation`,
`input_boolean.sleep_mode`, `input_boolean.wfh`. Each one is a helper somebody
toggles, and around each one grows a small pile of template sensors, condition
shorthands and dashboard cards that read it.

**Macro states replace the pile, not the helper.** This page shows what moves,
what stays, and what deliberately does not come with it.

## What a macro state is

A named household modifier — `Guest`, `Vacation`, `Away` — resolved from an
entity you already have and published as
`binary_sensor.household_state_<name>` on the Household State device.

`binary_sensor.household_state_quiet` has worked this way since 0.5.0: it is a
read-only mirror of a sleep-mode helper, published beside the axes so a
dashboard has one place to read *is the house asleep* instead of reaching into
`input_boolean.sleep_mode` directly. A macro state is that arrangement with the
source and the name moved into the options flow, so a second modifier is a form
rather than a release.

### It is read-only, and that is the point

Defining a macro state creates **no helper and nothing writable**. It names an
entity and a state string, and republishes what that entity says.

- Nothing on the Household State device can be turned on from a dashboard,
  because nothing here owns the fact — the bound entity does.
- If you want something a person can flip, you still want an `input_boolean`.
  Keep it.
- What you stop needing is the template layer **on top** of that helper.

### It moves no axis

A macro state carries no severity. It is not in the stage ramp, not in
`sources_total`, not in `confidence`, and it cannot make
`binary_sensor.household_state_feed_health` report a problem. Guest mode is not
a hazard, and a household that could raise its own stage from a form would have
a ramp that no longer means what `const.py` says it means.

If a modifier genuinely *should* move an axis, that is a `SOURCES` row and a
ruling about what it is worth — not a config change.

## The arrangement this replaces

A typical `configuration.yaml`, for two modes:

```yaml
input_boolean:
  guest_mode:
    name: Guest Mode
    icon: mdi:account-group
  vacation:
    name: Vacation
    icon: mdi:bag-suitcase

template:
  - binary_sensor:
      - name: Household Guest Mode
        state: "{{ is_state('input_boolean.guest_mode', 'on') }}"
        icon: mdi:account-group
      - name: Household Vacation
        state: "{{ is_state('input_boolean.vacation', 'on') }}"
        icon: mdi:bag-suitcase
      - name: Household Away
        state: "{{ is_state('person.sam', 'not_home') and is_state('person.alex', 'not_home') }}"
```

Three things are wrong with it, and they are the same three this integration
was built to refuse.

**`is_state()` returns `false` for a source it cannot read.** If
`input_boolean.guest_mode` is deleted, renamed, or not yet restored during a
restart, `is_state(...)` is `false` and the template sensor publishes `off` —
a positive claim that the household is *not* in guest mode, manufactured out of
an absence. Nothing distinguishes it from a genuine `off`.

**Every mode is a copy of the same block.** Adding a fourth means editing YAML,
reloading templates, and finding out afterwards whether the entity id you
picked collided with one that already existed.

**The name and the id drift.** Renaming `Household Guest Mode` in the UI leaves
`binary_sensor.household_guest_mode` behind; renaming it in YAML mints a new
entity and orphans the old one, because Home Assistant never reclaims an id.

## The migration

### 1. Define the macro state

*Settings → Devices & Services → Household State → Configure → Define a macro
state.*

| field | for the example above |
|---|---|
| **Name** | `Guest` |
| **Entity to read** | `input_boolean.guest_mode` |
| **State that means on** | `on` |
| **Icon** | `mdi:account-group` |

Saving reloads the entry and `binary_sensor.household_state_guest` appears
immediately.

**The name sets the entity id, once.** `Guest` becomes
`binary_sensor.household_state_guest` and that id is frozen: the edit form will
not offer it again. Renaming the macro later changes the friendly name and
nothing else, so nothing reading the id breaks. Pick the name you want in the
id — it is the only irreversible field on the form.

Two names are refused, because the integration already publishes them:
`Quiet` and `Feed health`. So are `Stage`, `Directive` and `Integrity` — those
are sensors rather than binary sensors, so there is no id collision, but a
`binary_sensor.household_state_stage` sitting beside
`sensor.household_state_stage` and answering a different question is a trap for
whoever reads the dashboard next.

### 2. Point the consumers at the new entity

```yaml
# before
{{ is_state('binary_sensor.household_guest_mode', 'on') }}
# after
{{ is_state('binary_sensor.household_state_guest', 'on') }}
```

Do this before step 3. A template sensor you have already deleted is one you
cannot diff against.

### 3. Delete the template sensor — and only the template sensor

Remove the `template:` block. **Keep `input_boolean.guest_mode`**: it is what a
person toggles and what the macro state reads. Deleting it leaves the macro
reading an entity that no longer exists, which publishes `unknown` and says so
on the entity — loudly, which is the intended behaviour, but still not what you
meant.

Then delete the orphaned template entity row under *Settings → Devices &
Services → Entities*. Home Assistant does not reclaim it on its own.

### One macro reads one entity

A macro state matches one entity against one string. The `Household Away`
example above — every person `not_home` — is **not** one macro, and this is a
deliberate limit rather than an omission: a rollup over several entities is a
rule about what the household means by "away", and the form has nowhere honest
to record what happens when two of the five are unreadable.

Keep those as what they already are. A [`group`](https://www.home-assistant.io/integrations/group/)
of the person entities, or a template binary sensor that states its own
handling of the unreadable case, then bind one macro to the result:

```yaml
group:
  everyone:
    entities: [person.sam, person.alex]
```

| macro | entity to read | state that means on |
|---|---|---|
| `Away` | `group.everyone` | `not_home` |

## What you get that the template did not do

### An unreadable source is `unknown`, never `off`

The whole reason to move. Compare the two on a deleted helper:

| | template sensor | macro state |
|---|---|---|
| helper deleted | `off` | `unknown` |
| helper `unavailable` | `off` | `unknown`, `disposition: unreachable` |
| helper restoring during a restart | `off` | `unknown`, `disposition: unknown` |
| helper genuinely off | `off` | `off`, `disposition: ok` |

A macro state publishes `None` — never `False` — when it cannot read its
source, exactly as `binary_sensor.household_state_quiet` has always done, and
exactly as every source on every axis does. An automation gated on
`is_state('binary_sensor.household_state_guest', 'off')` now genuinely means
*the household is not in guest mode*, rather than *the household is not in
guest mode, or I could not tell*.

To act only on a confident reading:

```yaml
condition:
  - condition: state
    entity_id: binary_sensor.household_state_guest
    state: "off"
  - condition: state
    entity_id: binary_sensor.household_state_guest
    attribute: disposition
    state: "ok"
```

The first condition alone is already safe — an unreadable macro is `unknown`,
which is not `off`, so it does not match. The second is for the case where you
want to distinguish *read it, and it is off* from *could not read it* in the
automation's own trace.

### It reads any entity, not just a helper

`on_state` is matched **exactly and case-sensitively** against the bound
entity's state, so the source does not have to be an `input_boolean` at all.
Several helpers exist only because a template sensor was the only way to give
something a name:

| macro | entity to read | state that means on |
|---|---|---|
| `Away` | `person.sam` | `not_home` |
| `Guest` | `schedule.guest_window` | `on` |
| `Vacation` | `calendar.travel` | `on` |
| `Cooking` | `input_select.kitchen_mode` | `Cooking` |
| `Quiet hours` | `binary_sensor.night` | `on` |

Case matters: an `input_select` reading `Cooking` does not match an `on_state`
of `cooking`. Both the state the entity reported and the state the macro was
watching for are published as attributes (`raw_state` and `on_state`), so a
macro stuck at `off` is diagnosable from the entity page without opening the
config entry.

A helper that exists only to be mirrored by a template sensor can usually be
deleted outright — bind the macro to the underlying entity instead. A helper a
person actually toggles stays.

### Deleting a macro takes its entity with it

Removing a macro state under *Configure → Delete a macro state* removes the
registry row too, rather than leaving a permanently unavailable entity holding
its id. The confirmation on that form is there because it is irreversible in
the direction that matters: anything still reading
`binary_sensor.household_state_<name>` stops resolving the moment it is saved.

Re-adding a macro with the same name therefore gets the same id back, instead
of landing on `_2`.

## What each macro publishes

```yaml
binary_sensor.household_state_guest:
  state: "on"
  attributes:
    slug: guest
    source_entity_id: input_boolean.guest_mode
    raw_state: "on"        # what the entity said
    on_state: "on"         # what this macro watches for
    disposition: ok        # ok | absent | unreachable | unknown
    since: "2026-09-11T02:00:00+00:00"
```

`since` is persisted rather than derived from `last_changed`, so it survives a
Home Assistant restart. `last_changed` resets to restart time for a restored
entity, which under-reports age — the direction that hides a problem.

## Should QUIET become a macro state?

No. `binary_sensor.household_state_quiet` already exists and is bound under
*Configure → Poll interval and source bindings → `quiet.entity_id`*. Re-minting
it as a macro would hand its published id to a different `unique_id` and orphan
every dashboard reading it, for no behavioural gain — a macro state and QUIET
resolve identically.

Leave it where it is. Define macro states for the modifiers QUIET does not
cover.
