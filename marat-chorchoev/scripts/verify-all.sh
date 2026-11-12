#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
FAILED=0

echo "=== FixFlow Verification Suite ==="
echo ""

echo "--- Backend ---"
(cd "$ROOT_DIR/backend" && uv sync --frozen && uv run ruff check . && uv run ruff format --check . && uv run ty check . && uv run pytest -q) || { echo "BACKEND FAILED"; FAILED=1; }

echo ""
echo "--- Web ---"
(cd "$ROOT_DIR/web" && bun install --frozen-lockfile && bun run lint && bun run typecheck && bun run test:ci && bun run build) || { echo "WEB FAILED"; FAILED=1; }

echo ""
echo "--- Mobile ---"
(cd "$ROOT_DIR/mobile" && flutter pub get && dart format --output=none --set-exit-if-changed lib test && flutter analyze && flutter test && flutter build apk --debug) || { echo "MOBILE FAILED"; FAILED=1; }

echo ""
if [ $FAILED -eq 0 ]; then
  echo "=== ALL CHECKS PASSED ==="
else
  echo "=== SOME CHECKS FAILED ==="
  exit 1
fi
