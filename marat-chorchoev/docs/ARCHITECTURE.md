# Architecture

## Components

```
 Next.js 16 web (3000) ──HTTPS/JSON + SSE──┐
 Flutter Android app  ──HTTPS/JSON─────────┼──►  FastAPI backend (8000, N workers)
                                           │          │ SQLAlchemy 2 (asyncpg)
                                           │          ├──► PostgreSQL 16  (all domain state, sessions, idempotency keys, audit)
                                           │          ├──► uploads volume (evidence images, files named by random key)
                                           │          └──  LISTEN/NOTIFY channel "fixflow_events" (live updates between workers)
 Offline on the phone: JSON state file + attachment copies (unsent notes, cached jobs)
```

* **Backend** (`backend/app`): `api/v1/*` routers (thin: authorization, validation, response shaping),
  `services/*` (rules shared by several routers: request access and transitions, scheduling eligibility,
  SLA clock, inventory consumption, maintenance generation, escalation, files, events, idempotency),
  `models/models.py` (schema), `core/*` (auth dependencies, errors, logging, security primitives),
  `cli.py` (operational commands), `seed.py` (deterministic demo data).
* **Web** (`web/src`): Next.js App Router, all authenticated screens are client components using TanStack
  Query; `lib/api.ts` (fetch + typed errors), `lib/session.ts` (per-tab session), `lib/live.ts` (SSE).
* **Mobile** (`mobile/lib`): Riverpod providers (`core/providers.dart`), `core/sync.dart` (replay engine),
  `core/store.dart` (persistence), screens in `ui/`.

## Database and storage layout

* Schema is created only by Alembic (`backend/alembic/versions/0001_initial_schema.py`); nothing calls
  `create_all`. The migration also installs a trigger that makes `audit_events` append-only.
* 33 tables. Tenant-owned tables carry `org_id`. Money is `BIGINT` minor units, instants are `timestamptz`.
* Evidence files: bytes in `UPLOAD_DIR/<org_id>/<random>.{jpg,png,webp}` (a Docker volume), metadata in
  `evidence_files`. The database never stores paths supplied by users.
* Restart safety: PostgreSQL and uploads are volumes. Sessions, idempotency keys, login attempts and the
  SLA clock state are rows, so nothing important lives in process memory.

## Data flow

**Web.** Browser → `fetch` with `Authorization` + `X-Organization-ID` → router → service → one transaction
(change + audit + notification + `pg_notify`) → commit → response. The web app keeps no state of its own:
every mutation invalidates the organization's TanStack Query cache, and the SSE stream triggers the same
invalidation when *another* user changes something. Cache keys all start with the organization id and the cache is
cleared on organization switch and sign-out; responses carry `Cache-Control: private, no-store`.

**Mobile.** Jobs are fetched online and cached on the device (`state.json`). Online-only actions
(accept, start, block, complete, materials) call the API directly and the screen changes only after the server
accepted them. Notes and photos always go through the **queue**: saved locally first, then delivered by the
sync engine with stable command ids (see `docs/API.md`). The engine runs when a note is saved, when the app
opens, and when connectivity returns.

## Tenant isolation

Defense in depth, so one forgotten filter cannot leak data:

1. **Context.** The bearer token identifies the user; `X-Organization-ID` selects the membership, which is
   looked up on every request (`core/deps.py`). A foreign or unknown organization yields the same
   `403 NOT_A_MEMBER`; deactivated members get `403 MEMBERSHIP_DEACTIVATED` immediately.
2. **Row-level rule.** `services/requests.visibility_clause` is applied in SQL to every request lookup:
   staff see all rows of their organization, a requester only their own, a technician only requests they are
   (or were, for history) assigned to. Wrong org, wrong owner and nonexistent all produce the same `404`.
3. **Database constraints.** Relations between tenant tables are *composite* foreign keys
   `(org_id, x_id) → parent(org_id, id)`; a row can therefore not reference another organization's record even if
   application code tried. Constraints are `DEFERRABLE INITIALLY DEFERRED` so a transaction may write rows in any
   order but cannot commit an inconsistent state.
4. **Per-resource ownership** for notifications (`org_id` + `recipient_id`), files (authorized through their
   request), notes (internal visibility hidden from requesters) and data returned to technicians (no requester email).

Cross-organization denial is exercised for requests, notes, activity, files, assets, inventory, notifications,
reports, audit and the live stream (`tests/test_isolation_and_files.py`).

## Concurrency strategy

| Invariant | Mechanism |
| --- | --- |
| One transition at a time per request | `SELECT … FOR UPDATE` on the request row, then re-check the current status |
| No overlapping active assignments of a technician | (a) row lock on the technician profile serializes scheduling decisions; (b) **exclusion constraint** `ex_assignments_no_overlap` (`int8range(technician_no) && tstzrange(start,end,'[)')` where active) is the storage-level guarantee; the loser receives `409 SCHEDULE_CONFLICT` |
| One active assignment per request; one current/draft estimate | partial unique indexes |
| Estimate decided once | lock request → lock estimate → check `AWAITING_APPROVAL` and version |
| Stock never negative, no double consumption | one conditional `UPDATE … WHERE stock_quantity >= :q RETURNING`; `CHECK (stock_quantity >= 0)`; unique `(org_id, client_command_id)` with a savepoint so a duplicate rolls the decrement back |
| Maintenance generation without duplicates | `INSERT … ON CONFLICT DO NOTHING` on unique `(maintenance_plan_id, occurrence_date)` |
| Escalate once | `UPDATE … WHERE sla_escalated_at IS NULL … RETURNING` flips the flag exactly once, even with parallel schedulers |
| Replay safety | unique command ids / idempotency keys in PostgreSQL |

Nothing relies on in-process locks, so any number of API workers is safe. The container starts 4 workers.

## SLA clock

Business time = organization opening intervals per weekday minus holidays, in the organization's timezone.
The request stores the budget, business seconds consumed so far, when the clock last started, and three
derived instants (at-risk, due, overdue-from). Every start/pause/resume/priority change/calendar change appends
a row to `sla_events` and recomputes those instants, so state can be filtered and counted in SQL
(`sla_state_expr`) with exactly the same answer Python gives. The estimate pause, priority recalculation
("new budget − consumed") and frozen outcome at completion all use the same functions.

## Live updates

`services/events.publish` calls `pg_notify` inside the business transaction, so an event exists only if the
change committed. Each worker holds one LISTEN connection and fans events out to its SSE subscribers filtered by
organization and audience (staff, or specific user ids). A slow consumer or a lost listener connection produces a
`resync` event; clients always refetch canonical state.
