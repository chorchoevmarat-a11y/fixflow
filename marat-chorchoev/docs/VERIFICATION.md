# Verification record

What was actually run while building this, what it printed, and what was **not** run.
Environment: Windows 11, bash; PostgreSQL 16.2 (a local server process — **no Docker**), uv 0.11.19 with
Python 3.14.5, Bun 1.4.4, Node 26.13, Flutter 3.50.0 / Dart 3.14.0, Android SDK 35/36 + JDK 21 from Android Studio.

## Backend

```
cd backend && uv sync --frozen && uv run ruff check . && uv run ruff format --check . && uv run ty check . && uv run pytest -q
```

| Step | Result |
| --- | --- |
| `uv sync --frozen` | OK (78 packages, lockfile in sync) |
| `ruff check` | `All checks passed!` |
| `ruff format --check` | `49 files already formatted` |
| `ty check` | `All checks passed!` |
| `pytest -q` with `TEST_DATABASE_URL=…/fixflow_test` | **45 passed** (≈36 s) |

The tests build the schema from the real Alembic migration into an empty database, then truncate between tests.
Coverage (QA-01): lifecycle permissions and every transition (16), organization isolation, notifications,
deactivation, auth failures, rate limiting and session revocation (7 incl. protected file downloads and
upload validation), schedule overlap/adjacency, candidate reasons, **concurrent assignment** (6 parallel
attempts → exactly one 200 and five 409), note/material/assignment **idempotency replay and key mismatch**,
**inventory race** (two technicians, last units → one 201, one 409, stock 3), offline-replay conflict
(`ASSIGNMENT_REVOKED`), smart slot suggestions (12), estimate gate, versioning, immutability, stale-version
approval, **simultaneous decisions** (one 200, two 409), idempotent decisions, SLA calendar maths (Friday
evening due after the weekend, holiday skipped, estimate pause, priority recalculation), **overdue escalation
exactly once across three parallel runs**, **recurring generation de-duplicated across three parallel runs**,
retired assets (10).

Seed: `python -m app.cli reset-db --yes-destroy-local-data` on a local database → migrations applied, 2
organizations / 15 users / 59 requests / 31 assignments / 13 completion + 11 intake photos / 5 feedback /
7 material usages / 4 plans; a second `seed` printed `demo data already present; nothing to do`.

## Smoke test against a running system

API started with `uvicorn app.main:app --workers 2` on the seeded database, then `./scripts/smoke.sh`:

```
health (live, ready) 200 · sign in as requester/dispatcher/technician/other-org admin
request created · requester cannot assign (403) · triage (200) · assigned · accepts (200) · starts (200) · IN_PROGRESS
invalid transition rejected (409) · overlapping assignment conflicts (409)
other organization cannot read the request (404) · cannot select org A (403) · missing credentials (401) · OpenAPI reachable (200)
SMOKE PASSED
```

## Web

```
cd web && bun install --frozen-lockfile && bun run lint && bun run typecheck && bun run test:ci && bun run build
```

| Step | Result |
| --- | --- |
| `bun install --frozen-lockfile` | OK (650 packages; Next 16.4.6, React 19, TypeScript 5.9) |
| `bun run lint` (ESLint) / `bun run typecheck` (`tsc --noEmit`, strict) | no findings |
| `bun run test:ci` | **15 passed** in 4 suites |
| `bun run build` | compiled; 17 routes generated |

Tests (QA-02): required-field validation with inline errors and no request sent; search and priority filter sent
to the server with the empty state; protected route redirects/role mismatch/expired-session handling; and a
backend-driven mutation (triage) after which the status badge changes without a reload, plus rejected actions
and double-submit protection.

Manual browser check against the live API (one desktop browser): sign-in as dispatcher → dashboard (counts,
charts, overdue count, 14-day window) → request queue with URL-driven filters → request detail → **Smart slot
finder** (found a bug: the page showed "Not Found" because the API process predated the new endpoint; after a
restart it listed bookable slots). Not covered: mobile-width visual review, requester and admin screens, keyboard
walk-through.

## Mobile

```
cd mobile && flutter pub get && dart format --output=none --set-exit-if-changed lib test && flutter analyze && flutter test && flutter build apk --debug
```

| Step | Result |
| --- | --- |
| `flutter pub get` | OK |
| `dart format --set-exit-if-changed` | clean |
| `flutter analyze` | `No issues found!` (a first full run found 20 brace-style infos after formatting; fixed with `dart fix`) |
| `flutter test` | **15 passed** (assignment card, restart persistence, replay after a dropped connection, idempotent duplicate delivery, conflict states, expired session, validation failure) |
| `flutter build apk --debug` | OK — `mobile/build/app/outputs/flutter-apk/app-debug.apk` (≈158 MB debug build; first build took ≈13 min while Gradle fetched the NDK/CMake) |

Real client against live API (`dart run tool/live_check.dart http://localhost:8000`, tech1 account): sign-in, 5
assigned jobs, the **same note id** returned when the identical command was replayed, a photo uploaded twice
→ one note, reuse of the id with a different body → `409 COMMAND_ID_REUSED`, unknown job → `404`, profile,
notifications, sign-out. It also found a real bug (the inbox listed a reopened job the technician no longer
holds, where notes get `ASSIGNMENT_REVOKED`); the inbox now shows only currently assigned jobs.

## Whole pipeline

`./scripts/verify-all.sh` (backend + web + mobile, exactly the commands above) ran to completion:
`=== ALL CHECKS PASSED ===`, exit code 0. Its first run **failed** at the mobile analyzer step (see above),
which is what the script is for; the second run, after the fix, passed.

## Not run

* `docker compose up` / image builds (no Docker available).
* The APK on a device or emulator; the offline scenario end to end on a phone.
* E2E-10 restart scenario across all services; mobile-width browser review.

See `docs/KNOWN_LIMITATIONS.md` for the full list and the reasons.
