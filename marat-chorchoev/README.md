# FixFlow — field service operations platform

> **Demo video:** _not published yet._ The YouTube link goes here before the deadline (README-03).
> This line is a deliberate placeholder, not a link.

FixFlow serves requesters, dispatchers, organization admins and technicians of several independent
service organizations from one product: a Python/PostgreSQL backend, a Next.js web app and a Flutter
Android app that all use the same live records.

## Feature status

| Area | Status |
| --- | --- |
| Multi-organization tenancy, 4 roles, explicit organization selection, deactivation | Implemented, tested |
| Request lifecycle (SUBMITTED → … → CLOSED, rework, decline, block), audit per transition | Implemented, tested |
| Scheduling: skills, availability, time off, 30-min minimum, DB-enforced no-overlap, 409 on conflict | Implemented, tested (incl. concurrent attempts) |
| Estimates: versions, immutability, approval gate, race-safe decisions | Implemented, tested |
| Inventory: atomic, non-negative, replay-safe consumption, price snapshot, low stock | Implemented, tested |
| Business-time SLA, holidays, estimate pause, one-time overdue escalation, CLI | Implemented, tested |
| Preventive maintenance with unique (plan, date) guard, CLI | Implemented, tested |
| Notes, evidence images (validated, authorized download), notifications, activity timeline | Implemented, tested |
| Live updates (Server-Sent Events over PostgreSQL LISTEN/NOTIFY) | Implemented; manually checked, one automated isolation check |
| Web app (requester, dispatcher, admin workspaces, dashboard, charts, schedule board) | Implemented; 16 automated tests; browser-checked as dispatcher and requester (staff, maintenance and organization-settings screens not yet) |
| **Original feature: Smart slot finder** (see `docs/PRODUCT_DECISIONS.md`) | Implemented, tested |
| Android app: sign-in, jobs, detail, notes + photos offline queue, conflicts, materials, availability, inbox | Implemented; 32 automated tests; **run on one physical phone** (sign-in/out, jobs, offline note queue); photo flows and job state changes **not yet walked through on a device** |
| Docker Compose stack | Implemented; **run on 13 Nov 2026**: both images build, the stack starts and seeds, `scripts/smoke.sh` passes against it, data and uploads survive a restart and a `down`/`up` (on alternate ports; see `docs/VERIFICATION.md`) |
| Demo video | **Not done** |

Everything that is incomplete or unverified is listed in [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).

## Prerequisites (versions actually used)

