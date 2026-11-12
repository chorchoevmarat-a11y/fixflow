# Product Decisions

## Feature: Smart Dispatch Assistant

### Problem Statement

Dispatchers in FixFlow manually evaluated technician availability, skill sets, and current workload across separate screens to make assignment decisions. This process:
- Required 3–5 minutes of context-switching per assignment
- Led to suboptimal assignments (overlooking closer or less-loaded technicians)
- Created scheduling conflicts discovered only after the fact, requiring reassignment
- Scaled poorly — dispatchers managing >20 open requests simultaneously made worse decisions

### Solution: Combined Ranking API Endpoint

**Endpoint**: `GET /api/v1/requests/{request_id}/candidates?start=<iso>&end=<iso>`

Returns a ranked list of technician candidates with a composite `match_score` (0–1) computed from:

| Factor | Weight | Description |
|--------|--------|-------------|
| Skill match | 40% | Fraction of request's required skills the technician holds |
| Availability | 30% | No `ScheduleBlock` overlap in the requested window |
| Workload | 20% | Inverse of active assignment count (fewer = higher score) |
| Proximity | 10% | Inverse of estimated distance (if location data present) |

The dispatcher sees a prioritized shortlist; selecting a candidate auto-fills the assignment form. If the top candidate has a conflict, the ranked list itself serves as the alternative suggestions included in the `409` response.

### Verification Steps

1. **Unit test** (`tests/test_dispatch.py`): Mock technician pool with known skills/workload; assert ranking order matches expected scores.
2. **Integration test**: Seed org with 3 technicians (varying skills/load), call candidates endpoint, assert JSON response order and score fields.
3. **Conflict test**: Book technician #1 for overlapping window, call candidates, assert technician #1 is marked `available: false` and ranked below available candidates.
4. **UI smoke**: Dispatcher opens assignment modal, selects time window, verifies candidate list appears within 500 ms.

---

## Trade-off Decision 1: Scoring in Application Layer vs. SQL

**Options considered**:
- A) Pull all technician data into Python and score in-process
- B) Compute scores entirely in a SQL `WITH` query with weighted expressions
- **Choice: A (application layer)**

**Rationale**: The scoring formula is likely to change frequently (product iteration). Python code is easier to unit-test in isolation, mock, and hot-reload than complex SQL expressions. Performance is acceptable because the candidate pool per org is typically <100 technicians; the query is a single indexed join. We can migrate to SQL if profiling shows it becomes a bottleneck.

---

## Trade-off Decision 2: SSE vs. WebSockets for Real-time Updates

**Options considered**:
- A) Server-Sent Events (SSE) — unidirectional server→client
- B) WebSockets — bidirectional
- **Choice: A (SSE)**

**Rationale**: The web client only needs to *receive* update notifications; all mutations go through REST. SSE works over standard HTTP/1.1, requires no protocol upgrade, is automatically reconnecting in browsers, and is trivially proxied through nginx/Cloudflare. WebSockets would add complexity (connection state management, heartbeating, load-balancer stickiness) for no benefit in this use case.

---

## Trade-off Decision 3: Local SQLite (Drift) vs. In-memory Cache for Mobile Offline

**Options considered**:
- A) Keep fetched jobs in Riverpod in-memory state only
- B) Persist to Drift (SQLite) on device
- **Choice: B (Drift / SQLite)**

**Rationale**: Technicians frequently lose connectivity mid-shift (basements, remote sites). In-memory state is lost on app restart. Drift provides typed, queryable persistence with zero extra infrastructure. The `PendingCommands` table ensures status updates and notes written offline survive app restarts and are replayed in order when connectivity returns. The trade-off is increased binary size (~500 KB) and drift_dev code-generation complexity — both acceptable given the operational reliability gain.
