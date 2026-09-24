# AGENTS.md — the rules every agent works under here

This file is for any coding agent (Claude Code, Codex, Gemini CLI, whatever
comes next) working in this repository. It is the same rules whichever tool
reads it; `CLAUDE.md` and `GEMINI.md` are symlinks to it. The estate-wide rules
are `jrackerby/estate`'s `AGENTS.md`; the laws are `jrackerby/HA`'s
`tools/work_docs/LAW.md`. Read `README.md` and
[`docs/DESIGN_CONTRACT.md`](docs/DESIGN_CONTRACT.md) before the first edit.

## Nothing about the household leaves this session

**This repository is PUBLIC** (`public: true` in `.github/workflows/validate.yml`,
which is the repository's real visibility as of 2026-09-24). Everything in it —
source, comments, commit messages, issue text, pull request bodies and titles,
review comments, docs, test fixtures, and anything CI logs — is world-readable
the moment it lands. Treat the following as belonging to the household, not to
the code, and keep it out of every artifact an agent can write:

- **People.** Names of the family, a child, guests or pets, in prose or inside
  an entity id. `notify.mobile_app_<firstname>_iphone` in a doc names a person
  as surely as a sentence does — and it did, in four documents, until
  2026-09-24. Use `example`, or say "the bound notify target".
- **Where the household is.** A county name, a utility's service-territory key,
  a National Weather Service office slug (`nws_<office>`), a zone or an
  SAME/UGC code. Any one of these puts the house inside a few-mile radius.
  The suite used a real office slug in 101 places until 2026-09-24; it uses
  `nws_example` now.
- **The home's network and machines.** Hostnames, subnets, addresses, MAC
  addresses, SSIDs, device serials and unique ids. Use RFC 5737 addresses
  (`192.0.2.0/24`), RFC 7042 MACs (`00:00:5e:00:53:xx`) and obvious
  placeholders.
- **The home's layout and habits.** Room names, which rooms have a screen,
  when the house is empty, which doors a panel can open. A remark like "on this
  estate" tells a reader this is one specific house and invites them to piece
  the rest together.
- **Health and care data**, and **credentials, always** — tokens, cookies,
  `Authorization` headers, the `uid` of a real account. These never enter a
  commit, a log or a transcript (estate `AGENTS.md`).

The test: **would this sentence still make sense if a stranger read it?** If it
only makes sense because you know this house, rewrite it.

## Nothing household-specific is hardcoded

Every source this integration reads is **bound by the operator through the
config flow**, not named in the code. `const.py`'s `SOURCES` carries a generic
`key`, `entity_id: None`, and a `# bind: <key>.<field>` comment for every value
the operator supplies; `BINDABLE` and `BINDABLE_TEXT` declare them. A literal
entity id, service name, office slug or zone code in `const.py` is a bug, not
a default — it hardcodes one household into a public integration and breaks it
for everyone else. The same rule reaches the fixtures: a fixture proves a
*shape*, and a placeholder proves the shape exactly as well as the real value
does.

## How work lands

- **One issue, one branch, one pull request.** Every pull request closes the
  issue it names.
- **`validate / hassfest`, `validate / hacs` and `validate / tests` are
  master's required contexts** (`.github/workflows/validate.yml` calls
  `jrackerby/gha-workflows`' `validate-integration.yml`). A skipped job is a
  pass. `run-imports` is `false` here.
- **`manifest.json`'s `version` cuts a release** on a push to master
  (`release.yml` is path-filtered to that file). Bump it in the pull request
  that ships a behaviour change — and **only** then. A docs-or-fixtures-only
  change must not bump it; a release with no code in it is noise HACS pushes
  at every installation.

## How an agent reasons

- **Measure, never infer.** A cause is read off a log, a file, a wire or a
  screen. If you cannot measure it, write "unmeasured" and stop.
- **Green CI is a precondition, not a result.** `tests/ha_stubs.py` fabricates
  what Home Assistant is missing, so the suite proves logic only (LAW §16).
  `resolver.py` imports nothing from `homeassistant` by design, so the contract
  half is genuinely testable; the coordinator half is not. Setup on a running
  instance is the read-back.
- **Every claim carries a timestamp** (LAW §1). A fact here that has expired is
  edited out, not argued with.
- **Scope is the deliverable.** Do the issue; a second issue is cheap.

## Verification available to you

- `./tools/run_tests.sh -q --cov=household_state --cov-fail-under=95` — the
  exact command CI runs. It `cd`s to `tests/` itself, because the repo root
  cannot be in pytest's collection tree (`tests/pytest.ini` says why).
- `grep -rn` over the repository for the identifier classes listed above,
  before every push. The 2026-09-24 sweep found the name inside an entity id in
  four documents and a real NWS office slug in ten files; neither was caught by
  a test, and no test can catch them.
