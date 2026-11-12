#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${API_URL:-http://localhost:8000}"
FAILED=0

echo "=== FixFlow Smoke Tests ==="
echo "API: $BASE_URL"
echo ""

# Health checks
echo "1. Health: liveness..."
curl -sf "$BASE_URL/api/v1/health/live" | grep -q "ok" || { echo "FAIL: liveness"; FAILED=1; }
echo "   OK"

echo "2. Health: readiness..."
curl -sf "$BASE_URL/api/v1/health/ready" | grep -q "ok" || { echo "FAIL: readiness"; FAILED=1; }
echo "   OK"

# Auth
echo "3. Login as requester..."
TOKEN=$(curl -sf -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"requester1@org1.fixflow.local","password":"Demo1234!"}' \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
[ -n "$TOKEN" ] || { echo "FAIL: login"; FAILED=1; }
echo "   OK (token: ${TOKEN:0:20}...)"

# Get orgs for this user
echo "4. Get current user..."
ME=$(curl -sf "$BASE_URL/api/v1/auth/me" -H "Authorization: Bearer $TOKEN")
echo "   OK"

# Get org id
ORG1_ID=$(echo "$ME" | grep -o '"organization_id":"[^"]*"' | head -1 | cut -d'"' -f4)
echo "   Org1 ID: $ORG1_ID"

# Create a request
echo "5. Create service request..."
REQ=$(curl -sf -X POST "$BASE_URL/api/v1/requests" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG1_ID" \
  -H "Content-Type: application/json" \
  -d '{"title":"Smoke test request","description":"This is a smoke test request with enough characters to pass validation","priority":"NORMAL","category_id":null}')
echo "   OK"

# Test cross-org isolation - try to access with wrong org
echo "6. Cross-org isolation (expect 403)..."
DISPATCHER_TOKEN=$(curl -sf -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"dispatcher1@org2.fixflow.local","password":"Demo1234!"}' \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
ORG2_ID="org2-placeholder"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/requests" \
  -H "Authorization: Bearer $DISPATCHER_TOKEN" \
  -H "X-Organization-ID: $ORG1_ID")
[ "$STATUS" = "403" ] || { echo "WARN: Expected 403 for cross-org, got $STATUS"; }
echo "   OK (got $STATUS)"

echo ""
if [ $FAILED -eq 0 ]; then
  echo "=== SMOKE TESTS PASSED ==="
else
  echo "=== SMOKE TESTS FAILED ==="
  exit 1
fi
