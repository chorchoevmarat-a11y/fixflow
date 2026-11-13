# FixFlow API

Base URL `http://localhost:8000/api/v1`. Interactive OpenAPI: `/api/v1/docs` (Swagger), `/api/v1/redoc`,
machine-readable `/api/v1/openapi.json`.

## Conventions

* **Auth:** `Authorization: Bearer <token>` from `POST /auth/login`. Tokens are opaque; only a SHA-256
  digest is stored server-side, sessions expire (default 12 h) and are revoked by `POST /auth/logout`.
* **Organization:** every protected call sends `X-Organization-ID: <uuid>`. The server checks the caller's
  active membership in that organization on *every* request. A role in organization A grants nothing in B.
* **Errors:** always `{"error": {"code": "...", "message": "...", "details": {...}?}, "request_id": "..."}`.
  `400` malformed, `401` no/invalid/expired/revoked session, `403` forbidden role or membership, `404`
  missing *or not visible to you*, `409` state/concurrency/idempotency conflict, `413` too large, `422`
  validation (`details.fields[]`), `429` rate limited, `503` database unavailable.
* **Pagination:** `?page=1&page_size=20` (max **100**) → `{items,total,page,page_size,total_pages}`.
* **Money:** integer minor units (tyiyn), currency `KGS`. **Times:** UTC ISO-8601 instants; display uses the
  organization's IANA timezone (seed default `Asia/Bishkek`).
