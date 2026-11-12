# AI Usage & Collaboration Disclosure

## Overview

This project was developed with assistance from state-of-the-art AI foundation models, primarily **Anthropic Claude 3.7 Sonnet / Claude Sonnet 4.6** and Google DeepMind systems, functioning in an agentic swarm workflow.

---

## AI Tools & Workflow

### 1. Primary Model Architecture
- **Model**: Claude Sonnet 4.6 / Claude 3.7 Sonnet
- **Role**: Architecture design, schema modeling, API contract authoring, implementation of backend services, frontend web components, mobile Flutter client, automated tests, and deployment configuration.
- **Workflow Paradigm**: Multi-agent coordinated swarm with specialized personas:
  - `coordinator`: Orchestration, specification decomposition, peer review.
  - `infra`: Directory scaffolding, Docker Compose orchestration, environment configuration, and core architectural documentation.
  - `backend`: FastAPI async REST endpoints, SQLAlchemy ORM models, Alembic migrations, PostgreSQL conflict locking, and pytest suites.
  - `web`: Next.js 15 App Router interface, Tailwind CSS layout, TanStack Query state handling, and SSE subscription.
  - `mobile`: Flutter 3.22 mobile application, Drift offline database, queue replay manager, Riverpod state, and widget testing.

---

## Areas of AI Contribution

| Domain | AI Contribution | Human Oversight & Validation |
|---|---|---|
| **System Architecture** | Multi-tenant schema design, GiST range locking strategy, SSE event broker topology | Evaluated trade-offs between SSE and WebSockets, selected database-backed locking |
| **Backend Implementation** | FastAPI dependency injection, Pydantic v2 schemas, asyncpg session lifecycle | Reviewed SQL query generation, ensured strict `org_id` filtering on all models |
| **Concurrency & Idempotency** | PostgreSQL `SELECT FOR UPDATE` pattern, UUIDv4 replay handling | Verified isolation levels, validated conflict response contracts (HTTP 409) |
| **Web Frontend** | Component hierarchy, Next.js 15 routing, SSE auto-reconnect logic | Checked UI responsiveness, form validation, and accessibility standards |
| **Mobile Client** | Drift SQLite table definitions, Riverpod state notifiers, Dio interceptor | Checked offline command queue durability and replay semantics |
| **Verification & Documentation** | Bash test orchestrator (`verify-all.sh`), E2E smoke tests (`smoke.sh`), API specifications | Ran and verified test scripts against running local containers |

---

## Verification & Guardrails

To guarantee code quality, reliability, and security of AI-generated artifacts:
1. **Automated Linters & Static Analysis**: Every file was subject to `ruff` (backend), `eslint` / `tsc` (web), and `flutter analyze` / `dart format` (mobile).
2. **Automated Test Suites**: Unit and integration test suites were generated and executed for all critical business logic, specifically targeting multi-tenancy isolation and concurrency conflict handling.
3. **No Unchecked Assumptions**: All configuration values and environment variables were centralized in `.env.example` and verified against Docker Compose definitions.
