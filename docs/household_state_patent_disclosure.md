# Invention disclosure draft — household_alert

> **This is an internal invention-disclosure draft, not a filed patent
> application and not legal advice.** It is written in patent-specification
> form (numbered paragraphs, formal claim language) as a documentation
> exercise and as a starting point should this ever go to actual patent
> counsel. No prior-art search, novelty opinion, or freedom-to-operate
> analysis has been performed. Every specific figure (30s poll, 120s dwell,
> 300s perimeter dwell, the severity bands) is drawn from
> `custom_components/household_alert/const.py` as of v0.4.0 and is
> presented below as "one embodiment" — the actual patent-claim scope, if
> pursued, would be drafted and narrowed by counsel, not by this file.

---

## TITLE OF THE INVENTION

MULTI-AXIS THREAT STATE RESOLUTION SYSTEM AND METHOD FOR AUTOMATED HOME
MONITORING, WITH DISPOSITION-PRESERVING SOURCE AGGREGATION AND ASYMMETRIC
TEMPORAL HYSTERESIS

## FIELD OF THE INVENTION

[0001] The present disclosure relates to automated monitoring and alerting
systems, and more particularly to a system and method for aggregating
multiple independently-polled sensor, feed, and device-registry sources
into a small number of differentiated output indications suitable for
directing the behavior of, and being trusted by, human occupants of a
monitored premises.

## BACKGROUND OF THE INVENTION

[0002] Automated home-monitoring platforms commonly compute a single
aggregate "threat," "alert," or "security" value from a plurality of
sensors, external data feeds, and control-panel states. Existing
implementations of such aggregation exhibit at least five distinct
deficiencies, each independently addressed by an aspect of the present
invention.

[0003] **First deficiency — disposition collapse.** Existing aggregation
logic typically reads a numeric attribute from each source and, when that
attribute is missing, the source is unavailable, or the source was never
successfully initialized, treats the absence identically to a read value
of zero. Because the aggregate is usually computed as a maximum or
threshold over the numeric values, a source that cannot be read
contributes nothing distinguishable from a source that read cleanly and
reported "all clear." This produces the specific failure mode in which
the aggregate indication continues to display a quiescent, safe reading
precisely when one or more constituent monitoring sources have silently
failed. In one measured instance, sixteen of nineteen constituent feed
sources in a prior implementation had never successfully initialized, and
the aggregate indication nonetheless displayed a normal reading
throughout, because the absent sources were read as numeric zero rather
than as a distinct "could not read" disposition.

[0004] **Second deficiency — symmetric or absent temporal hysteresis.**
Existing severity-to-displayed-state mappings apply either no smoothing
interval, or a single smoothing interval applied identically regardless of
whether the underlying value is rising or falling. Applying no smoothing
produces rapid oscillation between displayed states for a source whose
underlying reading crosses a threshold repeatedly over a short interval —
in one measured instance, a displayed state oscillated between two values
twenty-three times over six days, each occurrence lasting zero to four
seconds. Applying a symmetric smoothing interval to both rising and
falling values instead delays the display of a genuine escalation by the
same interval that is desirable for suppressing a falling-value
oscillation, which is undesirable whenever the escalation corresponds to
a safety-relevant condition.

[0005] **Third deficiency — undifferentiated adoption of an upstream
classification field.** Existing systems that consume a third-party,
standardized alert record (for example, a weather-service alert carrying
a coarse, standardized response-type field) commonly surface that field's
value to the household directly, or map it through a single lookup table.
Because the standardized field's categorization is generic across a wide
population of alert types and is not calibrated to the specific monitored
premises, this produces both (a) false positives, in which a
routine, seasonally-frequent alert type is tagged by the standardized
field with a response category that would otherwise trigger a physical
relocation instruction to the occupants, training the occupants to
disregard the instruction; and (b) false negatives, in which a
specific, narrowly-defined emergency category relevant to the premises
carries a standardized field value that a generic mapping does not
recognize as actionable.

[0006] **Fourth deficiency — conflation of monitoring trustworthiness
with the monitored condition.** Existing designs typically encode the
health or completeness of the monitoring layer itself as a value on the
same numeric scale, and displayed through the same channel, as the
household-facing threat indication. A monitoring degradation and a
concurrently-occurring genuine emergency therefore compete for the same
display value, and whichever is numerically larger suppresses the
visibility of the other — obscuring the specific combination (monitoring
degraded during an emergency) in which the discrepancy is most
consequential to a human operator responsible for the monitoring system.

