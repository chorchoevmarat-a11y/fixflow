# Known limitations, risks and unfinished work

This document is deliberately blunt. Nothing listed under "Not done" or "Not verified" is claimed as working.

## Not done

* **Demo video** (README-03/04/05) is not recorded or published; the README carries a placeholder, not a link.
* **Submission mechanics** (shared repository, `submission/<name>` branch, PR) are not done.
* Technician **push/system notifications** on Android: the inbox is fetched when the screen opens and pull-to-refresh;
  there is no background polling, FCM, or SSE on the phone.
* Mobile **availability is read-only**; time off and weekly hours are edited by an admin on the web.
* Intake images can only be attached while a request is `SUBMITTED` or `TRIAGED`.
* No recurring/annual holidays; each holiday date is entered individually.
* The web UI is English only (allowed by the brief). Accessibility was designed in (labels, focus rings, text
  alongside color, skip link, keyboard-operable controls) but not audited with a screen reader.

## Not verified (written, but not exercised in the authoring environment)

* **`docker compose up`** and the two Dockerfiles were never run: the Docker CLI and Compose are installed on the
  authoring machine, but the engine (Docker Desktop) was not running when this was checked. The backend image's
  start command, health checks and both image builds are untested. The same code paths were run natively (API with
  2 workers on PostgreSQL 16, `next build`, and the web standalone output started with `node server.js` exactly as
  the image does). A static review found that neither build context had a `.dockerignore`, so `COPY . .` would have
  copied the host's Windows virtualenv and `node_modules` into the images; both files were added but never exercised.
* **The Android app was only partly walked through on a device.** The debug APK was installed on one physical
  phone (USB, `adb reverse tcp:8000 tcp:8000`, server address `http://localhost:8000`) and driven through sign-in,
  sign-out, jobs, inbox, availability, profile, an online note, an offline note → app killed → reconnect → exactly
  one note (E2E-04), recovery with **Retry**, validation on the materials and completion screens, and landscape.
  **Not done on a device:** camera/gallery photos and the offline photo queue, Accept/Start/Decline/Block/Complete,
  reassignment while offline → conflict (E2E-05), marking notifications read, large font sizes; there is no emulator
  on the authoring machine. Beyond that: the queue, restart persistence, idempotent replay and conflict handling are
  covered by automated tests against a fake server, and the real HTTP client (`mobile/lib/core/api.dart`) was run
  against the live API with `dart run tool/live_check.dart` (each run adds one note to a job).
* **E2E-10** (restart PostgreSQL/API/web/app and re-check everything) was not performed end to end. Individually:
  all state lives in PostgreSQL and volumes by design, and the API process was restarted against the same database
  during development with data intact.
* **Browser coverage:** manual checks in one desktop browser of sign-in, dashboard, queue with filters, request
  detail, smart slot finder, the new-request form, the properties screen and its modals, role guards, sign-out, and
  three pages at phone width (no horizontal overflow). Never opened in a browser: the staff, maintenance-plan and
  organization-settings screens. No keyboard-only or screen-reader audit.
* **Multi-process races:** the concurrency tests fire simultaneous requests inside one process against PostgreSQL;
  the guarantees come from the database (locks and constraints), so they hold across workers, but a test that runs
  several OS processes at once was not written.
* Only some cross-organization denials are asserted one by one (request, notes, activity, files, assets,
  inventory, notifications, reports, audit, stream); assignment/estimate/material-usage ids are protected by the
  same lookups and composite foreign keys but have no dedicated cross-org test.

## Reproducible defects and rough edges

* The seeded demo data has **about 10 overdue requests** (10 on the first run, 11 on 13 Nov: it depends on the
  clock). Several seeded `HIGH` requests were created long enough ago that their business-hour budget is spent.
  That is intentional for the dashboard, but means the overdue notification list is long on a fresh seed.
* Manual testing leaves clutter in the demo database (canceled probe requests, test notes that the API cannot
  delete, generated maintenance requests, probe inventory items). Run `python -m app.cli reset-db
  --yes-destroy-local-data` and restart the API before recording or demonstrating.
* Flutter 3.50 deprecates `package:flutter/material.dart` in favour of a separate `material_ui` package. The
  analyzer rule `deprecated_member_use` is switched off in `mobile/analysis_options.yaml` rather than migrating.
