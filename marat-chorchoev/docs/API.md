# FixFlow API Reference

Base URL: `http://localhost:8000/api/v1`

All authenticated requests require `Authorization: Bearer <token>` and `X-Organization-ID: <org_id>` headers.

---

## Authentication

### Login

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dispatcher1@org1.fixflow.local","password":"Demo1234!"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Extract token for subsequent calls:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dispatcher1@org1.fixflow.local","password":"Demo1234!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Get Current User

```bash
curl -s http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "id": "usr_01j...",
  "email": "dispatcher1@org1.fixflow.local",
  "full_name": "Alice Dispatcher",
  "organization_id": "org_01j...",
  "role": "DISPATCHER"
}
```

---

## Service Requests

### Create a Request

```bash
curl -s -X POST http://localhost:8000/api/v1/requests \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "HVAC unit not cooling",
    "description": "The main office HVAC has stopped cooling. Temperature is rising above 28C.",
    "priority": "HIGH",
    "category_id": "cat_01j..."
  }'
```

Response `201 Created`:
```json
{
  "id": "req_01j...",
  "title": "HVAC unit not cooling",
  "status": "OPEN",
  "priority": "HIGH",
  "sla_deadline": "2024-01-15T14:00:00Z",
  "sla_breached": false,
  "created_at": "2024-01-15T10:00:00Z"
}
```

### List Requests

```bash
curl -s "http://localhost:8000/api/v1/requests?status=OPEN&priority=HIGH&page=1&size=20" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID"
```

---

## Assignments

### Smart Dispatch — Get Ranked Candidates

```bash
curl -s "http://localhost:8000/api/v1/requests/req_01j.../candidates?start=2024-01-16T09:00:00Z&end=2024-01-16T12:00:00Z" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID"
```

Response:
```json
{
  "candidates": [
    {
      "technician_id": "usr_tech1",
      "full_name": "Bob Technician",
      "match_score": 0.92,
      "skills_match": ["HVAC", "Electrical"],
      "active_jobs": 1,
      "distance_km": 2.4,
      "available": true
    },
    {
      "technician_id": "usr_tech2",
      "full_name": "Carol Expert",
      "match_score": 0.78,
      "skills_match": ["HVAC"],
      "active_jobs": 3,
      "distance_km": 5.1,
      "available": true
    }
  ]
}
```

### Assign with Conflict Detection

```bash
curl -s -X POST http://localhost:8000/api/v1/requests/req_01j.../assign \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "technician_id": "usr_tech1",
    "scheduled_start": "2024-01-16T09:00:00Z",
    "scheduled_end": "2024-01-16T12:00:00Z"
  }'
```

**Success** `201 Created`:
```json
{
  "id": "asgn_01j...",
  "request_id": "req_01j...",
  "technician_id": "usr_tech1",
  "scheduled_start": "2024-01-16T09:00:00Z",
  "scheduled_end": "2024-01-16T12:00:00Z",
  "status": "ASSIGNED"
}
```

**Conflict** `409 Conflict`:
```json
{
  "detail": "Schedule conflict: technician already has assignment 2024-01-16T08:00–11:00",
  "conflict_assignment_id": "asgn_existing...",
  "alternatives": [
    {
      "technician_id": "usr_tech2",
      "full_name": "Carol Expert",
      "match_score": 0.78,
      "available": true
    }
  ]
}
```

---

## Offline Replay (Idempotency)

Mobile clients attach a client-generated UUID as `Idempotency-Key`. If the same key is submitted twice (e.g., network retry after timeout), the backend returns the original response without re-executing the mutation.

```bash
# First submission
curl -s -X POST http://localhost:8000/api/v1/requests/req_01j.../notes \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{"body":"Arrived on site. Fault confirmed in compressor unit."}'

# Duplicate (returns cached 201 response, no DB write)
curl -s -X POST http://localhost:8000/api/v1/requests/req_01j.../notes \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{"body":"Arrived on site. Fault confirmed in compressor unit."}'
```

---

## Real-time Events (SSE)

Connect to the SSE stream to receive live updates for your organization:

```bash
curl -N http://localhost:8000/api/v1/events \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID"
```

Event stream:
```
data: {"event":"REQUEST_CREATED","request_id":"req_01j...","org_id":"org_01j...","ts":"2024-01-15T10:00:00Z"}

data: {"event":"ASSIGNED","request_id":"req_01j...","technician_id":"usr_tech1","ts":"2024-01-15T10:05:00Z"}

data: {"event":"STATUS_CHANGED","request_id":"req_01j...","from":"ASSIGNED","to":"IN_PROGRESS","ts":"2024-01-16T09:03:00Z"}
```

JavaScript client:
```typescript
const es = new EventSource(
  `${process.env.NEXT_PUBLIC_API_URL}/api/v1/events`,
  { withCredentials: true }
);
es.onmessage = (e) => {
  const event = JSON.parse(e.data);
  queryClient.invalidateQueries({ queryKey: ['requests', event.request_id] });
};
```

---

## Health Endpoints

```bash
# Liveness (always 200 if process is up)
curl http://localhost:8000/api/v1/health/live
# {"status":"ok"}

# Readiness (checks DB connection)
curl http://localhost:8000/api/v1/health/ready
# {"status":"ok","db":"connected"}
```
