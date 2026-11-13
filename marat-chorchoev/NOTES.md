# FixFlow — project notes

Working notes for the team: what the project is, what changed in the rebuild, and what is left.
Source of truth for requirements: `FixFlow_Requirements_261112_170928.pdf` (v2.0). Submission deadline:
**Sunday 15 Nov 2026, 18:00 Asia/Bishkek**; repository access opens 16:00.

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

**Quality** — 45 backend tests (real PostgreSQL, concurrency races), 15 web tests, 15 mobile tests, lint/type
checks everywhere, `verify-all.sh` passing end to end, smoke test against a 2-worker server.

## What is left to do

Must do before the deadline
1. **Record and publish the ~5 minute YouTube demo**, then put the real URL at the top of `README.md`
   (it currently holds a placeholder). The video must show web request creation, dispatcher assignment, the
   Android app, a backend-driven update, a conflict or offline flow, the Smart slot finder, and a test run.
2. **Run the Android APK on an emulator or phone** and walk through E2E-04/05 (offline note + photo, restart,
   reconnect → exactly one note; reassignment while offline → conflict). Fix whatever this finds.
3. **Run the Docker stack** on a machine with Docker: `SEED_ON_START=1 docker compose up --build -d`, check
   `/api/v1/health/ready`, log in as each role, restart containers and confirm data/evidence survive (E2E-10).
4. **Submission mechanics:** accept the repo invitation (opens 16:00 Sunday), create folder `<name-surname>/`,
   branch `submission/<name-surname>`, copy the project in (no nested git repo), PR titled
   `FixFlow: Name Surname` with links to the README, video and what is/isn't implemented. Do not merge it.
   The project currently lives in `marat-chorchoev/`; confirm the folder name matches the required pattern.

Should do if time allows
* Mobile-width and keyboard-only pass on the web app; requester and admin screens were not manually checked.
* A multi-process race test (several OS processes) for scheduling/inventory.
* Dedicated cross-organization tests for assignments, estimates and material usage.
* Add a Content-Security-Policy; consider moving the web session out of `sessionStorage`.
* Migrate Flutter from `package:flutter/material.dart` to `material_ui` (deprecation rule is switched off).
* Mobile: background sync/notifications, editing availability.
* Delete `mobile/tool/live_check.dart` or keep it documented as a manual check.

Full, honest lists live in `docs/KNOWN_LIMITATIONS.md` and `docs/VERIFICATION.md`.

## Handy commands

```bash
./scripts/verify-all.sh                       # everything the spec requires
./scripts/smoke.sh                            # against a running seeded system
cd backend && uv run python -m app.cli --help # migrate, seed, sla-check, generate-maintenance, reset-db, races
cd mobile && dart run tool/live_check.dart http://localhost:8000   # real Dart client vs live API
```

Demo password for all seeded accounts: see `README.md` (disposable, demo-only).

## Local environment notes (this machine)

* Flutter SDK cloned to `C:\Users\Azamama\flutter` (3.50.0); Android SDK/JDK from Android Studio.
* No Docker and no system PostgreSQL; tests used a throwaway PostgreSQL 16.2 started from a Python package.
  Provide your own with `TEST_DATABASE_URL` (database name must end in `_test`).