* **Idempotency:** see [Retries and idempotency](#retries-and-idempotency).

## Endpoint overview

| Area | Endpoints |
| --- | --- |
| Health | `GET /health/live`, `GET /health/ready` (503 when the database is down or unmigrated) |
| Auth / memberships | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Organizations / staff | `GET·PATCH /organization`, `PUT /organization/business-hours`, `POST·DELETE /organization/holidays[/{id}]`, `GET·POST /staff`, `PATCH /staff/{membership_id}` |
| Properties / assets | `GET·POST /properties`, `PATCH /properties/{id}`, `GET·POST /assets`, `GET·PATCH /assets/{id}`, `GET /assets/{id}/history` |
| Categories / skills | `GET·POST /categories`, `PATCH /categories/{id}`, `GET·POST /skills`, `DELETE /skills/{id}` |
| Technicians / availability | `GET /technicians`, `GET /technicians/me`, `PUT /technicians/{id}` (skills, weekly hours), `POST·DELETE /technicians/{id}/time-off[/{id}]`, `GET /schedule` |
| Requests / lifecycle | `GET·POST /requests`, `GET /requests/{id}`, `GET /requests/{id}/activity`; transitions `triage`, `reclassify`, `duplicate`, `assign`, `reschedule`, `unassign`, `accept`, `decline`, `start`, `block`, `unblock`, `complete`, `close`, `reopen`, `cancel`, `feedback` (all `POST /requests/{id}/<name>`) |
| Assignment helpers | `GET /requests/{id}/candidates?start_at&end_at`, `GET /requests/{id}/suggestions` (smart slot finder) |
| Estimates / approvals | `GET /estimates`, `GET·POST /requests/{id}/estimates`, `PUT·DELETE /estimates/{id}`, `POST /estimates/{id}/submit·approve·reject·withdraw` |
| Inventory / usage | `GET·POST /inventory`, `PATCH /inventory/{id}`, `POST /inventory/{id}/stock-additions`, `GET /inventory/{id}/movements`, `GET·POST /requests/{id}/materials` |
| Maintenance plans | `GET·POST /maintenance-plans`, `GET·PATCH /maintenance-plans/{id}`, `POST /maintenance-plans/generate` |
| Notes / files | `GET·POST /requests/{id}/notes`, `GET·POST /requests/{id}/files` (multipart), `GET /files/{id}/content` |
| Notifications | `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all` |
| Reports | `GET /reports/dashboard?date_from&date_to&category_id&technician_id` |
| Audit | `GET /audit?action=&actor_id=&request_id=&date_from=&date_to=` (admin) |
| Live updates | `GET /stream` (Server-Sent Events) |

## Example flows (curl)

The examples use the disposable demo accounts from the README.

### 1. Authenticate

```bash
curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"requester1@alatoo.example.com","password":"FixFlow-Demo-2026!"}'
```
```json
{ "access_token": "…", "token_type": "bearer", "expires_at": "2026-11-14T03:00:00+00:00",
  "user": {"id": "…", "email": "requester1@alatoo.example.com", "full_name": "Cholpon Ismailova"},
  "memberships": [{"membership_id": "…", "organization_id": "0681d9b4-…", "organization_name": "Ala-Too Facility Services",
                   "timezone": "Asia/Bishkek", "currency": "KGS", "role": "REQUESTER", "technician_id": null}] }
```

Failed sign-ins return `401 INVALID_CREDENTIALS`; after 5 failures per email in 15 minutes the API answers
`429 RATE_LIMITED`. A person with several memberships picks one explicitly by sending its
`organization_id` in `X-Organization-ID`; `GET /auth/me` returns the current membership.

### 2. Create a request

```bash
TOKEN=…; ORG=0681d9b4-…
curl -s -X POST localhost:8000/api/v1/requests \
  -H "Authorization: Bearer $TOKEN" -H "X-Organization-ID: $ORG" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: create-req-2026-0001' \
  -d '{"title":"Air handler is making noise","description":"The rooftop unit rattles loudly whenever the fan starts.",
       "category_id":"<category>","property_id":"<property>","asset_id":"<asset>","priority":"HIGH"}'
```
`201` with the request detail: `reference` (`REQ-00060`), `status: SUBMITTED`, `sla` (HIGH = 8 business
hours), and `allowed_actions`. Title must be 5–120 and description 20–3000 characters, otherwise
`422 {"error":{"code":"VALIDATION_ERROR","details":{"fields":[{"field":"title","message":"…"}]}}}`. A property
or asset the caller may not use is rejected with `422 PROPERTY_NOT_ALLOWED` / `ASSET_NOT_ALLOWED`.

### 3. Assign (dispatcher) and the conflict response

```bash
curl -s -X POST localhost:8000/api/v1/requests/$RID/assign -H "Authorization: Bearer $DISPATCHER" \
  -H "X-Organization-ID: $ORG" -H 'Content-Type: application/json' -H 'Idempotency-Key: assign-0001' \
  -d '{"technician_id":"<technician profile id>","start_at":"2026-11-18T08:00:00Z","end_at":"2026-11-18T10:00:00Z"}'
```
`200` → request is `SCHEDULED`, the technician gets an `ASSIGNMENT_NEW` notification, one audit entry is
written — all in one transaction. If the technician already holds an overlapping slot (half-open
intervals: 10:00–11:00 and 11:00–12:00 do **not** overlap) the loser of a race gets:

```http
HTTP/1.1 409 Conflict
{ "error": { "code": "SCHEDULE_CONFLICT",
             "message": "The technician already has a job in this time slot.",
             "details": { "conflicts": [{"request_id": "…", "reference": "REQ-00043",
                                         "title": "Replace lobby light fittings",
                                         "start_at": "2026-11-18T08:00:00+00:00", "end_at": "2026-11-18T10:00:00+00:00"}] } },
  "request_id": "…" }
```
Other assignment outcomes: `422 TECHNICIAN_NOT_ELIGIBLE` (missing skills, outside availability, time off —
`details.reasons[]`), `422 SLOT_IN_PAST | SLOT_TOO_SHORT`, `409 INVALID_TRANSITION` (request not `TRIAGED`).
`GET /requests/{id}/candidates?start_at=…&end_at=…` lists every technician with eligibility, workload and
conflict reasons; `GET /requests/{id}/suggestions` proposes the earliest bookable slots.

### 4. Offline replay (what the Android app sends)

A technician writes a note offline. The app stores it with a stable `client_command_id` and, when the
connection returns, replays it. Sending the identical command any number of times stores **one** note:

```bash
CMD=note-3f1c9d7e-5b0a-4f55-9a0e-2d7e8c1b6a11
curl -s -X POST localhost:8000/api/v1/requests/$RID/notes -H "Authorization: Bearer $TECH" -H "X-Organization-ID: $ORG" \
  -H 'Content-Type: application/json' \
  -d "{\"body\":\"Belt is worn; replacement needed.\",\"client_command_id\":\"$CMD\",\"assignment_id\":\"<assignment the app cached>\"}"
# first delivery  -> 201 {"id": "…"}
# replay          -> 200 {"id": "<same id>"}   header: Idempotency-Replayed: true
# same id, different text -> 409 COMMAND_ID_REUSED
```
Photos use `POST /requests/{id}/files` (multipart: `file`, `kind=NOTE`, `note_id`,
`client_command_id=<CMD>-img-<n>`); the same replay rules apply per photo. If the job was reassigned,
closed, or access was lost before the replay, the server answers `409 ASSIGNMENT_REVOKED`,
`409 REQUEST_CLOSED` or `404` and **stores nothing** — the app keeps the draft, shows the reason, and
asks the person to decide.

## Retries and idempotency

| Command | Mechanism |
| --- | --- |
| Work notes, material usage, evidence files | `client_command_id` in the body/form, unique per organization in PostgreSQL (`uq_work_note_command`, `uq_material_usage_command`, `uq_evidence_command`). A payload hash detects reuse with different content (`409 COMMAND_ID_REUSED`). |
| Request creation, assignment, reschedule, estimate approve/reject, maintenance generation | `Idempotency-Key: <8–100 chars>` header. Key + payload hash are stored in `idempotency_keys` in the **same transaction** as the command; a replay returns the stored response (`Idempotency-Replayed: true`), a different payload under the same key returns `409 IDEMPOTENCY_KEY_REUSED`, and a failed command rolls its key back so it can be retried. |

All of it lives in PostgreSQL, so it survives restarts and works across API workers.

## Other contracts worth knowing

* **Estimate gate:** `POST /requests/{id}/start` → `409 ESTIMATE_NOT_APPROVED` while the current estimate is
  `AWAITING_APPROVAL` or `REJECTED`. Approve/reject must name the version the requester saw
  (`{"version": 2}`), otherwise `409 ESTIMATE_VERSION_MISMATCH`; the second of two simultaneous decisions gets
  `409 ESTIMATE_ALREADY_DECIDED`.
* **Inventory:** `POST /requests/{id}/materials` → `409 INSUFFICIENT_STOCK` (`details.available`), nothing is written.
* **Files:** JPEG/PNG/WebP, ≤ 10 MiB, content verified, pixel bounds enforced. Downloads
  (`GET /files/{id}/content`) are authorized on every call (`Cache-Control: private, no-store`); there are no public URLs.
* **Live updates:** `GET /stream` sends the same auth headers. Events carry ids only (`request.updated`,
  `notification.created`, `inventory.updated`). A `ready` event follows connect and a `resync` event means
  "events may have been missed" — in both cases re-fetch what is on screen. An `unauthorized` event ends the stream.