[0007] **Fifth deficiency — static device-membership lists.** Existing
designs commonly identify the set of physical devices contributing to a
given monitored condition (for example, all door and window contact
sensors contributing to a "perimeter open" condition) by a fixed,
hand-maintained list of device or entity identifiers embedded in
configuration or code. When a physical device is replaced — for example,
following a hardware upgrade — the fixed list is not automatically
updated, and the replacement device silently fails to contribute to the
monitored condition, without the omission itself being flagged as a
fault.

[0008] There is accordingly a need for an aggregation architecture that
preserves the distinction between "could not be read" and "read as
quiescent" through every stage of computation; that applies temporal
smoothing asymmetrically so that an escalation is never delayed by the
mechanism intended to suppress a de-escalation oscillation; that derives
a household-facing directive from more than one independent classifier
applied to the same underlying alert record, with every declined finding
retained rather than discarded; that computes monitoring trustworthiness
as an output distinct from, and incapable of altering, the household-
facing threat indication; and that determines device-set membership by
live query against a registry rather than a static list.

## SUMMARY OF THE INVENTION

[0009] In one aspect, a monitoring coordinator reads each of a plurality
of sources at a fixed polling interval and, for each source, assigns one
of a plurality of dispositions, at least one of which is a positive-
reading disposition and at least one of which is a not-read disposition
distinct from any numeric value the source could otherwise report. A
stateless resolution function computes an aggregate severity value using
only sources assigned the positive-reading disposition, and — critically
— when no positive-reading source reports an active condition and at
least one source has been assigned a not-read disposition, the aggregate
severity is set to a third, indeterminate value rather than to the
zero value that "no active condition among the readable sources" would
otherwise imply.

[0010] In a second aspect, the aggregate severity value is passed through
an asymmetric temporal hysteresis stage: an increase relative to the
previously published value is published on the same polling cycle in
which it is computed, while a decrease is withheld for a predetermined
dwell interval, during which the previously published value continues to
be published, before the decrease is allowed to take effect.

[0011] In a third aspect, a directive indication is derived from an alert
record carrying both a standardized response-type field and a free-text
event-name field, by applying two classifiers to the same record
independently — one keyed to the standardized field, one keyed to the
event name — such that a classifier keyed to the event name can supply a
finding the standardized-field classifier would have missed, without
either classifier suppressing a more urgent finding the other classifier
produces on the same record. A predetermined suppression list excludes
specific event names from producing any directive, and each such
exclusion is recorded as a retrievable fact distinct from "no qualifying
alert record existed."

[0012] In a fourth aspect, a monitoring-trustworthiness indication is
computed from a set of sources distinct from those contributing to the
household-facing threat indication, carries no severity value of its own,
and is incapable, by the structure of the resolution function, of
altering the household-facing indication — while itself distinguishing an
indeterminate state (one or more of its own sources unreadable) from a
determined-degraded state, with the former outranking the latter.

[0013] In a fifth aspect, membership in a monitored device set is
determined at each polling interval by querying a device or entity
registry for the current set of devices carrying a shared label, rather
than by reading a previously stored list of identifiers, and a
sustained-condition duration for that set is computed from a
persisted since-timestamp maintained independently of, and not reset by,
a restart of the monitoring system.

## BRIEF DESCRIPTION OF THE DRAWINGS

[0014] FIG. 1 is a block-flow diagram illustrating the overall system:
a source layer 110, a per-source read stage 120, a stateless resolution
stage 130, an asymmetric-hysteresis stage 140, an entity-publication
stage 150, and a plurality of consuming components 160.

[0015] FIG. 2 is a flow diagram illustrating the tiebreak-ordered
severity-resolution process of the resolution stage 130, including the
disposition-preserving exclusion described in the Summary.

[0016] FIG. 3 is a flow diagram illustrating the dual-classifier
directive-resolution process, including the independent application of a
response-field classifier and an event-name classifier to a common alert
record, the suppression-with-recording step, and the fixed-precedence
selection step.

[0017] FIG. 4 is a state diagram illustrating the asymmetric temporal
hysteresis of the second aspect: an unconditional rising transition and a
dwell-gated falling transition sharing one state variable.

## DETAILED DESCRIPTION OF THE PREFERRED EMBODIMENT

