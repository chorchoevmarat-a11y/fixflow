# FixFlow — project notes

Working notes for the team: what the project is, what changed in the rebuild, and what is left.
Source of truth for requirements: `FixFlow_Requirements_261112_170928.pdf` (v2.0). Submission deadline:
**Sunday 15 Nov 2026, 18:00 Asia/Bishkek**; repository access opens 16:00.
Last refreshed: **13 Nov 2026** (after the adversarial testing round described below).

## What the project is

FixFlow is a multi-organization field-service platform: requesters report problems, dispatchers triage and
schedule, admins configure the organization, technicians do the work on Android.

| Part | Stack | Folder |
| --- | --- | --- |
| Backend | Python 3.13+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, uv | `backend/` |
| Web | Next.js 16, React 19, TypeScript (strict), TanStack Query, Bun | `web/` |
| Mobile | Flutter 3.50 (Android), Riverpod, file-backed offline store | `mobile/` |
| Infra | `compose.yaml` (db, backend, web), `scripts/verify-all.sh`, `scripts/smoke.sh` | root |

Start with `README.md` (setup, accounts, commands) and `docs/` (architecture, API, decisions, limitations,
verification, AI usage).

## Why it was rebuilt

The first version did not meet the specification, and the gaps were in the foundations:

* Wrong lifecycle, 6 roles and 5 priorities instead of the specified statuses/4 roles/3 priorities; float money
  instead of integer tyiyn (KGS).
* Almost no role checks: any member could approve estimates, assign technicians or change status.
* Schedule conflicts were check-then-insert (race-prone); no estimate versioning or approval gate; no
  idempotency; SLA was `now + hours`, not business time.
* No migrations (`create_all` at startup), readiness did not check the database, tests ran on SQLite.
* Web on Next 15 / npm; mobile depended on generated code and the old API.
* Docs claimed guarantees (e.g. exclusion constraints) the code did not provide.

## What changed

**Backend (rewritten)**
* 33-table schema via a single Alembic migration; composite `(org_id, id)` foreign keys so records cannot
  link across organizations; append-only audit trigger.
* Server-side revocable sessions (Argon2id passwords), per-request membership check, DB-backed login rate limit.
* Row-level visibility rules per role; uniform 404 for missing/foreign/not-yours.
* Full lifecycle with a transaction-scoped audit entry per transition.
* Scheduling: eligibility (skills, hours, time off), row lock + PostgreSQL exclusion constraint, 409 on conflict.
* Estimates: versions, immutable once submitted, approval gate on starting work, race-safe decisions.
* Inventory: conditional `UPDATE`, never negative, replay-safe, price snapshot.
* Business-hours SLA with holidays, estimate pause, priority recalculation, one-time escalation.
* Preventive maintenance with a unique (plan, date) guard; CLI commands for SLA check and generation.
* Evidence uploads (validated, authorized download), notifications, dashboard/reports, audit API.
* Live updates: SSE over PostgreSQL LISTEN/NOTIFY.
* Deterministic seed that replays history through the real API; `app.cli` (migrate, seed, reset, race demos).

**Web (rewritten)** — role-based shell, requester portal, dispatcher queue/detail/schedule board, admin screens,
dashboard with charts, live refresh, organization-scoped cache, accessible forms, and the original feature:
the **Smart slot finder** (`GET /requests/{id}/suggestions`).

**Mobile (rewritten)** — sign-in with server address and organization picker, job inbox cached for offline use,
job detail with online-only actions disabled offline, notes + photos through a persistent queue with stable
command ids, conflict recovery (keep/retry/discard), materials, completion, availability, notifications.

**Hardening round (13 Nov 2026)** — about 400 adversarial API probes (auth, validation, tenant isolation, roles,
races, uploads, numeric and date limits), a browser pass over the web app, a code review of the mobile app and a
sweep of it on a physical Android phone. Everything found was fixed and has a regression test:
* *Backend:* NUL characters in text or query strings, year-9999 slots/report dates and estimate totals above the
  BIGINT range returned 500 → now 422 (`SLOT_TOO_FAR`, `RANGE_INVALID`, `ESTIMATE_TOTAL_TOO_LARGE`); `%`/`_` in
  search matched every row; inventory codes were case-sensitive; JSON responses lacked the `no-store`/`nosniff`
  headers the docs promised; past preferred-visit windows are rejected; canceled requests leave the default
  list after `CANCELED_HIDE_AFTER_MINUTES` (5).
* *Web:* every modal rendered as a plain in-page box (no backdrop, no focus trap); `/schedule` had no role guard;
  property access can be edited from the properties screen.
* *Mobile:* a mistyped server address or odd server reply crashed sign-in; a non-API error left a note stuck in
  "Sending…"; overlapping saves could collide on the state file; **Sign out did nothing** (circular provider
  dependency); the app could not get back online after a server outage on working Wi-Fi (Refresh was disabled
  while "offline"); "Upcoming appointments" listed past ones.
* *Docker:* added `backend/.dockerignore` and `web/.dockerignore`; without them `COPY . .` would copy the host's
  Windows `.venv` and `node_modules` into the images. **Running the stack found that the backend image crashed on
  start whenever `SEED_ON_START` was set** (a `&&` inside a `${VAR:+...}` expansion was passed to the seed command as
  an argument), so the documented `SEED_ON_START=1 docker compose up` never worked; the `CMD` now uses an `if`,
  and the health check's start period is 120 s to cover the first-start seed.

**Quality** — 52 backend tests (real PostgreSQL, concurrency races), 16 web tests, 32 mobile tests, lint/type
checks everywhere, production web build, smoke test against a 2-worker server. Numbers and commands:
`docs/VERIFICATION.md`.

