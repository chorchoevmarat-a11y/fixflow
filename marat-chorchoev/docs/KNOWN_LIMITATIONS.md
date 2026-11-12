# Known Limitations & Security Considerations

This document outlines known limitations, trade-offs, security considerations, and potential areas for future enhancement in the FixFlow platform.

---

## Security Risks & Mitigations

### Risk 1: File Upload MIME Spoofing
- **Risk**: Malicious actors may attempt to upload executable binaries, scripts, or SVG files with embedded JavaScript disguised as safe image or PDF attachments (e.g. naming an executable `invoice.pdf` or forging the HTTP `Content-Type` header).
- **Impact**: Stored XSS, remote code execution if executed on host, or client-side compromise when downloaded by dispatchers/technicians.
- **Mitigation**:
  - Upload endpoints inspect file magic bytes using `python-magic` rather than relying solely on client-provided `Content-Type` headers.
  - File extensions are sanitized and strictly validated against an allowlist (`.png`, `.jpg`, `.jpeg`, `.pdf`, `.heic`).
  - Stored files are renamed using client-detached UUIDs and written into tenant-isolated directory trees (`/app/uploads/{org_id}/{request_id}/{uuid}.{ext}`).
  - Files are served through authenticated streaming endpoints with strict headers: `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and restrictive Content Security Policy (CSP).

### Risk 2: JWT Revocation & Session Invalidation
- **Risk**: Standard stateless JSON Web Tokens (HS256) cannot be revoked centrally prior to their expiration timestamp without maintaining server-side state.
- **Impact**: If a user is deactivated, removed from an organization, or has their credentials leaked, an issued token remains valid until `ACCESS_TOKEN_EXPIRE_MINUTES` expires.
- **Mitigation**:
  - Short token lifetimes (default 60 minutes) minimize the window of vulnerability.
  - Revocations and role changes emit an `AuditEvent` logging the event.
  - For immediate revocation of compromised accounts, an in-memory or Redis-backed token blacklist check can be enabled in `get_current_user` dependencies.
  - Tenant membership is checked in the database during sensitive mutations to ensure membership status is active regardless of token validity.

### Risk 3: Concurrent Schedule Writes Under Extreme Load
- **Risk**: High-concurrency automated dispatch engines or multiple dispatchers assigning technicians simultaneously to the exact same slot may encounter database deadlocks or race conditions if lock ordering is non-deterministic.
- **Impact**: Transient `500` or `409` errors under heavy burst traffic, or potential double-booking if locking is bypassed.
- **Mitigation**:
  - Schedule windows use transactional `SELECT FOR UPDATE` on technician schedule blocks to serialize conflicting slot reservations.
  - PostgreSQL exclusion constraints using GiST indexing (`btree_gist` extension with `tsrange`) enforce double-booking prevention at the storage engine level.
  - Database-level session advisory locks (`pg_advisory_xact_lock(hash(technician_id))`) can serialize assignments per technician without locking the entire table.

---

## Known Limitations & Incomplete Features

1. **Push Notifications Fallback**:
   - In offline mode or local development environments, Firebase Cloud Messaging (FCM) is mocked or relies on `flutter_local_notifications` for on-device delivery. Direct FCM delivery requires production APNs/FCM credentials.
2. **Real-time Transport Scaling**:
   - The current Server-Sent Events (SSE) broadcaster uses an in-memory `asyncio.Queue` per organization. While optimal for single-node deployments, horizontal scaling across multiple backend replicas requires a Redis Pub/Sub backplane.
3. **Advanced Geospatial Routing**:
   - Candidate ranking distance calculation uses direct Euclidean / Haversine distance rather than live road routing APIs (such as Google Maps Distance Matrix or OSRM).
4. **Offline Conflict Resolution**:
   - When conflicting status transitions occur concurrently between the field technician and a dispatcher, FixFlow applies a server-authoritative "last-write-wins" or flags the entity for manual dispatcher review via a conflict recovery modal. Automatic three-way semantic merging is not implemented for arbitrary text notes.
5. **Batch Inventory Transactions**:
   - Material consumption logging is currently online-only to prevent negative stock conditions in warehouse inventory across multiple mobile workers.