[0018] Referring to FIG. 1, a plurality of source records 112 are read at
120 by a coordinator on a fixed polling interval, in one embodiment 30
seconds. Each source record 112 is associated with exactly one of three
output axes: an urgency axis, a directive axis, or a monitoring-
trustworthiness axis, such that a given source contributes to exactly one
axis and the monitoring-trustworthiness axis is computed from a set of
source records disjoint from the set contributing to the urgency axis.

[0019] **Disposition-preserving read (first aspect).** At 120, each
source record 112 is assigned one of a plurality of dispositions
comprising, in one embodiment: a positive-reading disposition indicating
the source was read and its value parsed successfully; an absent
disposition indicating no monitoring source exists at the expected
location; an unreachable disposition indicating the source exists but did
not respond; an unknown-state disposition indicating the source responded
with a state carrying no information; and an unparsed disposition
indicating the source responded but its value could not be interpreted as
a severity value. None of the non-positive-reading dispositions carry an
implicit numeric value.

[0020] At 130, the resolution stage computes the urgency axis by
examining only source records assigned the positive-reading disposition,
in a fixed evaluation order (a "tiebreak order," FIG. 2) so that the
identity of the driving source, not only the numeric value, is
deterministic when two sources report the same severity. If no
positive-reading source reports a severity above a quiescent threshold,
and at least one source record was assigned a non-positive-reading
disposition, the urgency axis is set to an indeterminate value — distinct
from, and never collapsing into, the quiescent value that would be
reported if all sources were positive-reading and quiescent. If no source
record exists for a given polling cycle at all, the indeterminate value
is likewise reported rather than a quiescent default.

[0021] **Asymmetric temporal hysteresis (second aspect).** Referring to
FIG. 4, the resolution stage's output urgency value at each polling cycle
is compared to a held value from the previous cycle. If the new value is
greater than or equal to the held value (including a transition from a
determinate value to the indeterminate value, which is ranked below every
determinate value for this comparison), the held value is updated to the
new value immediately and published without delay. If the new value is
less than the held value, the previously held value continues to be
published, and the new value is only adopted, and published, once a
predetermined dwell interval has elapsed since the held value was last
updated — in one embodiment, 120 seconds. The dwell interval is applied
exclusively to decreasing transitions; no dwell is applied to an
increasing transition under any circumstance.

[0022] **Dual-classifier directive resolution (third aspect).** Referring
to FIG. 3, for each alert record among a plurality of currently active
alert records, a first classifier maps a standardized response-type field
carried by the alert record to one of a fixed set of directive values, and
a second classifier, independently and regardless of the outcome of the
first classifier, maps the alert record's free-text event-name field to
one of the same fixed set of directive values via a lookup table. Both
classifiers are evaluated for every alert record; the second classifier's
finding is not conditioned on, and does not suppress, the first
classifier's finding on the same record, or vice versa. A predetermined
suppression list, keyed by event name, causes any finding — from either
classifier — produced on a record carrying a listed event name to be
excluded from the selection step below; each such exclusion is recorded,
together with the alert record's event name and the finding that was
excluded, as an attribute of the output directive indication, such that a
consuming display component can distinguish "a directive was found and
declined" from "no directive was found." Among the findings not excluded,
across all classifiers and all currently active alert records, the
finding corresponding to the highest-precedence directive value under a
fixed, total precedence order is selected as the output directive value.

[0023] **Audience-separated, non-severity trustworthiness axis (fourth
aspect).** The monitoring-trustworthiness axis is computed from a set of
source records distinct from the urgency axis's source records. Its
output value is one of a fixed, small set of states carrying no
associated numeric severity: unreadable source records, in the
aggregate, produce an indeterminate trustworthiness state; in the absence
of any unreadable source record, a source record indicating a degraded
condition produces a degraded trustworthiness state; and the absence of
both conditions produces a nominal trustworthiness state. The
indeterminate state outranks the degraded state. The resolution function
is structured such that no code path exists by which a value computed for
the trustworthiness axis can alter the urgency axis's output value.

