# Verification record

What was actually run while building this, what it printed, and what was **not** run.
Environment: Windows 11, bash; PostgreSQL 16 (initially a throwaway 16.2 server process, from 13 Nov the Windows
service `postgresql-x64-16`), uv 0.11.19 with Python 3.14.5, Bun 1.4.4, Node 26.13, Flutter 3.50.0 / Dart 3.14.0,
Android SDK 35/36 + JDK 21 from Android Studio. Docker CLI 29.9.3 / Compose 5.7.0 are installed, but the engine
was not running, so **nothing was run through Docker**.

The sections below show the **latest** numbers (re-run on 13 Nov 2026 after the hardening round); the last section
describes that round and what it found.

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
| `pytest -q` with `TEST_DATABASE_URL=…/fixflow_test` | **52 passed** (≈36 s) |

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
retired assets (10). Added in the hardening round (7 tests): search wildcards treated literally, NUL characters
rejected with 422, past preferred-visit windows rejected, canceled requests leaving the default list, estimate totals
beyond BIGINT, extreme dates in slots/reports, case-insensitive inventory codes plus the `no-store`/`nosniff` headers.

Seed: `python -m app.cli reset-db --yes-destroy-local-data` on a local database → migrations applied, 2
organizations / 15 users / 59 requests / 31 assignments / 13 completion + 11 intake photos / 5 feedback /
7 material usages / 4 plans; a second `seed` printed `demo data already present; nothing to do`.
Re-checked on 13 Nov with the current code on a scratch database that was dropped afterwards: 34 tables (33 plus
`alembic_version`), the same counts (59 requests, 31 assignments, 24 evidence files), and 11 requests escalated as
overdue — the overdue count depends on the clock (it was 10 on the first run).

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
| `bun run test:ci` | **16 passed** in 4 suites |
| `bun run build` | compiled; 17 pages generated (`output: "standalone"`) |
| Production runtime | the standalone output copied next to `.next/static` and started with `node server.js` (exactly the image's runner stage): `/login`, `/dashboard`, `/requests`, `/requests/new` → 200, unknown path → 404, a JS chunk served as `application/javascript`, headers `Cache-Control: private, no-store`, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`. `next start` also answers but prints a warning that it is unsupported with `output: "standalone"`. |

Tests (QA-02): required-field validation with inline errors and no request sent; search and priority filter sent
to the server with the empty state; protected route redirects/role mismatch/expired-session handling; and a
backend-driven mutation (triage) after which the status badge changes without a reload, plus rejected actions
and double-submit protection.

Manual browser check against the live API (one desktop browser): sign-in as dispatcher → dashboard (counts,
charts, overdue count, 14-day window) → request queue with URL-driven filters → request detail → **Smart slot
finder** (found a bug: the page showed "Not Found" because the API process predated the new endpoint; after a
restart it listed bookable slots). The hardening round added the new-request form (including past-date
validation), the properties screen and its edit modal, role guards as a requester, stored-XSS titles, bad/unknown
request ids, sign-out and back-button behaviour, a double-clicked Submit, and three pages at phone width (no
horizontal overflow). Still not covered: the staff, maintenance-plan and organization-settings screens, and a
keyboard or screen-reader walk-through.

## Mobile

```
cd mobile && flutter pub get && dart format --output=none --set-exit-if-changed lib test && flutter analyze && flutter test && flutter build apk --debug
```

| Step | Result |
| --- | --- |
| `flutter pub get` | OK |
| `dart format --set-exit-if-changed` | clean |
| `flutter analyze` | `No issues found!` (a first full run found 20 brace-style infos after formatting; fixed with `dart fix`) |
| `flutter test` | **32 passed** (assignment card, restart persistence, replay after a dropped connection, idempotent duplicate delivery, conflict states, expired session, validation failure; plus 17 from the hardening round: malformed addresses and odd server replies, a stuck-"syncing" note, overlapping saves, sign-out, recovery after a server outage) |
| `flutter build apk --debug` | OK — `mobile/build/app/outputs/flutter-apk/app-debug.apk` (≈181 MB debug build; the first build took ≈13 min while Gradle fetched the NDK/CMake, later ones under a minute) |

Real client against live API (`dart run tool/live_check.dart http://localhost:8000`, tech1 account): sign-in, 5
assigned jobs, the **same note id** returned when the identical command was replayed, a photo uploaded twice
→ one note, reuse of the id with a different body → `409 COMMAND_ID_REUSED`, unknown job → `404`, profile,
notifications, sign-out. It also found a real bug (the inbox listed a reopened job the technician no longer
holds, where notes get `ASSIGNMENT_REVOKED`); the inbox now shows only currently assigned jobs.

## Whole pipeline

`./scripts/verify-all.sh` (backend + web + mobile, exactly the commands above) ran to completion:
`=== ALL CHECKS PASSED ===`, exit code 0. Its first run **failed** at the mobile analyzer step (see above),
which is what the script is for; the second run, after the fix, passed.

## Hardening round (13 Nov 2026)

An adversarial pass over all three parts after the main build. Defects were reproduced first (a failing test, a
script, or on the running system) unless a line says they came from reading the code. Backend and mobile fixes have
regression tests, except the mobile "nothing was changed" message and the appointment label; the web fixes were
re-checked in the browser but have no Jest test.

**API (~400 probes with throw-away scripts against the running server):** sign-in with injection and
type-confusion payloads, forged/expired/revoked tokens, rate limiting, forged `X-Organization-ID`, cross-organization
reads and writes of requests, notes, files and activity, role escalation on every staff endpoint, request-creation
boundaries (lengths, enums, dates, ids), idempotency replay and 8 concurrent creates, out-of-order transitions,
10 parallel cancels (exactly one succeeds, one audit entry), 6 requests racing for one technician slot (exactly one
wins, an overlap by one minute is rejected), upload abuse (PHP/SVG/GIF, oversized dimensions, traversal and odd
filenames, the 3-image limit under 6 parallel uploads), estimate and inventory numeric limits, extreme dates, CORS.

| Found | Fix |
| --- | --- |
| NUL (`\u0000`) in any text field or in a query string → 500 | rejected with 422 (`schemas.Body`, middleware) |
| Assignment slot in year 9999 → 500 | `422 SLOT_TOO_FAR` (more than 2 years ahead) |
| Dashboard/schedule with year-9999 or year-1 dates → 500 | `422 RANGE_INVALID` (1970–2100) |
| Estimate total above the BIGINT range → 500 | `422 ESTIMATE_TOTAL_TOO_LARGE` |
| `%` / `_` in search matched everything (requests, properties, assets, staff, inventory) | escaped (`icontains(..., autoescape=True)`) |
| Inventory codes unique only case-sensitively | unique ignoring case |
| JSON responses lacked `Cache-Control: private, no-store` and `nosniff`, contrary to the docs | added for every response |

**Web:** every modal was rendered as an in-page box (`<dialog open>` skipped `showModal()`), radio buttons were
mis-sized, and `/schedule` had no role guard. All fixed and re-checked in the browser.

**Mobile — code review, an API-client probe, and a sweep on a physical Android phone (USB, `adb reverse`):**
a mistyped server address or odd server reply threw uncaught exceptions and left sign-in spinning; a non-API error
left a queued note in "syncing" until the app restarted; overlapping writes to `state.json` could collide; an action
that succeeded server-side but failed to refresh claimed "nothing was changed"; **Sign out did nothing**
(`CircularDependencyError`: the notifier read a provider that depends on it — seen in the phone's log); once the
app believed it was offline it could not recover from a server-only outage (Refresh was disabled); "Upcoming
appointments" listed past slots. On the device these were then re-checked: sign-in and sign-out (the backend log
shows `POST /auth/logout 200`), jobs, inbox, availability and profile, an online note (one copy on the server), an
offline note → app force-killed → reconnect → exactly one copy, recovery with **Retry**, validation on the materials
and completion screens (no valid submission was made; the job stayed `IN_PROGRESS`), and landscape with no layout
overflow.

**Docker, reviewed statically:** neither build context had a `.dockerignore`, so `COPY . .` would have copied the
host's Windows `backend/.venv` (162 MB) over the image's Linux virtualenv and the host's `web/node_modules` over the
image's — both added now.

## Not run

* `docker compose up` / image builds: the CLI is installed but the engine was not running. The web runtime was
  checked without Docker (see Web); the backend image's start command and health check were not.
* On the phone: camera/gallery photos and the offline photo queue, Accept/Start/Decline/Block/Complete,
  reassignment while offline (E2E-05), marking notifications read, large font sizes.
* E2E-10 (restart of every service and the app, then re-check); keyboard-only and screen-reader passes on the web app.
* Multi-process race tests, and dedicated cross-organization tests for assignment, estimate and material ids.

See `docs/KNOWN_LIMITATIONS.md` for the full list and the reasons.
