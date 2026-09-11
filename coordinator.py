"""Coordinator — source reads, the fall dwell, and the persisted ages."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, label_registry as lr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    AXIS_DIRECTIVE,
    BIND_PERIMETER,
    BIND_QUIET,
    AXIS_INTEGRITY,
    AXIS_STAGE,
    CONFIG_ENTRY_DWELL,
    DISP_ABSENT,
    DISP_OK,
    DISP_UNKNOWN,
    DISP_UNPARSED,
    DISP_UNREACHABLE,
    FALL_DWELL,
    INTEGRITY_DEGRADED,
    INTEGRITY_OK,
    PERIMETER_DWELL,
    PERIMETER_LABEL,
    PERIMETER_OPEN_STATES,
    PERIMETER_SEV,
    QUIET_SOURCE_ENTITY,
    SLUG_FIELD,
    SOURCES,
    STORE_KEY,
    bind_key,
    STORE_VERSION,
)
from .resolver import alarm_severity, resolve

_LOGGER = logging.getLogger(__name__)

_BAD_STATES = ("unavailable", "unknown", "none", "")

# Condition tokens that mean SOMEBODY MUST EDIT SOMETHING, as opposed to a
# source that is merely unreadable right now. These log at WARNING; every
# other token logs at INFO, per the quality scale's log-when-unavailable.
_DEFECT_STATES = frozenset(
    {"missing", "label_absent", "label_empty", "unparsed", "registry_error",
     # #16. An unbound source needs somebody to fill in the options form.
     # Log level splits on WHO ACTS: nobody waits this out, so it is a
     # warning like every other condition that needs an edit — not the INFO
     # this integration uses when it is merely reporting on its own subject.
     "unbound"}
)


class HouseholdStateCoordinator(DataUpdateCoordinator):
    """Reads every source, resolves, holds falls, persists ages.

    RULE 1: THIS COORDINATOR NEVER RAISES UpdateFailed. There is no
    `raise` anywhere in _async_update_data and there must not be one.
    Raising takes every entity unavailable, and attributes on an
    unavailable entity vanish — which is the exact mechanism by which a
    broken collector comes to read green.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        scan_interval: int,
        bindings: dict | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="household_state",
            update_interval=timedelta(seconds=scan_interval),
        )
        # #16. Which entity supplies a source is CONFIGURATION; the SOURCES
        # row supplies the default. Resolved through _bound() at every read
        # rather than baked into the spec at setup, so a reconfigure reaches
        # the next poll without a reload having to rebuild the row.
        self._bindings = dict(bindings or {})
        self._store = Store(hass, STORE_VERSION, STORE_KEY)
        self._ages: dict = {}
        self._ages_loaded = False
        # Fall-dwell state. RULE 3.
        self._held_severity = None
        self._held_since = None
        self._warned: dict = {}
        # Armed by async_at_started; see async_arm_logging.
        self._log_armed = False

    def _bound(self, source_key: str, field: str, default=None):
        """The configured value for one binding, or the row's own default.

        An EMPTY configured value is treated as unset, not as a deliberate
        blank: an options flow hands back "" for a field the user cleared, and
        reading that as an entity id would turn a cleared field into a lookup
        for the entity named "", which reports `absent` and looks exactly like
        a deleted entity. Those must not collapse.
        """
        value = self._bindings.get(bind_key(source_key, field))
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return value

    def _spec_entity(self, spec: dict):
        """The entity a SOURCES row reads, after binding."""
        return self._bound(spec["key"], "entity_id", spec.get("entity_id"))

    def slug_for(self, spec: dict) -> str:
        """The row's PUBLISHED identity: the tail of its entity's unique_id and
        the token the stage sensor names as its driver.

        Defaults to the key. Bindable because renaming a key would otherwise
        mint a new entity and orphan the one an installation already publishes
        (#19) — HA never reclaims an id, so the rename would be visible on
        every dashboard reading the old one.
        """
        return self._bound(spec["key"], SLUG_FIELD, spec["key"])

    async def async_load_ages(self) -> None:
        """RULE 5. Must run BEFORE the first refresh, or every age
        clock restarts at zero on every HA restart — which under-reports
        age, the direction that hides the problem."""
        data = await self._store.async_load()
        self._ages = data or {}
        self._ages_loaded = True

    async def _save_ages(self) -> None:
        await self._store.async_save(self._ages)

    def _mark(self, key: str, value) -> str | None:
        """Persist the moment `key` last took a new value; return it."""
        row = self._ages.get(key)
        now = dt_util.utcnow().isoformat()
        if row is None or row.get("value") != value:
            self._ages[key] = {"value": value, "since": now}
            return now
        return row.get("since")

    @callback
    def async_arm_logging(self, _hass: HomeAssistant | None = None) -> None:
        """Start logging source conditions. Called from async_at_started.

        Until HA reaches RUNNING, every source this integration reads is
        expected to be blind: the registry restores an entity row long
        before the integration that owns it has published a state, so the
        first polls see `st is None` for perimeter contacts and source
        sensors that are merely still starting. Logging that is noise
        about HA's boot, not about the installation.

        Only the LOGGING is gated. The readings themselves are unchanged
        and still publish `absent` / `unknown` on the entity attributes
        throughout startup — collapsing those into `ok` is the dead-feed-reads-green defect and is
        exactly what this integration exists to refuse.
        """
        self._log_armed = True

    def _warn_once(self, key: str, state: str, detail: str = "") -> None:
        """Log a source condition ONCE at the crossing and once on recovery.

        HA quality scale, `log-when-unavailable`: log once in total, and
        once again on recovery, at INFO level. A source that cannot be
        read is not an integration error — it is this integration's whole
        output, already published on the entity attributes every surface
        reads. A WARNING per poll duplicates that and buries the one class
        that is not routine.

        TWO ARGUMENTS, NOT ONE, AND THIS IS THE FIX. `state` is a stable
        condition token and is the ONLY thing compared; `detail` is the
        human sentence and is never compared. Deduping on the message
        itself is not deduping: the perimeter message carries a count and
        a member list, so "4 unreadable" and "1 unreadable"
        were different strings and each re-fired a warning while the
        condition never changed. The live count belongs on the entity,
        which is where a dashboard reads it, not in a repeated log line.

        `_DEFECT_STATES` is the exception the rule leaves room for: a
        source entity that does not exist, a label that does not resolve,
        an attribute that will not parse. Nobody waits those out — somebody
        has to edit something — so they stay WARNING.
        """
        if not self._log_armed:
            # Deliberately records nothing: a state recorded while silent
            # would read as already-reported once armed, and a genuinely
            # missing source would then never log at all.
            return
        prev = self._warned.get(key)
        if prev == state:
            return
        self._warned[key] = state
        if state:
            _log = _LOGGER.warning if state in _DEFECT_STATES else _LOGGER.info
            _log("household_state: %s", detail or state)
        elif prev:
            # `elif prev`, never a bare `else`: on the first poll every
            # healthy source arrives here with prev None, and announcing a
            # recovery from a fault that never happened is a false reading
            # in the direction that trains an operator to ignore the log.
            _LOGGER.info("household_state: %s recovered", key)

    def _read_source(self, spec: dict) -> dict:
        """One source -> one reading. NEVER returns severity 0 for a
        source it could not read. That substitution is the dead-feed-reads-green defect."""
        eid = self._spec_entity(spec)
        base = {
            "key": spec["key"],
            "slug": self.slug_for(spec),
            "name": spec["name"],
            "entity_id": eid,
            "axis": spec["axis"],
            "kind": spec["kind"],
            "severity": None,
            "raw_state": None,
            "detail": None,
            "disposition": DISP_ABSENT,
        }

        if eid is None and spec["kind"] not in ("perimeter", "config_entries",
                                                "notify_health"):
            # #16. "You have not told me where to look" is a different fact
            # from "the entity you named is gone" (absent and
            # unreachable do not collapse, and neither do these). Both are
            # ABSENT on the axis — an unbound source must never read as a
            # quiet zero — but the detail and the log token differ, because
            # only one of them is fixed by editing the entity and the other by
            # filling in the options form. The three kinds excluded here read
            # no entity of their own and report their own unbound state below.
            base["detail"] = "not configured: bind " + spec["key"] + ".entity_id"
            self._warn_once(
                spec["key"], "unbound",
                spec["key"] + " has no entity bound (Configure -> "
                + spec["key"] + ".entity_id)",
            )
            return base

        if spec["kind"] == "perimeter":
            # The one row with no entity_id. Dispatched before the state
            # lookup, because there is nothing to look up.
            return self._read_perimeter(spec, base)

        if spec["kind"] == "config_entries":
            return self._read_config_entries(spec, base)

        if spec["kind"] == "notify_health":
            return self._read_notify_health(spec, base)

        st = self.hass.states.get(eid)
        if st is None:
            # The never-set-up-source defect lives here: an entity never set up is a
            # different fact from an entity reporting all clear.
            self._warn_once(
                spec["key"], "missing", eid + " does not exist (never set up?)"
            )
            return base

        base["raw_state"] = st.state
        if st.state == "unavailable":
            base["disposition"] = DISP_UNREACHABLE
            self._warn_once(spec["key"], "unavailable", eid + " is unavailable")
            return base
        if st.state in ("unknown", ""):
            base["disposition"] = DISP_UNKNOWN
            self._warn_once(spec["key"], "unknown", eid + " is unknown")
            return base

        self._warn_once(spec["key"], "")

        if spec["kind"] == "alarm":
            open_sensors = st.attributes.get("open_sensors")
            base["severity"] = alarm_severity(st.state, open_sensors)
            base["detail"] = "alarm " + str(st.state)
            # THE SENSORS ALARMO ALREADY NAMED. `open_sensors` is what
            # promotes this row to sev 6 in the first place (alarm_severity
            # above reads the same value), and on `triggered` it is the zone
            # that tripped -- so the row scored itself on a fact it then
            # discarded, and the wall said "armed with something open" while
            # holding the answer. The unnamed-opening defect, the same one as the perimeter
            # row above and fixed the same way.
            #
            # Alarmo publishes a dict keyed by entity_id; the list form is
            # accepted too rather than asserted against, because being wrong
            # about the shape here would cost the name and the severity is
            # computed from the same value either way.
            ids = []
            if isinstance(open_sensors, dict):
                ids = sorted(open_sensors)
            elif isinstance(open_sensors, (list, tuple, set)):
                ids = sorted(str(x) for x in open_sensors)
            if ids:
                base["detail"] += ", open: " + ", ".join(ids)
            base["disposition"] = DISP_OK
            return base

        if spec["kind"] == "binary_hazard":
            # A binary_sensor whose `on` IS the hazard. No scale to read.
            #
            # Deliberately strict about what counts as off: only the literal
            # "off" resolves to severity 0. Anything else that reached here
            # is a state this row does not understand, and guessing `clear`
            # for it is the dead-feed-reads-green substitution in a new coat. (unavailable,
            # unknown and missing were already handled above and never get
            # this far.)
            if st.state == "on":
                base["severity"] = spec["severity_when_on"]
                base["detail"] = spec["name"] + " in effect for this address"
            elif st.state == "off":
                base["severity"] = 0
                base["detail"] = "no " + spec["name"].lower() + " for this address"
            else:
                base["disposition"] = DISP_UNPARSED
                base["detail"] = "unrecognised binary state: " + str(st.state)
                return base
            base["disposition"] = DISP_OK
            return base

        if spec["kind"] == "cap":
            # RAW PAIRS ONLY — the vocabulary map and the
            # suppression policy are in resolver.py, where they can be
            # exercised without moving the real world.
            pairs = st.attributes.get(spec["pairs_attr"])
            if pairs is None:
                # The entity answered but the attribute is not there:
                # a template that failed to render, not a dead feed.
                base["disposition"] = DISP_UNPARSED
                base["detail"] = spec["pairs_attr"] + " attribute absent"
                self._warn_once(
                    spec["key"],
                    "unparsed",
                    eid + " has no " + spec["pairs_attr"] + " attribute",
                )
                return base
            if not isinstance(pairs, (list, tuple)):
                base["disposition"] = DISP_UNPARSED
                base["detail"] = "cap pairs did not parse as a list"
                self._warn_once(
                spec["key"], "unparsed", eid + " cap pairs did not parse as a list"
            )
                return base
            base["disposition"] = DISP_OK
            base["pairs"] = [p for p in pairs if isinstance(p, dict)]
            base["detail"] = str(len(base["pairs"])) + " active alert(s) carrying CAP"
            self._warn_once(spec["key"], "")
            return base

        if spec["kind"] == "fls":
            # RULE 6. Integrity axis only — the severity
            # attribute on this entity is deliberately NOT read.
            #
            # THE ATTRIBUTE TRIPLE COMES OFF THE REGISTRY ROW, not off a
            # name hardcoded here. The integrity axis has always specified
            # two sources on this entity — device liveness and perimeter
            # tamper — and 0.1.0 read tamper_integrity into a key that
            # nothing downstream consumed. A value read and dropped is
            # indistinguishable from a value never read.
            base["disposition"] = DISP_OK
            base["integrity"] = st.attributes.get(spec["integrity_attr"])
            base["integrity_detail"] = st.attributes.get(spec["detail_attr"])
            base["affected"] = st.attributes.get(spec["affected_attr"]) or 0
            base["detail"] = base["integrity_detail"]
            # CARRY WHICH ATTRIBUTE WAS READ, not just which
            # entity. Two rows deliberately share sensor.fls_device_status
            # and are distinguished only by their triple. With `entity_id`
            # alone on the reading, the two per-source entities were
            # indistinguishable on glass and got reported as one row
            # duplicated onto another's subject. The binding was correct;
            # it was unreadable. Naming the attribute here is what makes
            # that checkable without opening const.py.
            base["integrity_attr"] = spec["integrity_attr"]
            return base

        # severity_attr
        raw = st.attributes.get("severity")
        try:
            base["severity"] = int(raw)
        except (TypeError, ValueError):
            # The state-disagrees-with-severity shape: the entity answered and the severity did
            # not parse. That is NOT zero and it is NOT unavailable.
            base["disposition"] = DISP_UNPARSED
            base["detail"] = "severity did not parse: " + str(raw)
            return base

        base["disposition"] = DISP_OK
        base["detail"] = st.attributes.get("headline") or st.state
        return base

    def _read_quiet(self) -> dict:
        """0.5.0. QUIET's one source, read-only — see const.py's module
        docstring. Guards unknown/unavailable/missing the same way every
        other read in this file does: `quiet` is None, never False, when
        the source cannot be read, so an unreadable sleep_mode never
        silently claims the house is NOT quiet."""
        quiet_entity = self._bound(BIND_QUIET, "entity_id", QUIET_SOURCE_ENTITY)
        base = {
            "quiet": None,
            "quiet_source_entity_id": quiet_entity,
            "quiet_raw_state": None,
        }
        if quiet_entity is None:
            self._warn_once(
                "quiet", "unbound",
                "QUIET has no entity bound (Configure -> quiet.entity_id)",
            )
            return base
        st = self.hass.states.get(quiet_entity)
        if st is None:
            self._warn_once(
                "quiet",
                "missing",
                quiet_entity + " does not exist (never set up?)",
            )
            return base
        base["quiet_raw_state"] = st.state
        if st.state in ("unavailable", "unknown", ""):
            self._warn_once(
                "quiet",
                st.state or "empty",
                quiet_entity + " is " + (st.state or "empty"),
            )
            return base
        self._warn_once("quiet", "")
        base["quiet"] = st.state == "on"
        return base

    def _perimeter_label(self) -> str:
        """The label whose members ARE the perimeter, after binding."""
        return self._bound(BIND_PERIMETER, "label", PERIMETER_LABEL)

    def _perimeter_entity_ids(self):
        """DISCOVER, DON'T PIN — resolve the fls_device label at runtime.

        Returns None when the label itself cannot be resolved, which is
        `absent` and NOT an empty perimeter. The two must not collapse:
        one is a config defect, the other is a house with no doors.

        The registry call is guarded because RULE 1 admits no exception.
        A label-registry API that moves under a core upgrade would
        otherwise raise inside _async_update_data, take every entity
        unavailable, and take their attributes with them — which is the
        exact mechanism this integration exists to refuse.
        """
        try:
            wanted = self._perimeter_label()
            if wanted is None:
                return None
            lreg = lr.async_get(self.hass)
            label = lreg.async_get_label(wanted)
            if label is None:
                label = lreg.async_get_label_by_name(wanted)
            if label is None:
                return None
            ereg = er.async_get(self.hass)
            return sorted(
                e.entity_id
                for e in er.async_entries_for_label(ereg, label.label_id)
                if e.entity_id.split(".")[0] in PERIMETER_OPEN_STATES
            )
        except Exception as exc:  # noqa: BLE001 — RULE 1
            self._warn_once(
                "perimeter_registry",
                "registry_error",
                "perimeter label lookup failed: " + str(exc),
            )
            return None

    def _read_perimeter(self, spec, base):
        """"Perimeter Open, Sustained" — severity 2 after a 5-minute dwell.

        THREE THINGS DIFFER FROM THE YAML THIS REPLACED, ON PURPOSE.

        1. THE DWELL IS MEASURED FROM A PERSISTED OPEN-SINCE, not from
           `last_changed` (RULE 5, Home Assistant's restored-entity behaviour). HA resets
           `last_changed` to restart time for every restored entity, so
           the template version cannot fire for five minutes after any
           restart and under-reports age — the direction that hides the
           problem.
        2. A MEMBER THAT IS MISSING OR UNREADABLE MAKES THIS SOURCE
           `unknown`, NOT CLOSED. The template's `is not none` guard
           fails permissive: a deleted contact reads as 'off', which is
           precisely how the front door and the drop zone went uncovered
           for weeks after a doorbell swap — the dead-feed-reads-green defect.
        3. A SUSTAINED OPEN STILL PUBLISHES sev 2 while other members
           are unreadable. A positive finding does not need complete
           visibility; only a negative one does.
        """
        label = self._perimeter_label()
        if label is None:
            base["detail"] = "not configured: bind perimeter.label"
            self._warn_once(
                spec["key"], "unbound",
                "perimeter has no label bound (Configure -> perimeter.label)",
            )
            return base
        ents = self._perimeter_entity_ids()
        if ents is None:
            base["disposition"] = DISP_ABSENT
            base["detail"] = "label " + label + " does not resolve"
            self._warn_once(
                spec["key"],
                "label_absent",
                "perimeter label " + label + " does not resolve",
            )
            return base
        if not ents:
            base["disposition"] = DISP_ABSENT
            base["detail"] = "no contacts or covers carry label " + label
            self._warn_once(
                spec["key"], "label_empty", "perimeter label resolves to zero members"
            )
            return base

        now = dt_util.utcnow()
        blind = []
        open_now = []
        sustained = []
        for eid in ents:
            st = self.hass.states.get(eid)
            if st is None or st.state in _BAD_STATES:
                blind.append(eid)
                continue
            # Marked only while readable: an unavailable stretch must not
            # overwrite the stored value and restart the clock on recovery.
            since = self._mark("perim:" + eid, st.state)
            if st.state != PERIMETER_OPEN_STATES[eid.split(".")[0]]:
                continue
            open_now.append(eid)
            started = dt_util.parse_datetime(since or "")
            if started is None:
                continue
            if (now - started).total_seconds() >= PERIMETER_DWELL:
                sustained.append(eid)

        base["raw_state"] = str(len(open_now)) + " open of " + str(len(ents))
        base["watched_count"] = len(ents)
        base["open_count"] = len(open_now)
        base["blind"] = blind

        if sustained:
            base["disposition"] = DISP_OK
            base["severity"] = PERIMETER_SEV
            # EVERY SUSTAINED MEMBER, NAMED. This used to publish
            # `sustained[0] + " +2 more"`, which made the other openings
            # unnameable at the render boundary no matter what the surface
            # did with the string -- and the surface is where a household
            # member reads it. Read off a wall: "'something is left open'
            # is silly. say which door is left open." the unnamed-opening defect.
            #
            # Comma-joined because an entity_id cannot contain a comma, so
            # the value is incapable of tearing its own delimiter;
            # the reader splits on it without an escape rule. Unbounded on
            # purpose -- this string is the diagnostic record and the glass
            # decides how many it has room to say, which is the render-
            # boundary split the surface already applies to every other
            # log-shaped detail on this axis.
            base["detail"] = (
                ", ".join(sustained) + " open over " + str(PERIMETER_DWELL) + "s"
            )
            self._warn_once(spec["key"], "")
            return base

        if blind:
            base["disposition"] = DISP_UNKNOWN
            base["detail"] = (
                "cannot confirm closed: "
                + str(len(blind))
                + " of "
                + str(len(ents))
                + " unreadable"
            )
            # "blind", never the count: the membership moves as contacts
            # come back and every move used to re-fire this line.
            self._warn_once(
                spec["key"],
                "blind",
                str(len(blind)) + " perimeter member(s) unreadable: " + ", ".join(blind),
            )
            return base

        base["disposition"] = DISP_OK
        base["severity"] = 0
        base["detail"] = "all " + str(len(ents)) + " perimeter members closed"
        self._warn_once(spec["key"], "")
        return base

    def _entry_unavailable_ratio(self, entry_id):
        """(unavailable, total) owned entities for one config entry.

        total==0 is vacuously healthy, never a finding — an integration
        that creates no entities is not this row's business.
        """
        ereg = er.async_get(self.hass)
        total = 0
        unavailable = 0
        for e in er.async_entries_for_config_entry(ereg, entry_id):
            st = self.hass.states.get(e.entity_id)
            total += 1
            if st is None or st.state == "unavailable":
                unavailable += 1
        return unavailable, total

    def _read_config_entries(self, spec, base):
        """Two shapes, both generic across every domain:

          setup_retry     HA already says so outright.
          loaded + dead    a config entry can read `loaded` while every
                           entity it owns reads unavailable (one live
                           case ran 2h25m, found only by accident). total==0 is
                           excluded — see _entry_unavailable_ratio.

        THE SIGNAL KEYS ON THE SHAPE, NEVER ONE INTEGRATION: no domain is
        named anywhere in this function. CONFIG_ENTRY_DWELL holds a fresh
        `bad` reading for 300s before it counts, because this row —
        unlike every other INTEGRITY row — reads raw framework state with
        no upstream dwell of its own, and a core restart's ~60-90s window
        of entries still starting up would otherwise page an operator before HA
        finished booting.
        """
        try:
            entries = self.hass.config_entries.async_entries()
        except Exception as exc:  # noqa: BLE001 — RULE 1
            self._warn_once(
                "config_entries_registry",
                "registry_error",
                "config_entries read failed: " + str(exc),
            )
            base["disposition"] = DISP_ABSENT
            base["detail"] = "config_entries registry unreadable"
            return base

        now = dt_util.utcnow()
        sustained = []
        watched = 0
        for entry in entries:
            try:
                if entry.disabled_by is not None:
                    continue
                watched += 1

                is_retry = entry.state == ConfigEntryState.SETUP_RETRY
                reason = "setup_retry" if is_retry else None
                if entry.state == ConfigEntryState.LOADED and not is_retry:
                    unavailable, total = self._entry_unavailable_ratio(entry.entry_id)
                    if total > 0 and unavailable == total:
                        reason = "all " + str(total) + " entities unavailable"

                since = self._mark("cfgentry:" + entry.entry_id, reason or "ok")
                if reason is None:
                    continue
                started = dt_util.parse_datetime(since or "")
                if started is None:
                    continue
                if (now - started).total_seconds() >= CONFIG_ENTRY_DWELL:
                    sustained.append(entry.title + " (" + entry.domain + "): " + reason)
            except Exception as exc:  # noqa: BLE001 — RULE 1: one bad entry
                # must never take the whole coordinator update down with it.
                self._warn_once(
                    "cfgentry_read:" + getattr(entry, "entry_id", "?"),
                    "registry_error",
                    "config entry read failed: " + str(exc),
                )
                continue

        base["watched_count"] = watched
        if sustained:
            more = ""
            if len(sustained) > 1:
                more = " +" + str(len(sustained) - 1) + " more"
            base["disposition"] = DISP_OK
            base["integrity"] = INTEGRITY_DEGRADED
            base["integrity_detail"] = sustained[0] + more
            base["affected"] = len(sustained)
            self._warn_once(spec["key"], "")
            return base

        base["disposition"] = DISP_OK
        base["integrity"] = INTEGRITY_OK
        base["integrity_detail"] = "all " + str(watched) + " config entries healthy"
        self._warn_once(spec["key"], "")
        return base

    def _read_notify_health(self, spec, base):
        """Two facts, both cheap, both certain — see
        const.py's SOURCES comment for why this stops short of a delivery
        heartbeat. `exists` is the only thing that ever moves `integrity`;
        `last_sent` rides along as an informational attribute the resolver
        never judges against a threshold.
        """
        # GUARDED, LIKE EVERY OTHER FRAMEWORK READ IN THIS FILE. RULE 1 admits
        # no exception, and this call was the one registry-shaped read that
        # was not wrapped — _perimeter_entity_ids and _read_config_entries
        # both are, for the same stated reason. An exception escaping here
        # leaves _async_update_data, takes every entity unavailable, and takes
        # their attributes with them, which is the exact mechanism this
        # integration exists to refuse. Found by the coordinator read suite,
        # which drives this path against a hass that cannot answer.
        domain = self._bound(spec["key"], "service_domain", spec.get("service_domain"))
        service = self._bound(spec["key"], "service", spec.get("service"))
        if domain is None or service is None:
            base["detail"] = (
                "not configured: bind notify_health.service_domain and .service"
            )
            self._warn_once(
                spec["key"], "unbound",
                "notify path has no service bound (Configure -> "
                "notify_health.service_domain / .service)",
            )
            return base
        try:
            exists = self.hass.services.has_service(domain, service)
        except Exception as exc:  # noqa: BLE001 — RULE 1
            self._warn_once(
                "notify_registry",
                "registry_error",
                "service registry read failed: " + str(exc),
            )
            base["disposition"] = DISP_ABSENT
            base["detail"] = "service registry unreadable"
            return base

        last_sent = None
        st = self.hass.states.get(
            self._bound(spec["key"], "last_sent_entity_id",
                        spec.get("last_sent_entity_id"))
        )
        if st is not None and st.state not in ("unknown", "unavailable", ""):
            last_sent = st.state

        base["disposition"] = DISP_OK
        base["last_sent"] = last_sent

        if not exists:
            base["integrity"] = INTEGRITY_DEGRADED
            base["integrity_detail"] = (
                str(domain) + "." + str(service)
                + " is not a registered service — the notify target is gone"
            )
            base["affected"] = 1
            self._warn_once(spec["key"], "")
            return base

        base["integrity"] = INTEGRITY_OK
        base["integrity_detail"] = (
            "notify target registered; last successful send "
            + (last_sent or "never observed")
        )
        self._warn_once(spec["key"], "")
        return base

    def _apply_fall_dwell(self, severity):
        """RULE 3. A rise publishes immediately; a fall is held.

        Returns (published_severity, holding, held_from).
        `None` (unknown) is treated as a fall from any positive value —
        losing sight of a source must not silently clear an escalation.
        """
        now = dt_util.utcnow()
        prev = self._held_severity

        def rank(v):
            return -1 if v is None else v

        if prev is None and self._held_since is None:
            self._held_severity = severity
            self._held_since = now
            return severity, False, None

        if rank(severity) >= rank(prev):
            self._held_severity = severity
            self._held_since = now
            return severity, False, None

        # A fall. Hold the previous value until the dwell expires.
        if self._held_since is not None:
            elapsed = (now - self._held_since).total_seconds()
            if elapsed < FALL_DWELL:
                return prev, True, self._held_since.isoformat()

        self._held_severity = severity
        self._held_since = now
        return severity, False, None

    async def _async_update_data(self) -> dict:
        if not self._ages_loaded:
            await self.async_load_ages()

        readings = [self._read_source(s) for s in SOURCES]
        out = resolve(readings)

        published, holding, held_from = self._apply_fall_dwell(out["severity"])
        if published != out["severity"]:
            from .resolver import band_for, stage_for

            out["raw_severity"] = out["severity"]
            out["severity"] = published
            out["stage"] = stage_for(published)
            out["band"] = band_for(published)
        else:
            out["raw_severity"] = out["severity"]
        out["fall_dwell_holding"] = holding
        out["fall_dwell_since"] = held_from

        out.update(self._read_quiet())
        out["quiet_since"] = self._mark("quiet", out["quiet"])

        out["stage_since"] = self._mark("stage", out["stage"])
        out["integrity_since"] = self._mark("integrity", out["integrity"])
        out["directive_since"] = self._mark("directive", out["directive"])
        await self._save_ages()

        out["readings"] = {r["key"]: r for r in readings}
        out["axis_stage_keys"] = [
            r["key"] for r in readings if r["axis"] == AXIS_STAGE
        ]
        out["axis_integrity_keys"] = [
            r["key"] for r in readings if r["axis"] == AXIS_INTEGRITY
        ]
        out["axis_directive_keys"] = [
            r["key"] for r in readings if r["axis"] == AXIS_DIRECTIVE
        ]
        return out


# The quality scale's `runtime-data` rule: the coordinator hangs off the entry
# itself, and the entry carries its type. A plain assignment rather than a PEP
# 695 `type` statement so the alias evaluates on the interpreter the suite runs
# on as well as the one HA requires — the rule is about where runtime data
# lives, not about which alias syntax declares it.
HouseholdStateConfigEntry = ConfigEntry[HouseholdStateCoordinator]