[0024] **Live-discovered device-set membership with restart-independent
duration (fifth aspect).** For a monitored condition defined over a set
of physical devices sharing a common attribute (in one embodiment, a
label applied to each device at registration time), the set of member
device identifiers is determined at each polling interval by querying a
device or entity registry for the devices currently carrying the shared
attribute, rather than by reading a list of identifiers stored in
configuration or code. For each queried device found to be in a
triggering state, a since-timestamp recording the moment that device most
recently transitioned into the triggering state is read from, and written
to, a persistent store maintained by the coordinator, independently of
any timestamp the device's own record carries — the device's own
last-change timestamp being, in at least one home-automation platform,
reset to the platform's most recent restart time for a device whose prior
state was reconstructed from persisted storage rather than freshly
observed. A sustained-condition duration is computed as the difference
between the current time and the persisted since-timestamp, and a
sustained-condition finding (for example, a "sustained perimeter breach"
condition) contributes to the urgency axis once that duration exceeds a
predetermined threshold, in one embodiment 300 seconds, regardless of an
intervening restart of the monitoring system.

[0025] **Availability-preserving coordinator (supporting the first
aspect).** The coordinator is configured such that no failure to read an
individual source record, and no failure encountered while querying the
device registry of the fifth aspect, causes the coordinator to enter a
failed-update state. The coordinator instead always publishes a complete
data structure, on every polling cycle, in which an individual
unreadable source is represented by its assigned disposition rather than
by the absence of the source's entry or by the unavailability of any
output entity computed from the data structure. Each output entity
computed from the data structure reports itself as available for
observation at all times, reporting the underlying read failure, if any,
as an attribute value rather than as its own unavailability — so that an
observing party is never prevented, by the failure that most needs to be
observed, from observing it.

## CLAIMS

**1.** A computer-implemented method for resolving a plurality of
independently polled monitoring sources into a threat indication for an
automated premises-monitoring system, the method comprising:

&nbsp;&nbsp;(a) reading, at each of a series of polling intervals, a value
from each of the plurality of monitoring sources;

&nbsp;&nbsp;(b) assigning to each monitoring source, based on the result
of the reading, one of a plurality of dispositions, the plurality of
dispositions comprising at least a positive-reading disposition and one
or more not-read dispositions distinct from any numeric severity value;

&nbsp;&nbsp;(c) computing an aggregate severity value using only monitoring
sources assigned the positive-reading disposition; and

&nbsp;&nbsp;(d) responsive to determining that (i) no monitoring source
assigned the positive-reading disposition reports a severity value
exceeding a quiescent threshold, and (ii) at least one monitoring source
was assigned a not-read disposition, setting the aggregate severity value
to an indeterminate value distinct from a quiescent value.

**2.** The method of claim 1, wherein the plurality of dispositions
further comprises: an absent disposition indicating no monitoring source
exists at an expected source location; an unreachable disposition
indicating a monitoring source exists but did not respond; an
unknown-state disposition indicating a monitoring source responded with a
state carrying no information; and an unparsed disposition indicating a
monitoring source responded with a value that could not be interpreted as
a severity value.

**3.** The method of claim 1, further comprising applying a temporal
hysteresis to the aggregate severity value, wherein an increase in the
aggregate severity value relative to a previously published value is
published without delay, and a decrease in the aggregate severity value
relative to the previously published value is withheld for a
predetermined dwell interval before being published, the previously
published value continuing to be published during the dwell interval.

**4.** The method of claim 3, wherein a transition of a monitoring source
from the positive-reading disposition to a not-read disposition, for a
monitoring source previously contributing to the aggregate severity
value, is treated as a decrease subject to the dwell interval.

**5.** A computer-implemented method for deriving a directive indication
for an automated premises-monitoring system from an alert record
comprising a standardized response-type field and an event-name field,
the method comprising:

&nbsp;&nbsp;(a) applying a first classifier to the standardized
response-type field of the alert record to produce a first candidate
finding;

&nbsp;&nbsp;(b) applying a second classifier to the event-name field of the
alert record, independently of the first classifier and irrespective of
whether the first classifier produced a candidate finding, to produce a
second candidate finding;

&nbsp;&nbsp;(c) responsive to the event-name field matching an entry in a
predetermined suppression list, excluding both the first candidate
finding and the second candidate finding from further consideration, and
recording an indication of the exclusion; and

&nbsp;&nbsp;(d) selecting, from candidate findings not excluded under
step (c), across a plurality of alert records, a candidate finding
corresponding to a highest-precedence directive value under a fixed
precedence order, as the directive indication.