* The web "duplicate request" control takes a pasted request id; there is no search picker.
* A request cannot change category after it is scheduled (unassign first) by design; the UI shows the field disabled.
* Dashboard daily series is bucketed in Python from the timestamps in range (portable across PostgreSQL builds);
  for very large ranges a SQL `GROUP BY` would be cheaper.

## Found during testing, not fixed

* **`Idempotency-Key` is optional when creating a request.** The web app always sends one (a double-clicked Submit
  creates one request), but a raw API client that retries without it can create a duplicate.
* **Mobile:** a completion photo retaken after a timeout gets a new command id and can be stored twice; photos
  already uploaded on the completion screen are only remembered while that screen is open; a note that keeps failing
  with a server error (5xx) pauses the whole queue behind it, retrying forever.
* **Web:** an unknown or malformed request id shows the raw API message with a "Try again" button; signing out
  and back in does not return to the page you were on.
* **Uploads:** an image with trailing bytes after its data is stored byte for byte (served as an image with
  `nosniff`, so it is inert); right-to-left override characters are allowed in file names.
* **Validation leniency:** the API accepts `true` as the number 1 and numeric strings such as `"5"` as integers.
* **Housekeeping:** SQLAlchemy's `.tuples()` is deprecated in three places; one web test prints a React `act()`
  warning; `bun run start` (`next start`) warns that it is unsupported with `output: "standalone"` — the image
  runs `node server.js` instead.

## Risk notes (SEC-09)

| # | Risk | Mitigation (status) | How to verify |
| - | --- | --- | --- |
| 1 | **Double-booked technician under concurrent assignment** | Row lock on the technician + PostgreSQL exclusion constraint `ex_assignments_no_overlap`; loser gets `409 SCHEDULE_CONFLICT`. **Mitigated** | `pytest tests/test_scheduling_inventory.py::test_concurrent_assignments_exactly_one_wins`; `python -m app.cli race-assign` against a running API; `scripts/smoke.sh` (overlap → 409) |
| 2 | **Negative or double-consumed stock** (concurrent consumption, offline retries) | Single conditional `UPDATE … WHERE stock >= q`, `CHECK stock >= 0`, unique command id with savepoint rollback. **Mitigated** | `test_inventory_race_never_goes_negative`, `test_material_consumption_is_atomic_replay_safe_and_snapshots_price` |
| 3 | **Cross-tenant data leak** through a missing filter | Membership checked per request, row-level visibility clause, composite foreign keys, uniform 404, no cache persistence. **Mitigated; partly tested** (see "Not verified") | `pytest tests/test_isolation_and_files.py`; forge `X-Organization-ID` of another org → 403 |
| 4 | **Session token theft** (stored in `sessionStorage` on web, Android keystore on mobile) | Server-side revocable sessions, 12 h expiry, only a digest stored, tokens never logged, security headers/no-store. **Partially mitigated:** a script injected into the web app could still read `sessionStorage`; no CSP is configured yet | `tests/test_isolation_and_files.py::test_login_rate_limit_and_logout_revokes` |
| 5 | **Brute-force sign-in** | 5 failures per email / 50 per IP per 15 min stored in PostgreSQL (works across workers), failures audited. **Mitigated;** locked-out users wait out the window | same test; `429 RATE_LIMITED` |
| 6 | **Lost live events** (listener reconnect, slow client) | Events are hints; `resync` event + refetch on every (re)connect. **Mitigated** | stop/start PostgreSQL while a page is open; the page refetches |
| 7 | **Uploaded file abuse** (type spoofing, bombs, path tricks) | Pillow decode check, size/pixel bounds, random server-generated keys, authorized download, incomplete uploads removed. **Mitigated** | `test_file_upload_validation_and_protected_download` |
| 8 | **Unbounded request bodies** | 1 MiB JSON / ~10.25 MiB multipart cap enforced in ASGI middleware before parsing. **Mitigated** | send an oversized body → `413` |

## Security notes

* CORS allows only the configured origins (`CORS_ORIGINS`) and no credentials; authentication uses bearer tokens,
  not cookies, so there is no CSRF surface.
* Passwords use Argon2id. Passwords, tokens and secrets never appear in logs (structured logs are redacted by
  key name and exception messages are reduced to the exception type).
* The demo password is public by design and only valid for seeded accounts. Do not run the seed on a real system.
