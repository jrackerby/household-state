<img src="https://raw.githubusercontent.com/jrackerby/household-state/master/brand/logo%402x.png" alt="Household State" width="240" align="right">

# household_state — abstract

Siblings: `household_state_process_flow.md` (what happens, in what order) ·
`household_state_data_flow.md` (which value came from where) ·
`household_state_architecture.md` (the static pieces and how they fit
together) · `household_state.md` (the full technical reference) ·
`household_alert_patent_disclosure.md` (a patent-disclosure draft, kept
under this system's earlier name — its own footer explains why).

## The problem

A house has a lot of things watching it: weather alerts, a security
system, door and window sensors, smoke and carbon-monoxide detectors,
network and camera health, and a handful of other feeds nobody thinks
about until the day they matter. Somebody glances at a light, a color, or
a small panel on the wall and needs an honest answer to a simple
question: is everything okay?

The trouble is that "is everything okay" is actually three different
questions wearing one costume, and most home-monitoring displays only
ever answer one of them — usually badly.

## Three questions, not one

**How urgent is this, right now?** A tornado approaching the county is
not the same urgency as a door left open for ten minutes, and neither is
the same as nothing happening at all. A single dial that tries to
represent every kind of concern with one number ends up either crying
wolf over routine things or staying calm through something that matters.

**What should a person in the house actually do about it?** Urgency and
instruction are not the same thing. Something can be very urgent and
still call for no action beyond awareness — and something moderately
urgent can call for a specific, physical response: get away from windows,
seal up the house, leave. Collapsing "how bad is it" and "what do I do"
into one signal means the moment a real instruction is needed, it either
doesn't exist or gets buried under the noise of everything else that's
merely urgent.

**Can this reading be trusted?** A monitoring system is made of parts,
and parts fail — a sensor loses power, a feed stops updating, a camera
goes offline. The question of whether the watching itself is working is
a completely different question from whether anything bad is currently
happening, and it has a different audience: the person responsible for
keeping the monitoring running, not necessarily everyone in the house.
When a system quietly folds "I can't tell" into "everything's fine," the
one moment that matters most — when the watchers themselves have gone
blind — is exactly the moment nobody finds out.

A system that gives an honest, glanceable answer needs to keep these
three questions visibly separate, because the failure mode of merging
them is always the same shape: a serious problem gets diluted by
something routine, a routine problem gets treated as an emergency, or a
broken sensor gets mistaken for good news. None of those are hypothetical
— they are the specific, recurring ways a single-number system fails
quietly and confidently.

## Why a fourth, quieter signal helps too

Households also go through stretches where the right response to
something is different simply because everyone is asleep or the house is
otherwise in a deliberately quiet state — not because the underlying
situation changed, but because who's around to act on it, and how, does.
Recognizing "the house is currently quiet" as its own fact, separate from
how urgent anything is, keeps that context available without letting it
quietly reshape what the other three questions mean. Today that fact is
just made visible, nothing more — no decision is made on the household's
behalf because of it.

## What this buys a household member

A glance answers exactly one of the three questions at a time, honestly:
red doesn't get watered down by something routine happening elsewhere, a
routine event doesn't get dressed up as a red emergency, and "I don't
know" is never disguised as "all clear." The three questions stay three
answers, not one number pretending to be enough.