**6.** The method of claim 5, wherein the recording of an exclusion under
step (c) persists an identification of the alert record and the
candidate finding excluded, retrievable by a display component consuming
the directive indication, such that a decision to withhold a directive
finding is distinguishable, at the display component, from an absence of
any qualifying alert record.

**7.** An automated premises-monitoring system comprising:

&nbsp;&nbsp;a first output representing an urgency level for a first,
household audience, computed from a first plurality of monitoring
sources; and

&nbsp;&nbsp;a second output representing a trustworthiness of the
monitoring system, for a second, operator audience, computed from a
second plurality of monitoring sources disjoint from the first plurality,

&nbsp;&nbsp;wherein the second output carries no severity value, and
wherein the system is configured such that no value computed for the
second output alters the first output.

**8.** The system of claim 7, wherein the second output takes on an
indeterminate state, ranked above a degraded state of the second output,
whenever any monitoring source of the second plurality cannot be read,
such that an inability to determine the trustworthiness of the monitoring
system is distinguished from a determined-degraded trustworthiness.

**9.** A method for determining membership in a monitored device set for
an automated premises-monitoring system, comprising:

&nbsp;&nbsp;assigning a common label to each of a plurality of physical
devices at a time each device is registered with a device or entity
registry;

&nbsp;&nbsp;at each of a series of polling intervals, querying the
registry for a current set of devices carrying the common label, rather
than reading a previously stored list of device identifiers; and

&nbsp;&nbsp;evaluating a state-based condition against the queried
current set,

&nbsp;&nbsp;whereby a replacement of a physical device carrying the
common label is reflected in the monitored device set at a next polling
interval without a corresponding configuration or code change.

**10.** The method of claim 9, further comprising:

&nbsp;&nbsp;persisting, independently of a last-state-change timestamp
maintained by each device's own record, a since-timestamp recording when
each device most recently transitioned into a triggering state; and

&nbsp;&nbsp;computing a sustained-condition duration from the persisted
since-timestamp rather than from the device's own last-state-change
timestamp,

&nbsp;&nbsp;whereby the sustained-condition duration is not reset by a
restart of the automated premises-monitoring system.

**11.** A monitoring coordinator for an automated premises-monitoring
system, configured to:

&nbsp;&nbsp;read a plurality of monitoring sources at each of a series of
polling intervals; and

&nbsp;&nbsp;publish, on every polling interval regardless of whether any
individual monitoring source could be read, a data structure representing
all of the plurality of monitoring sources,

&nbsp;&nbsp;the coordinator being configured to never enter a
failed-update state responsive to a failure to read any individual
monitoring source,

&nbsp;&nbsp;whereby a plurality of output entities computed from the data
structure remain available for observation regardless of whether one or
more of the plurality of monitoring sources could be read.

**12.** The monitoring coordinator of claim 11, wherein an output entity
computed from the data structure reports its own availability state as
available regardless of whether a monitoring source it depends on could
be read, and reports an inability to read the monitoring source as an
attribute value of the output entity rather than as the output entity's
own unavailability.

## ABSTRACT

A system and method for resolving a plurality of independently polled
sensor and feed sources into three audience-differentiated household
indications — an urgency indication, a directive indication, and a
monitoring-confidence indication — without conflating an inability to
read a source with a quiescent reading from that source. Each source is
assigned one of a plurality of dispositions, and sources assigned a
not-read disposition are excluded from contributing an implicit
zero-severity value to the urgency indication. A temporal hysteresis is
applied asymmetrically, publishing an increase in urgency without delay
while withholding a decrease for a predetermined dwell period. A
directive indication is derived from two independent classifiers applied
to a common alert record and combined under a fixed precedence rule, with
every declined finding recorded rather than discarded. A monitoring-
confidence indication is computed from a source set disjoint from the
urgency indication's sources, carries no severity value, and cannot alter
the urgency indication. Monitored-device-set membership is determined by
live registry query against a shared device label rather than a static
identifier list, with sustained-condition duration computed from a
persisted timestamp independent of system restarts.

---

*Reference implementation: `custom_components/household_alert/`
(`const.py`, `coordinator.py`, `resolver.py`), v0.4.0 — renamed
`household_state` at v0.5.0 (2026-08-22); this draft is pinned to the
v0.4.0 name and figures deliberately, per the note above. See
`docs/integrations/household_state.md` for the current operational
reference and `jrackerby/HA` `docs/PROCESS.md` for the documentation method used
across this repo's `docs/integrations/` tree.*
