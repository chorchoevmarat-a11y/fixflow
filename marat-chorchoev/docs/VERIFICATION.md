# FixFlow Verification & Testing Guide

This document describes the test strategy, verification suite, and step-by-step procedures to validate all components of FixFlow.

---

## 1. Automated Verification Suite (`verify-all.sh`)

FixFlow provides a single command to execute the full test and lint suite across all three delivery units:

```bash
./scripts/verify-all.sh
```

This script performs:
1. **Backend**: Dependency check, Ruff linting, Ruff formatting check, type checking (`ty check`), and Pytest test suite execution.
2. **Web**: Bun dependencies validation, ESLint linting, TypeScript typecheck (`tsc --noEmit`), Jest/React Testing Library unit tests, and Next.js production build (`next build`).
3. **Mobile**: Flutter dependencies (`pub get`), Dart formatting check, Flutter analyzer (`flutter analyze`), unit/widget tests (`flutter test`), and debug APK build.

---

## 2. Backend Verification

### Unit & Integration Tests (Pytest)
Execute all tests using `uv`:
```bash
cd backend
uv run pytest -v
```

### Test Areas Covered:
- **Authentication & RBAC**:
  - Valid login returns JWT with claims (`sub`, `org_id`, `role`).
  - Invalid password returns 401 Unauthorized.
  - Role-based permissions enforce access rules (e.g. `REQUESTER` cannot assign jobs).
- **Multi-Tenant Isolation**:
  - Queries for requests, assignments, notes, and evidence are strictly isolated by `org_id`.
  - Supplying a header for Org A with a user belonging to Org B yields 403 Forbidden.
- **Assignment & Concurrency**:
  - Assigning a technician creates a schedule block.
  - Overlapping assignment attempts return `409 Conflict` with conflict details and candidate alternatives.
  - Concurrent assignment requests serialized by transactional locks without deadlocks.
- **Idempotency**:
  - Repeating a mutation with identical `Idempotency-Key` returns identical cached payload without creating duplicate database rows.
- **Health Checks**:
  - `/api/v1/health/live` returns 200 OK.
  - `/api/v1/health/ready` validates database connectivity and returns 200 OK.

---

## 3. Web Frontend Verification

### Lint & Typecheck
```bash
cd web
bun run lint
bun run typecheck
```

### Unit & Component Tests
```bash
cd web
bun run test
```

### Build Verification
```bash
cd web
bun run build
```

### Verification Scenarios:
- **Authentication Flow**: Login form validation, cookie storage, session restore, route guards.
- **Dispatcher Dashboard**: Request table rendering, status filtering, priority badges, SLA indicators.
- **Assignment Modal**: Technician candidate list rendering, match score indicators, conflict feedback alert.
- **Real-time SSE Listener**: Event processing on `REQUEST_CREATED` and `STATUS_CHANGED`, optimistic cache invalidation.

---

## 4. Mobile Client Verification

### Static Analysis & Formatting
```bash
cd mobile
dart format --output=none --set-exit-if-changed lib test
flutter analyze
```

### Widget & Unit Tests
```bash
cd mobile
flutter test
```

### Key Test Coverage:
- `jobs_test.dart`: Assignment inbox rendering, status chip colors, pull-to-refresh.
- `offline_queue_test.dart`: SQLite command queueing when network is disconnected.
- `idempotency_test.dart`: Replay of pending commands with consistent UUID keys upon network reconnection.
- `conflict_test.dart`: Handling 409 responses from server and displaying conflict recovery dialog.

---

## 5. End-to-End Smoke Verification (`smoke.sh`)

Ensure services are running (`docker compose up -d`) and execute:

```bash
./scripts/smoke.sh
```

### Sequence of Checks:
1. **Liveness Probe**: Confirms API process is alive.
2. **Readiness Probe**: Confirms database connection pool is active.
3. **Requester Authentication**: Authenticates demo user and extracts Bearer JWT.
4. **Current User Profile**: Fetches `/api/v1/auth/me` to determine active organization.
5. **Work Order Creation**: Creates a new service request and verifies 201 Created response.
6. **Cross-Tenant Isolation Gate**: Tries to access Org 1 request using Org 2 credentials; asserts `403 Forbidden`.

---

## 6. Verification Matrix Summary

| Test Area | Tooling | Success Criteria |
|---|---|---|
| Backend Lint & Format | `ruff check`, `ruff format` | 0 errors, 0 warnings |
| Backend Types | `ty check` | 0 type errors |
| Backend Tests | `pytest` | 100% pass rate |
| Web Lint & Types | `eslint`, `tsc` | Clean exit, no errors |
| Web Tests | `jest` / RTL | All test suites passing |
| Web Build | `next build` | Optimized production bundle generated |
| Mobile Lint & Format | `flutter analyze`, `dart format` | No issues found |
| Mobile Tests | `flutter test` | All unit & widget tests pass |
| Smoke Tests | `smoke.sh` | All steps OK, isolation verified |
