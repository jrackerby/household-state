"""Coordinator — source reads, the fall dwell, and the persisted ages."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, label_registry as lr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    AXIS_DIRECTIVE,
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
    SOURCES,
    STORE_KEY,
    STORE_VERSION,
)
from .resolver import alarm_severity, resolve

_LOGGER = logging.getLogger(__name__)

_BAD_STATES = ("unavailable", "unknown", "none", "")

# Condition tokens that mean SOMEBODY MUST EDIT SOMETHING, as opposed to a
# source that is merely unreadable right now. These log at WARNING; every
# other token logs at INFO, per the quality scale's log-when-unavailable.
_DEFECT_STATES = frozenset(
    {"missing", "label_absent", "label_empty", "unparsed", "registry_error"}
)


class HouseholdStateCoordinator(DataUpdateCoordinator):
    """Reads every source, resolves, holds falls, persists ages.

    RULE 1: THIS COORDINATOR NEVER RAISES UpdateFailed. There is no
    `raise` anywhere in _async_update_data and there must not be one.
    Raising takes every entity unavailable, and attributes on an
    unavailable entity vanish — which is the exact mechanism by which a
    broken collector comes to read green.
    """

    def __init__(self, hass: HomeAssistant, scan_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="household_state",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._store = Store(hass, STORE_VERSION, STORE_KEY)
        self._ages: dict = {}
        self._ages_loaded = False
        # Fall-dwell state. RULE 3.
        self._held_severity = None
        self._held_since = None
        self._warned: dict = {}
        # Armed by async_at_started; see async_arm_logging.
        self._log_armed = False

    async def async_load_ages(self) -> None:
        """RULE 5. Must run BEFORE the first refresh, or every age
        clock restarts at zero on every HA restart — which under-reports
        age, the direction that hides the problem (Playbook §15.3)."""
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
        first polls see `st is None` for kiosk sensors and perimeter
        contacts that are merely still starting. Logging that is noise
        about HA's boot, not about the estate.

        Only the LOGGING is gated. The readings themselves are unchanged
        and still publish `absent` / `unknown` on the entity attributes
        throughout startup — collapsing those into `ok` is KAN-139 and is
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
        itself is not deduping: the perimeter and live_page messages carry
        a count and a member list, so "4 unreadable" and "1 unreadable"
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
        source it could not read. That substitution is KAN-139."""
        eid = spec["entity_id"]
        base = {
            "key": spec["key"],
            "name": spec["name"],
            "entity_id": eid,
            "axis": spec["axis"],
            "kind": spec["kind"],
            "severity": None,
            "raw_state": None,
            "detail": None,
            "disposition": DISP_ABSENT,
        }

        if spec["kind"] == "perimeter":
            # The one row with no entity_id. Dispatched before the state
            # lookup, because there is nothing to look up.
            return self._read_perimeter(spec, base)

        if spec["kind"] == "live_page":
            return self._read_live_page(spec, base)

        if spec["kind"] == "config_entries":
            return self._read_config_entries(spec, base)

        if spec["kind"] == "notify_health":
            return self._read_notify_health(spec, base)

        st = self.hass.states.get(eid)
        if st is None:
            # KAN-182 lives here: an entity that was never set up is a
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
            base["severity"] = alarm_severity(
                st.state, st.attributes.get("open_sensors")
            )
            base["detail"] = "alarm " + str(st.state)
            base["disposition"] = DISP_OK
            return base

        if spec["kind"] == "binary_hazard":
            # A binary_sensor whose `on` IS the hazard. No scale to read.
            #
            # Deliberately strict about what counts as off: only the literal
            # "off" resolves to severity 0. Anything else that reached here
            # is a state this row does not understand, and guessing `clear`
            # for it is the KAN-139 substitution in a new coat. (unavailable,
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
            # KAN-208. RAW PAIRS ONLY — the vocabulary map and the
            # suppression policy are in resolver.py, where they can be
            # exercised without moving the real world (Playbook §16.1).
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
            # RULE 6 / §11.5 step 3b. Integrity axis only — the severity
            # attribute on this entity is deliberately NOT read.
            #
            # KAN-210: THE ATTRIBUTE TRIPLE COMES OFF THE REGISTRY ROW,
            # not off a name hardcoded here. §7.3 has always specified
            # two sources on this entity — device liveness and perimeter
            # tamper — and 0.1.0 read tamper_integrity into a key that
            # nothing downstream consumed. A value read and dropped is
            # indistinguishable from a value never read.
            base["disposition"] = DISP_OK
            base["integrity"] = st.attributes.get(spec["integrity_attr"])
            base["integrity_detail"] = st.attributes.get(spec["detail_attr"])
            base["affected"] = st.attributes.get(spec["affected_attr"]) or 0
            base["detail"] = base["integrity_detail"]
            # GH-565: CARRY WHICH ATTRIBUTE WAS READ, not just which
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
            # KAN-207's shape: the entity answered and the severity did
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
        st = self.hass.states.get(QUIET_SOURCE_ENTITY)
        base = {
            "quiet": None,
            "quiet_source_entity_id": QUIET_SOURCE_ENTITY,
            "quiet_raw_state": None,
        }
        if st is None:
            self._warn_once(
                "quiet",
                "missing",
                QUIET_SOURCE_ENTITY + " does not exist (never set up?)",
            )
            return base
        base["quiet_raw_state"] = st.state
        if st.state in ("unavailable", "unknown", ""):
            self._warn_once(
                "quiet",
                st.state or "empty",
                QUIET_SOURCE_ENTITY + " is " + (st.state or "empty"),
            )
            return base
        self._warn_once("quiet", "")
        base["quiet"] = st.state == "on"
        return base

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
            lreg = lr.async_get(self.hass)
            label = lreg.async_get_label(PERIMETER_LABEL)
            if label is None:
                label = lreg.async_get_label_by_name(PERIMETER_LABEL)
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
        """§7's "Perimeter Open, Sustained" — sev 2 after a 5-minute dwell.

        THREE THINGS DIFFER FROM home_posture.yaml's version, ON PURPOSE.

        1. THE DWELL IS MEASURED FROM A PERSISTED OPEN-SINCE, not from
           `last_changed` (RULE 5, Playbook §15.3). HA resets
           `last_changed` to restart time for every restored entity, so
           the template version cannot fire for five minutes after any
           restart and under-reports age — the direction that hides the
           problem.
        2. A MEMBER THAT IS MISSING OR UNREADABLE MAKES THIS SOURCE
           `unknown`, NOT CLOSED. The template's `is not none` guard
           fails permissive: a deleted contact reads as 'off', which is
           precisely how the front door and the drop zone went uncovered
           for weeks after the Ring swap. KAN-139.
        3. A SUSTAINED OPEN STILL PUBLISHES sev 2 while other members
           are unreadable. A positive finding does not need complete
           visibility; only a negative one does.
        """
        ents = self._perimeter_entity_ids()
        if ents is None:
            base["disposition"] = DISP_ABSENT
            base["detail"] = "label " + PERIMETER_LABEL + " does not resolve"
            self._warn_once(
                spec["key"],
                "label_absent",
                "perimeter label " + PERIMETER_LABEL + " does not resolve",
            )
            return base
        if not ents:
            base["disposition"] = DISP_ABSENT
            base["detail"] = "no contacts or covers carry label " + PERIMETER_LABEL
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
            more = ""
            if len(sustained) > 1:
                more = " +" + str(len(sustained) - 1) + " more"
            base["disposition"] = DISP_OK
            base["severity"] = PERIMETER_SEV
            base["detail"] = (
                sustained[0] + more + " open over " + str(PERIMETER_DWELL) + "s"
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

    def _live_page_entity_ids(self):
        """DISCOVER, DON'T PIN — kiosk_pi's live_page sensors, off the
        registry. Matched on PLATFORM plus the unique_id TAIL, never on
        entity_id or a host list: TOOLS.md already found one kiosk_pi
        device carrying several id prefixes at once, so entity_id itself
        cannot be trusted to end in `_live_page` in every case a bare
        pattern match would assume.

        Returns None only when the registry lookup itself fails (RULE 1
        guards it the same way the perimeter label lookup is guarded); an
        empty list is a real, distinct fact — no kiosk_pi hosts exist.
        """
        try:
            ereg = er.async_get(self.hass)
            return sorted(
                e.entity_id
                for e in ereg.entities.values()
                if e.platform == "kiosk_pi" and (e.unique_id or "").endswith("_live_page")
            )
        except Exception as exc:  # noqa: BLE001 — RULE 1
            self._warn_once(
                "live_page_registry",
                "registry_error",
                "kiosk_pi live_page discovery failed: " + str(exc),
            )
            return None

    def _read_live_page(self, spec, base):
        """KAN-260 (GH #55). Aggregates every sensor.<host>_live_page.

        Reads only the `diverged` / `read_unreachable` booleans kiosk_pi's
        own coordinator already dwells (see sensor.py's KAN-311 comment on
        the live_page description) — this function does no dwelling of its
        own. TWO SIGNALS, NOT ONE FAULT: kept in separate lists so the
        detail string never collapses "showing a stale page" into "DevTools
        not answering," which are different problems with different fixes.

        STATE `unknown` IS NOT BLIND HERE, unlike the perimeter row. This
        sensor's own `state` is the live-page URL itself, which
        sensor.py's docstring says is legitimately null the moment DevTools
        cannot be read — that is exactly the `read_unreachable` case this
        row exists to catch, carried in the ATTRIBUTES regardless of what
        `state` holds. Routing every `unknown` state into blind first
        found this live, on the very host it was supposed to catch:
        kiosk05 read `read_unreachable: true` while its own state sat at
        `unknown`, and the blind-first check silently swallowed the
        finding. Only `st is None` or `state == unavailable` — the entity
        itself gone, attributes cleared with it (RULE 1) — is really blind.
        """
        ent_ids = self._live_page_entity_ids()
        if not ent_ids:
            base["disposition"] = DISP_ABSENT
            base["detail"] = "no kiosk_pi live_page entities discovered"
            return base

        blind = []
        diverged = []
        unreachable = []
        for eid in ent_ids:
            st = self.hass.states.get(eid)
            if st is None or st.state == "unavailable":
                blind.append(eid)
                continue
            attrs = st.attributes
            if attrs.get("read") == "offline_expected":
                continue
            if attrs.get("diverged"):
                diverged.append(eid)
            if attrs.get("read_unreachable"):
                unreachable.append(eid)

        base["watched_count"] = len(ent_ids)
        base["blind"] = blind

        if diverged or unreachable:
            parts = []
            if diverged:
                parts.append(
                    str(len(diverged)) + " showing a stale page (" + diverged[0] + ")"
                )
            if unreachable:
                parts.append(
                    str(len(unreachable)) + " DevTools unreachable (" + unreachable[0] + ")"
                )
            base["disposition"] = DISP_OK
            base["integrity"] = INTEGRITY_DEGRADED
            base["integrity_detail"] = "; ".join(parts)
            base["affected"] = len(set(diverged) | set(unreachable))
            self._warn_once(spec["key"], "")
            return base

        if blind:
            # No positive finding and incomplete visibility — unknown, not
            # ok, same rule the perimeter row already applies.
            base["disposition"] = DISP_UNKNOWN
            base["detail"] = (
                "cannot confirm live page health: "
                + str(len(blind)) + " of " + str(len(ent_ids)) + " unreadable"
            )
            # Same token rule as the perimeter row above.
            self._warn_once(
                spec["key"],
                "blind",
                str(len(blind)) + " live_page sensor(s) unreadable: " + ", ".join(blind),
            )
            return base

        base["disposition"] = DISP_OK
        base["integrity"] = INTEGRITY_OK
        base["integrity_detail"] = (
            "all " + str(len(ent_ids)) + " kiosk live pages agree with kiosk.sh"
        )
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
        """KAN-285 (GH #55). Two shapes, both generic across every domain:

          setup_retry     HA already says so outright (music_assistant,
                           androidtv_remote, both named live in the ticket).
          loaded + dead    a config entry can read `loaded` while every
                           entity it owns reads unavailable (the UPS,
                           2h25m, found only by accident). total==0 is
                           excluded — see _entry_unavailable_ratio.

        THE SIGNAL KEYS ON THE SHAPE, NEVER ONE INTEGRATION: no domain is
        named anywhere in this function. CONFIG_ENTRY_DWELL holds a fresh
        `bad` reading for 300s before it counts, because this row —
        unlike every other INTEGRITY row — reads raw framework state with
        no upstream dwell of its own, and a core restart's ~60-90s window
        of entries still starting up would otherwise page Joel before HA
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
        """KAN-309 (GH #55). Two facts, both cheap, both certain — see
        const.py's SOURCES comment for why this stops short of a delivery
        heartbeat. `exists` is the only thing that ever moves `integrity`;
        `last_sent` rides along as an informational attribute the resolver
        never judges against a threshold.
        """
        exists = self.hass.services.has_service(spec["service_domain"], spec["service"])

        last_sent = None
        st = self.hass.states.get(spec["last_sent_entity_id"])
        if st is not None and st.state not in ("unknown", "unavailable", ""):
            last_sent = st.state

        base["disposition"] = DISP_OK
        base["last_sent"] = last_sent

        if not exists:
            base["integrity"] = INTEGRITY_DEGRADED
            base["integrity_detail"] = (
                spec["service_domain"] + "." + spec["service"]
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
