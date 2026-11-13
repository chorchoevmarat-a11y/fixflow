# Product decisions

## Original workflow improvement: the Smart slot finder

**Problem.** Assigning a technician is the dispatcher's most frequent and most error-prone task. To find a
valid combination they must check the category's required skills, each technician's weekly hours and time
off, existing jobs, and the requester's preferred time — then try a slot and often get a conflict. On the
queue of a busy day this is repeated trial and error across the candidate list and the schedule board.

**Decision.** Add `GET /requests/{id}/suggestions` and a **Smart slot finder** panel at the top of the
assignment form on every triaged request. It proposes up to six bookable (technician, slot) pairs, each with
a one-click **Book this** button.

**Actual behavior.**
* The slot length is the category's default duration (minimum 30 minutes).
* Candidate starts are every full hour, in the organization's timezone, from now over the next 10 days,
  Monday–Saturday. The requester's preferred start (if any) is tried first and the option is badged
  "Matches requested time".
* Every candidate goes through the *same* eligibility function that the assignment endpoint enforces: all
  required skills, inside one availability interval, no time off, no overlap with another active
  assignment, not in the past, technician active. A suggestion therefore books successfully unless somebody
  else takes the slot first, in which case the normal `409 SCHEDULE_CONFLICT` appears.
* At most two options per technician keep the list varied; ties are ordered by earliest start, then by the
  technician's workload that week (less loaded first). The first option is labeled **Best match**.
* The booking uses an idempotency key, so a double click cannot double-book.

**Verification.** `backend/tests/test_scheduling_inventory.py::test_smart_slot_suggestions_are_bookable`
books the top suggestion through the real endpoint and checks that suggestions are refused for non-triaged
requests. In the browser: sign in as `dispatcher@salymbekov.example.com`, open the "Collision candidate" request
(REQ-00044) — the preferred slot is already taken by Farid, so the finder proposes Ilyas Mamytov for that
time instead, plus later alternatives.

## Trade-offs

1. **Server-side sessions instead of JWTs.** Tokens are random strings; only a SHA-256 digest is stored.
   Sign-out, deactivation and expiry take effect immediately and a leaked database does not leak usable
   tokens. Cost: one indexed lookup per request. JWTs would avoid that lookup but cannot be revoked.
2. **Live updates over PostgreSQL LISTEN/NOTIFY + SSE instead of Redis or polling.** No extra service to run,
   events are published inside the committing transaction, and every worker gets every event. Cost:
   notifications are best-effort (payload ≤ 8 kB, lost when a listener is down), so events are only hints and
   clients refetch on reconnect. Redis would scale further but adds infrastructure the brief wants to avoid.
3. **Database-enforced scheduling (exclusion constraint) on top of row locks.** The lock gives clean 409
   messages before a write; the constraint is the guarantee even if code is bypassed. Cost: a technician's
   numeric identity column (`technician_no`) exists solely so a GiST constraint can combine it with the time
   range without the `btree_gist` extension.
4. **SLA state stored as instants on the request.** At-risk/due/overdue are materialized and re-planned when
   the clock changes, which makes filtering ("overdue"), counting and escalation single SQL statements.
   Cost: every event that changes the clock must recompute (pause/resume/priority/calendar are centralized in
   `services/sla.py`).
5. **Composite foreign keys for tenancy.** The database refuses cross-organization references, at the price of
   `(org_id, id)` unique constraints and slightly more verbose models.
6. **Mobile persistence as an atomically-written JSON file instead of SQLite.** The offline data set is small
   (a handful of cached jobs and queued notes), the format is trivially inspectable, there is no native
   dependency, and the persistence logic can be tested on a developer machine by "restarting" a store over
   the same directory. Cost: whole-file rewrites and single-process access; a database would be the right
   choice if the app cached thousands of records.
7. **Notes and photos always go through the queue, even online.** One code path to test, identical behaviour
   online and offline, and a network failure at any moment cannot lose or duplicate a note. Cost: a note shows
   "sending…" for a moment instead of an immediate server response.
8. **Materials and lifecycle actions are online-only on mobile.** Stock is shared and must never be decremented
   from a stale local copy; the UI says why a button is disabled offline instead of faking success.
9. **Spam guard: an identical open request is never filed twice.** If a requester submits a request with the
   same property, asset, category, title and description (compared ignoring case and extra spaces) as one of
   their own requests that is still open (anything except COMPLETED, CLOSED or CANCELED), the API returns that
   original request with `200` and `"deduplicated": true` instead of creating a new one, so dispatchers see a
   single entry rather than a pile of repeats from double-sends, impatient re-submits or retries. Once the
   original is finished or canceled, the same text can be filed again. Cost: a requester cannot deliberately
   file the exact same text twice while the first is open (they should reword it or add detail); near-identical
   wording from different people is still handled by the dispatcher's manual "duplicate" link.
