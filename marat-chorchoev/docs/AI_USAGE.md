# AI usage

## Tools

* **Claude Code** (Anthropic's coding agent, desktop app) was used throughout: reading the specification,
  comparing it with an earlier draft of this repository, rewriting the backend, web and mobile code, writing the
  tests, scripts and documentation, and running the toolchains.
* No other generative tools were used. Library code comes from open-source packages listed in each
  component's lockfile (`backend/uv.lock`, `web/bun.lock`, `mobile/pubspec.lock`).

## How the output was verified

AI-written code was not trusted on sight. It was accepted only after:

1. **Automated checks** — backend: `ruff check`, `ruff format --check`, `ty check`, 45 `pytest` tests against a
   real PostgreSQL built from the Alembic migrations; web: ESLint, strict `tsc`, 15 Jest tests, `next build`;
   mobile: `flutter analyze`, `dart format`, 15 `flutter test` tests. Results are in `docs/VERIFICATION.md`.
2. **Concurrency tests that can fail** — races (assignment, inventory, estimate decisions, duplicate commands,
   maintenance generation, escalation) are asserted with `asyncio.gather` against PostgreSQL, so a missing lock or
   constraint produces a red test rather than a hidden bug.
3. **Running the real thing** — the seed replays history through the live HTTP API; `scripts/smoke.sh` ran
   against a 2-worker server; the web app was driven in a browser against that server. Problems found this way
   (for example a stale server missing a new endpoint, and a dashboard query that needs a timezone database)
   were fixed.
4. **Review against the specification** — requirement identifiers (e.g. SCHED-03, INV-05) were mapped to code and
   tests; items that could not be proven are listed in `docs/KNOWN_LIMITATIONS.md` rather than claimed.

Known weak spots of AI-generated work to keep in mind when reviewing: UI copy, CSS details, and anything that
needs a device or Docker (see "Not verified" in the limitations document).

Private prompts and chat logs are not included.
