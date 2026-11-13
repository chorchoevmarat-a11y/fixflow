#!/usr/bin/env bash
# Smoke test of a RUNNING, SEEDED system through real HTTP calls (QA-08).
# Exits non-zero on any unexpected result.
set -euo pipefail

API="${API_URL:-http://localhost:8000}/api/v1"
PASSWORD="${DEMO_PASSWORD:-FixFlow-Demo-2026!}"
FAILED=0

json() { node -e "let s='';process.stdin.on('data',c=>s+=c).on('end',()=>{const d=JSON.parse(s);console.log($1)})"; }
pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1"; FAILED=1; }
expect() { # description, expected status, actual status
  if [ "$2" = "$3" ]; then pass "$1 ($3)"; else fail "$1 (expected $2, got $3)"; fi
}
status() { curl -s -o /dev/null -w "%{http_code}" "$@"; }

login() { curl -sf -X POST "$API/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\"}"; }

echo "== health =="
expect "liveness" 200 "$(status "$API/health/live")"
expect "readiness" 200 "$(status "$API/health/ready")"

echo "== sign in =="
req_login=$(login requester1@salymbekov.example.com)
REQ_TOKEN=$(echo "$req_login" | json "d.access_token")
ORG_A=$(echo "$req_login" | json "d.memberships[0].organization_id")
DISP_TOKEN=$(login dispatcher@salymbekov.example.com | json "d.access_token")
TECH_LOGIN=$(login tech1@salymbekov.example.com)
TECH_TOKEN=$(echo "$TECH_LOGIN" | json "d.access_token")
TECH_ID=$(echo "$TECH_LOGIN" | json "d.memberships[0].technician_id")
ORG_B=$(login admin@salymbekov-hospital.example.com | json "d.memberships[0].organization_id")
B_TOKEN=$(login admin@salymbekov-hospital.example.com | json "d.access_token")
pass "signed in as requester, dispatcher, technician, other-org admin"

call() { # token org method path [data]
  local token=$1 org=$2 method=$3 path=$4 data=${5:-}
  if [ -n "$data" ]; then
    curl -s -X "$method" "$API$path" -H "Authorization: Bearer $token" -H "X-Organization-ID: $org" -H 'Content-Type: application/json' -d "$data"
  else
    curl -s -X "$method" "$API$path" -H "Authorization: Bearer $token" -H "X-Organization-ID: $org" -H 'Content-Type: application/json' -d '{}'
  fi
}
code() { # same as call but returns the HTTP status
  local token=$1 org=$2 method=$3 path=$4 data=${5:-{\}}
  curl -s -o /dev/null -w "%{http_code}" -X "$method" "$API$path" -H "Authorization: Bearer $token" -H "X-Organization-ID: $org" -H 'Content-Type: application/json' -d "$data"
}

echo "== positive lifecycle: create -> triage -> assign -> accept -> start =="
CAT=$(call "$REQ_TOKEN" "$ORG_A" GET "/categories?enabled_only=true" | json "d.find(c=>c.name==='General maintenance').id")
PROP=$(call "$REQ_TOKEN" "$ORG_A" GET "/properties" | json "d.items[0].id")
STAMP=$(date +%s)
CREATED=$(call "$REQ_TOKEN" "$ORG_A" POST /requests "{\"title\":\"Smoke test request $STAMP\",\"description\":\"Created by scripts/smoke.sh to exercise the lifecycle end to end.\",\"category_id\":\"$CAT\",\"property_id\":\"$PROP\",\"priority\":\"NORMAL\"}")
RID=$(echo "$CREATED" | json "d.id")
[ -n "$RID" ] && pass "request created ($RID)" || fail "create request"
expect "requester cannot assign" 403 "$(code "$REQ_TOKEN" "$ORG_A" POST "/requests/$RID/assign" '{}')"
expect "triage" 200 "$(code "$DISP_TOKEN" "$ORG_A" POST "/requests/$RID/triage")"

# Find a free slot on a future weekday, two-hour steps, until the API accepts one.
ASSIGNED=0
for day_offset in $(seq 8 40); do
  for hour in 9 11 14 16; do
    day=$(date -u -d "+$day_offset days" +%Y-%m-%d 2>/dev/null || date -u -v+${day_offset}d +%Y-%m-%d)
    dow=$(date -u -d "$day" +%u 2>/dev/null || date -u -j -f %Y-%m-%d "$day" +%u)
    [ "$dow" -ge 6 ] && continue
    utc_hour=$((hour - 6)); [ $utc_hour -lt 10 ] && utc_hour="0$utc_hour"
    end_hour=$((hour - 4)); [ $end_hour -lt 10 ] && end_hour="0$end_hour"
    body="{\"technician_id\":\"$TECH_ID\",\"start_at\":\"${day}T${utc_hour}:00:00+00:00\",\"end_at\":\"${day}T${end_hour}:00:00+00:00\"}"
    c=$(code "$DISP_TOKEN" "$ORG_A" POST "/requests/$RID/assign" "$body")
    if [ "$c" = "200" ]; then ASSIGNED=1; SLOT_BODY=$body; break 2; fi
  done
done
[ $ASSIGNED = 1 ] && pass "assigned to technician" || fail "no free slot found to assign"
expect "technician accepts" 200 "$(code "$TECH_TOKEN" "$ORG_A" POST "/requests/$RID/accept")"
expect "technician starts" 200 "$(code "$TECH_TOKEN" "$ORG_A" POST "/requests/$RID/start")"
STATUS=$(call "$DISP_TOKEN" "$ORG_A" GET "/requests/$RID" | json "d.status")
[ "$STATUS" = "IN_PROGRESS" ] && pass "status is IN_PROGRESS" || fail "status $STATUS"

echo "== expected failures =="
expect "invalid transition rejected" 409 "$(code "$DISP_TOKEN" "$ORG_A" POST "/requests/$RID/triage")"
# Re-using the same technician slot for a new request must conflict.
CREATED2=$(call "$REQ_TOKEN" "$ORG_A" POST /requests "{\"title\":\"Smoke conflict $STAMP\",\"description\":\"Second request used to provoke a schedule conflict in the smoke test.\",\"category_id\":\"$CAT\",\"property_id\":\"$PROP\"}")
RID2=$(echo "$CREATED2" | json "d.id")
call "$DISP_TOKEN" "$ORG_A" POST "/requests/$RID2/triage" >/dev/null
expect "overlapping assignment conflicts" 409 "$(code "$DISP_TOKEN" "$ORG_A" POST "/requests/$RID2/assign" "$SLOT_BODY")"
expect "other organization cannot read the request" 404 "$(code "$B_TOKEN" "$ORG_B" GET "/requests/$RID")"
expect "other organization cannot select org A" 403 "$(code "$B_TOKEN" "$ORG_A" GET "/requests")"
expect "missing credentials rejected" 401 "$(status "$API/requests")"
expect "OpenAPI reachable" 200 "$(status "$API/openapi.json")"

echo
if [ $FAILED -eq 0 ]; then echo "SMOKE PASSED"; else echo "SMOKE FAILED"; exit 1; fi