| Tool | Version used | Needed for |
| --- | --- | --- |
| Docker + Compose v2 | Docker 29.9.3 / Compose 5.7.0 (Docker Desktop, WSL2 backend) | one-command stack |
| [uv](https://docs.astral.sh/uv/) | 0.11.19 | Python env (Python ≥ 3.13; tested on 3.14.5) |
| PostgreSQL | 16 (tests ran on 16.2, later the Windows service `postgresql-x64-16`) | database |
| [Bun](https://bun.sh) | 1.4.4 | web install/scripts |
| Node.js | 26.13 (any 22+ works for `next`) | Next.js runtime, smoke script |
| Flutter | 3.50.0 stable (Dart 3.14) | Android app |
| Android SDK | platforms 35/36, build-tools 34–36, JDK 21 (Android Studio) | APK |

## Quick start (Docker)

```bash
cp .env.example .env                # optional; defaults work. Never commit .env
SEED_ON_START=1 docker compose up --build -d   # db → backend (migrates, seeds) → web
curl http://localhost:8000/api/v1/health/ready  # {"status":"ok",...}
```

| Service | Address |
| --- | --- |
| Web app | http://localhost:3000 |
| API | http://localhost:8000 |
| OpenAPI (Swagger) | http://localhost:8000/api/v1/docs |
| PostgreSQL | localhost:5432 (user/db `fixflow`) |

Ports and credentials can be overridden through `.env` (`WEB_PORT`, `API_PORT`, `DB_PORT`, `POSTGRES_*`). If something
on this machine already uses 5432/8000/3000 (a local PostgreSQL, the dev servers), pick other ports and keep the
browser-visible addresses consistent, e.g. `DB_PORT=5433 API_PORT=8001 WEB_PORT=3001
CORS_ORIGINS=http://localhost:3001 NEXT_PUBLIC_API_URL=http://localhost:8001` (the web build bakes in
`NEXT_PUBLIC_API_URL`, so changing it needs `--build`).
Startup needs no manual sleeps: the backend waits for PostgreSQL, applies Alembic migrations, then serves
with 4 workers; `web` starts after the backend reports ready. Data lives in the `postgres_data` and
`uploads_data` volumes and survives `docker compose stop/start`.

Seed once (idempotent; safe to repeat):

```bash
docker compose exec backend uv run --no-sync python -m app.cli seed
```

**Reset the demo environment (destroys all local data):**

```bash
docker compose down -v && SEED_ON_START=1 docker compose up --build -d
```

## Quick start (without Docker)

```bash
# 1. PostgreSQL 16 with an empty database, e.g. postgresql://fixflow:fixflow@localhost:5432/fixflow
# 2. Backend
cd backend
uv sync
export DATABASE_URL=postgresql+asyncpg://fixflow:fixflow@localhost:5432/fixflow
export UPLOAD_DIR=./uploads
uv run python -m app.cli migrate          # alembic upgrade head
uv run python -m app.cli seed             # deterministic demo data
uv run uvicorn app.main:app --port 8000 --workers 4   # listens on 127.0.0.1 only (see the phone note below)
# 3. Web (new terminal)
cd web && bun install && bun run dev      # http://localhost:3000
```

Restart the API after changing backend code (it does not reload by itself). To start from a clean demo state:
`uv run python -m app.cli reset-db --yes-destroy-local-data`, then restart the API.

Other operational commands (run from `backend/`; in Docker prefix with `docker compose exec backend uv run --no-sync`):

| Command | Purpose |
| --- | --- |
| `python -m app.cli wait-for-db` | block until PostgreSQL accepts connections |
| `python -m app.cli sla-check` | detect overdue requests and create escalations (safe to repeat) |
| `python -m app.cli generate-maintenance --date 2026-11-20` | generate due preventive-maintenance requests |
| `python -m app.cli reset-db --yes-destroy-local-data` | **destructive**: drop all tables, migrate, re-seed. Refuses non-local hosts |
| `python -m app.cli race-assign` | development-only: two simultaneous assignments for one slot → one 200, one 409 |

## Demo accounts (disposable, demo-only)

All accounts share the password **`FixFlow-Demo-2026!`**. They exist only in seeded demo data; never reuse this password.

| Organization | Role | Email |
| --- | --- | --- |
| Ala-Too Facility Services | Admin | `admin@alatoo.example.com` |
| | Dispatcher | `dispatcher@alatoo.example.com` |
| | Requesters | `requester1@alatoo.example.com` … `requester3@…` |
| | Technicians | `tech1@alatoo.example.com` … `tech4@…` |
| Issyk-Kul Property Care | Admin | `admin@issykkul.example.com` |
| | Requesters | `requester1@issykkul.example.com`, `requester2@…` |
| | Technicians | `tech1@issykkul.example.com`, `tech2@…` |
| **Both** | Dispatcher in Ala-Too, requester in Issyk-Kul | `multi@fixflow.example.com` |

Seed data: 2 organizations, 15 users, 10 properties, 15 assets, 8 categories, 20 inventory items,
59 requests (every status and priority, estimate states, evidence, feedback, asset history, overdue items,
a collision candidate), 4 maintenance plans (one already due), low-stock items.

## Android app

```bash
cd mobile
flutter pub get
flutter build apk --debug          # → mobile/build/app/outputs/flutter-apk/app-debug.apk
adb install -r build/app/outputs/flutter-apk/app-debug.apk
```

* **Emulator:** the default server address `http://10.0.2.2:8000` reaches the API on your computer.
* **Physical phone, USB (simplest; this is how it was tested):** enable USB debugging, run
  `adb reverse tcp:8000 tcp:8000` and type `http://localhost:8000` into the **Server address** field on the
  sign-in screen. No Wi-Fi or firewall setup is needed. If `adb devices` says `unauthorized`, accept the prompt on
  the phone. (In Git Bash prefix `adb shell` commands that contain a `/path` with `MSYS_NO_PATHCONV=1`.)
* **Physical phone, Wi-Fi:** the API must listen on the network, so start it with `--host 0.0.0.0` (the quick
  start above binds `127.0.0.1`, which a phone cannot reach), put the phone and the computer on the same Wi-Fi,
  allow port 8000 through the computer's firewall and type `http://<computer-LAN-IP>:8000` into the **Server
  address** field. The address is stored on the device, so nothing is baked into the APK. A build-time default
  can be set with `--dart-define=API_BASE_URL=http://192.168.1.20:8000`.
* Sign in as a technician (e.g. `tech1@alatoo.example.com`). Dispatchers and requesters use the web app.
* Offline demo: open a job while online, turn on airplane mode, write a note and attach a photo
  (**Pending sync** appears), restart the app, turn the network back on — it is delivered exactly once.
  If only the server was unreachable (Wi-Fi stayed on), no network event fires: tap **Retry** in the offline
  banner (or pull to refresh) and the queue is sent.

## Tests and checks

```bash
./scripts/verify-all.sh            # backend + web + mobile, fails if any step fails
```

or per component (these are the exact commands from the specification):

```bash
(cd backend && uv sync --frozen && uv run ruff check . && uv run ruff format --check . && uv run ty check . && uv run pytest -q)
(cd web && bun install --frozen-lockfile && bun run lint && bun run typecheck && bun run test:ci && bun run build)
(cd mobile && flutter pub get && dart format --output=none --set-exit-if-changed lib test && flutter analyze && flutter test && flutter build apk --debug)
```

Backend tests need a real PostgreSQL. Provide it with `TEST_DATABASE_URL`; the database name **must end
in `_test`** (the suite drops all its tables and refuses to run otherwise):

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://fixflow:fixflow@localhost:5432/fixflow_test
```

Smoke test of a running, seeded system through real HTTP (positive lifecycle + expected 403/404/409/401):

```bash
./scripts/smoke.sh                 # API_URL=http://localhost:8000 by default; needs bash, curl, node
```

What was actually run and what passed is recorded honestly in [`docs/VERIFICATION.md`](docs/VERIFICATION.md).

## Documentation

* [Architecture](docs/ARCHITECTURE.md) — components, storage, data flow, tenant isolation, concurrency
* [API](docs/API.md) — endpoint overview and runnable example flows
* [Product decisions](docs/PRODUCT_DECISIONS.md) — the original feature and trade-offs
* [Known limitations](docs/KNOWN_LIMITATIONS.md) — incomplete items, risks, mitigations
* [Verification](docs/VERIFICATION.md) — commands run and observed results
* [AI usage](docs/AI_USAGE.md)

## Repository layout

```
backend/   FastAPI, SQLAlchemy 2, Alembic, tests      web/      Next.js 16, React, TypeScript (strict), Bun
mobile/    Flutter (Riverpod, file-backed store)       scripts/  verify-all.sh, smoke.sh
docs/      the six required documents                  compose.yaml, .env.example
```