## What is left to do

Must do before the deadline
1. **Reset the demo data, then record and publish the ~5 minute YouTube demo**, and put the real URL at the top
   of `README.md` (it currently holds a placeholder). Manual testing leaves clutter (canceled probe requests,
   test notes, generated maintenance requests), so first run
   `cd backend && uv run python -m app.cli reset-db --yes-destroy-local-data` (restart the API afterwards).
   The video must show web request creation, dispatcher assignment, the Android app, a backend-driven update,
   a conflict or offline flow, the Smart slot finder, and a test run.
2. **Finish the on-device walk-through.** Done on a physical phone: sign-in/sign-out, jobs/inbox/availability/
   profile, online note, offline note → app killed → reconnect → exactly one note, Retry after a server outage,
   materials and completion validation, landscape. **Still to do:** camera/gallery photos and the offline photo
   queue, Accept/Start/Decline/Block/Complete against a fresh seed, and reassignment while offline → conflict (E2E-05).
3. **Docker stack — done on 13 Nov, repeat before submitting.** Docker Desktop was started and
   `docker compose --progress=plain up --build -d` built both images and ran the stack with demo data on **alternate
   ports** (`.env`, gitignored: `DB_PORT=5433`, `API_PORT=8001`, `WEB_PORT=3001`, `CORS_ORIGINS=http://localhost:3001`,
   `NEXT_PUBLIC_API_URL=http://localhost:8001`, `SEED_ON_START=1`), because the local PostgreSQL service and the dev
   servers use 5432/3000/8000. Results: all three containers healthy, `scripts/smoke.sh` passes against it, all six
   demo roles sign in, the seeded evidence image is served from the uploads volume, CORS matches the web origin, the
   web app works in a browser, and a request plus an uploaded image survive both `docker compose restart` and
   `docker compose down` + `up` (no duplicate seeding). Not done: pointing the phone at the container API, and a run
   with the default ports on a clean machine. To run it again: `docker compose up -d` (add `--build` after code
   changes); `docker compose down -v` wipes the stack's data.
4. **Submission mechanics:** accept the repo invitation (opens 16:00 Sunday), create folder `<name-surname>/`,
   branch `submission/<name-surname>`, copy the project in (no nested git repo), PR titled
   `FixFlow: Name Surname` with links to the README, video and what is/isn't implemented. Do not merge it.
   The project currently lives in `marat-chorchoev/`; confirm the folder name matches the required pattern.

Should do if time allows
* Keyboard-only and screen-reader pass on the web app; the staff, maintenance-plan and organization-settings
  screens were never opened in a browser.
* A multi-process race test (several OS processes) for scheduling/inventory.
* Dedicated cross-organization tests for assignments, estimates and material usage.
* Add a Content-Security-Policy; consider moving the web session out of `sessionStorage`.
* Decide whether `Idempotency-Key` should be required when creating a request (today it is optional, so a raw API
  client that retries without one can create a duplicate; the web app always sends one).
* Mobile: a completion photo retaken after a timeout can be stored twice; one permanently failing note
  (server 5xx) pauses the whole queue behind it; background sync/notifications; editing availability.
* Migrate Flutter from `package:flutter/material.dart` to `material_ui` (deprecation rule is switched off).
* Delete `mobile/tool/live_check.dart` or keep it documented as a manual check (each run adds a note to a job).

Full, honest lists live in `docs/KNOWN_LIMITATIONS.md` and `docs/VERIFICATION.md`.

## Handy commands

```bash
./scripts/verify-all.sh                       # everything the spec requires
./scripts/smoke.sh                            # against a running seeded system
cd backend && uv run python -m app.cli --help # migrate, seed, sla-check, generate-maintenance, reset-db, races
cd mobile && dart run tool/live_check.dart http://localhost:8000   # real Dart client vs live API
```

Run locally without Docker (three terminals; the database must already be running):

```bash
cd backend && uv run uvicorn app.main:app --port 8000     # API on 127.0.0.1 only
cd web && bun run dev                                     # http://localhost:3000
# phone over USB, no Wi-Fi/firewall setup (server address in the app: http://localhost:8000):
adb reverse tcp:8000 tcp:8000
adb install -r mobile/build/app/outputs/flutter-apk/app-debug.apk
```

Restart the API after pulling backend changes — it does not reload by itself, and a stale server was the cause of
confusing "missing endpoint" and "old behaviour" reports before.

Demo password for all seeded accounts: see `README.md` (disposable, demo-only).

## Local environment notes (this machine)

* Flutter SDK cloned to `C:\Users\Azamama\flutter` (3.50.0); Android SDK/JDK from Android Studio.
  `flutter doctor` still reports the Android cmdline-tools/licences, Chrome and Visual Studio as missing; none of
  them blocks `flutter build apk` or running on a USB phone (USB debugging must be allowed on the phone).
* PostgreSQL 16 runs as the Windows service `postgresql-x64-16` (automatic start) on port 5432, with user
  `fixflow` and the databases `fixflow` (the app) and `fixflow_test` (the tests; it is dropped and rebuilt by every
  run). The original build used a throwaway PostgreSQL 16.2 instead. Provide your own with `TEST_DATABASE_URL`
  (database name must end in `_test`).
* Docker Desktop (Docker 29.9.3, Compose 5.7.0, WSL2 backend) is installed; start it from the Start menu before using
  `docker compose`. The container stack, if left running, publishes 5433/8001/3001 (see item 3 above).
* In Git Bash, `adb shell` arguments starting with `/` are rewritten to Windows paths; use `MSYS_NO_PATHCONV=1`.
