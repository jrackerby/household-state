"""Config flow. Single entry — there is one household."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    BINDABLE,
    BINDABLE_TEXT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MACRO_DEFAULT_ON_STATE,
    MACRO_RENAMEABLE_FIELDS,
    MACRO_SLUG_MAX,
    OPT_MACROS,
    RESERVED_MACRO_SLUGS,
    bind_key,
    macro_slugify,
    macros_from_options,
    slug_bindings,
)


class HouseholdStateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Household State", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HouseholdStateOptionsFlow()


class HouseholdStateOptionsFlow(config_entries.OptionsFlow):
    """Poll interval, source bindings (#16), and custom macro states.

    THE MERGE TRAP, AND WHY IT IS STRUCTURALLY CLOSED HERE. This flow used to
    be one step, deliberately, because `async_create_entry(data=...)` REPLACES
    entry.options wholesale: a multi-step flow whose second step returns only
    its own fields silently deletes every option the first step owns, and the
    deletion is invisible until an installation reboots into unbound sources.
    Macro states cannot live in the bindings form — there are already thirty-odd
    fields in it and a macro is a row, not a field — so the flow is now a menu
    and the trap had to be closed rather than avoided.

    It is closed in ONE place: NOTHING IN THIS CLASS CALLS async_create_entry.
    Every terminal step returns `self._save(changes)`, which merges over the
    live entry options and writes the complete set. A step added later that
    reaches for async_create_entry directly is the bug; the round-trip tests in
    tests/test_bindings.py and tests/test_config_flow.py are what go red.

    EVERY OPERATION SAVES AND ENDS THE FLOW, rather than accumulating edits
    behind a final "done". Options only persist on create_entry, so an
    accumulating flow loses the whole batch if the dialog is dismissed — and
    ending the flow reloads the entry, which is what makes a newly defined
    macro's entity appear immediately instead of after the next restart.
    """

    # Set only while the edit form is being shown; see async_step_macro_edit.
    _editing = None

    # --------------------------------------------------------------- saving

    def _save(self, changes: dict):
        """Write `changes` MERGED OVER the entry's current options.

        The single write path. See the class docstring for why there is
        exactly one.
        """
        merged = dict(self.config_entry.options)
        merged.update(changes)
        return self.async_create_entry(title="", data=merged)

    def _macros(self) -> list:
        """The macro states as stored, normalised."""
        return [dict(m) for m in macros_from_options(self.config_entry.options)]

    # ----------------------------------------------------------------- menu

    async def async_step_init(self, user_input=None):
        """The menu. `macro_edit` and `macro_remove` are offered only when
        there is something to edit or remove — a menu entry that leads to an
        empty picker is a dead end the user has to discover by clicking it."""
        menu = ["bindings", "macro_add"]
        if self._macros():
            menu += ["macro_edit", "macro_remove"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    # ------------------------------------------------------------- bindings

    async def async_step_bindings(self, user_input=None):
        """Poll interval, plus which entity supplies each source (#16)."""
        if user_input is not None:
            return self._save(user_input)

        options = self.config_entry.options
        schema = {
            vol.Optional(
                "scan_interval",
                default=options.get("scan_interval", DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300))
        }

        # Bindings are OPTIONAL and default to whatever is already set. An
        # unset binding falls through to the SOURCES row's own default in the
        # coordinator, so leaving the whole form alone changes nothing.
        for source_key, field, _domain, label in BINDABLE:
            key = bind_key(source_key, field)
            schema[vol.Optional(key, description={"suggested_value": options.get(key)})] = str
        for source_key, field, label in BINDABLE_TEXT + slug_bindings():
            key = bind_key(source_key, field)
            schema[vol.Optional(key, description={"suggested_value": options.get(key)})] = str

        return self.async_show_form(step_id="bindings", data_schema=vol.Schema(schema))

    # --------------------------------------------------------- macro states

    def _macro_schema(self, current=None):
        """The add/edit form. ONE schema for both, so the two forms cannot
        drift apart into a field the add step accepts and the edit step
        silently drops.

        NO SLUG FIELD, IN EITHER. The slug is derived from the name once, at
        creation, and frozen (const.py, MACRO_RENAMEABLE_FIELDS): it is the
        tail of the published entity id and Home Assistant never reclaims one.

        Plain `str` fields rather than selectors, matching the bindings form
        above. The domain a macro reads is not fixed — a macro may mirror an
        input_boolean, a schedule, a person or a select — so there is no one
        domain to hand an entity selector, and a selector that offers every
        entity in the installation is a longer list than a text box.
        """
        current = current or {}
        schema = {
            vol.Required(
                "name", description={"suggested_value": current.get("name")}
            ): str
        }
        schema[
            vol.Required(
                "entity_id",
                description={"suggested_value": current.get("entity_id")},
            )
        ] = str
        schema[
            vol.Optional(
                "on_state",
                default=current.get("on_state", MACRO_DEFAULT_ON_STATE),
            )
        ] = str
        schema[
            vol.Optional(
                "icon", description={"suggested_value": current.get("icon")}
            )
        ] = str
        # #30. The one field here that changes what a WALL does rather than
        # what this macro publishes: while a macro with this set is on, the
        # banner states nothing but an evacuation. Default off — every macro
        # defined before this field existed masks nothing.
        schema[
            vol.Optional("masks", default=bool(current.get("masks")))
        ] = bool
        return vol.Schema(schema)

    @staticmethod
    def _macro_fields(user_input: dict) -> dict:
        """The editable fields, trimmed.

        Read off MACRO_RENAMEABLE_FIELDS rather than named here, so const.py
        holds the one list of what an edit may change — and `slug` stays off it
        by construction rather than by both files remembering.

        BLANK IS NOT A VALUE. A cleared text box arrives as "", and storing it
        would define a macro whose `on_state` is the empty string — a macro
        that can never be true, on a form that looks filled in.
        """
        fields = {}
        for key in MACRO_RENAMEABLE_FIELDS:
            value = user_input.get(key)
            fields[key] = value.strip() if isinstance(value, str) else value
        fields["on_state"] = fields["on_state"] or MACRO_DEFAULT_ON_STATE
        fields["icon"] = fields["icon"] or None
        # A checkbox arrives as a bool; anything else (an absent field on a
        # hand-built call) is off, never truthy-by-accident.
        fields["masks"] = fields.get("masks") is True
        return fields

    async def async_step_macro_add(self, user_input=None):
        """Define a new macro state.

        The slug is derived from the name HERE, once, and then never again.
        """
        errors = {}
        if user_input is not None:
            fields = self._macro_fields(user_input)
            slug = macro_slugify(fields["name"])
            if not slug:
                # A name of nothing but punctuation slugifies to "", and an
                # entity id cannot be built from it. Named rather than
                # silently repaired: the name is the thing the user sees on
                # every dashboard, so this repo does not pick one for them.
                errors["base"] = "invalid_name"
            elif slug in RESERVED_MACRO_SLUGS:
                errors["base"] = "reserved_name"
            elif any(m["slug"] == slug for m in self._macros()):
                errors["base"] = "duplicate_name"
            elif not fields["entity_id"]:
                errors["base"] = "entity_required"
            else:
                macros = self._macros()
                macros.append({"slug": slug, **fields})
                return self._save({OPT_MACROS: macros})

        return self.async_show_form(
            step_id="macro_add",
            data_schema=self._macro_schema(user_input),
            errors=errors,
            description_placeholders={"max": str(MACRO_SLUG_MAX)},
        )

    async def async_step_macro_edit(self, user_input=None):
        """Pick which macro to edit, then hand off to the detail form."""
        macros = self._macros()
        if not macros:
            return await self.async_step_init()
        if user_input is not None:
            self._editing = user_input["slug"]
            return await self.async_step_macro_detail()
        return self.async_show_form(
            step_id="macro_edit",
            data_schema=vol.Schema(
                {vol.Required("slug"): vol.In({m["slug"]: m["name"] for m in macros})}
            ),
        )

    async def async_step_macro_detail(self, user_input=None):
        """Edit one macro. The slug is not offered — see const.py.

        A rename here changes the friendly name and NOT the published entity
        id: Home Assistant fixes an entity id at first registration and never
        moves it on a rename, which is the behaviour this design wants rather
        than one it works around.
        """
        macros = self._macros()
        current = next((m for m in macros if m["slug"] == self._editing), None)
        if current is None:
            # The entry was reconfigured in another window between the picker
            # and this form. Back to the menu rather than writing a macro with
            # a slug that no longer exists.
            return await self.async_step_init()

        errors = {}
        if user_input is not None:
            fields = self._macro_fields(user_input)
            if not fields["entity_id"]:
                errors["base"] = "entity_required"
            elif not fields["name"]:
                errors["base"] = "invalid_name"
            else:
                updated = [
                    {"slug": m["slug"], **fields} if m["slug"] == self._editing else m
                    for m in macros
                ]
                return self._save({OPT_MACROS: updated})

        return self.async_show_form(
            step_id="macro_detail",
            data_schema=self._macro_schema(user_input or current),
            errors=errors,
            description_placeholders={
                "slug": current["slug"],
                "name": current["name"],
            },
        )

    async def async_step_macro_remove(self, user_input=None):
        """Delete a macro state, with a confirmation.

        CONFIRMED BECAUSE IT IS A DELETION OF A PUBLISHED ENTITY, not because
        the form is hard to use. Every dashboard card, automation trigger and
        template reading `binary_sensor.household_state_<slug>` stops resolving
        the moment this is saved — __init__.py removes the registry row so the
        id is not left behind as a permanently unavailable ghost, and that is
        the half that cannot be undone by re-adding the macro.
        """
        macros = self._macros()
        if not macros:
            return await self.async_step_init()

        errors = {}
        if user_input is not None:
            if not user_input.get("confirm"):
                errors["base"] = "not_confirmed"
            else:
                slug = user_input["slug"]
                return self._save(
                    {OPT_MACROS: [m for m in macros if m["slug"] != slug]}
                )

        return self.async_show_form(
            step_id="macro_remove",
            data_schema=vol.Schema(
                {
                    vol.Required("slug"): vol.In(
                        {m["slug"]: m["name"] for m in macros}
                    ),
                    vol.Required("confirm", default=False): bool,
                }
            ),
            errors=errors,
        )
