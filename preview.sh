#!/usr/bin/env bash
# Serves the widget locally against your local data.json, instead of the
# live jsDelivr CDN — for previewing CSS/JS changes before pushing.
#
# Usage: ./preview.sh [port]   (default port: 8080)
#
# This never modifies the real ean-resources.js: it copies the widget
# files into a temp directory, points that copy's DATA_URL at the local
# data.json sitting alongside it, and serves the temp directory. The temp
# copy is deleted when you stop the server (Ctrl+C).
#
# The copy is refreshed from the real files every second while the server
# runs, so editing ean-resources.css/js/data.json and hitting reload in
# the browser is enough — no need to restart this script after each edit.

set -euo pipefail

PORT="${1:-8080}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"

cleanup() {
  kill "$SYNC_PID" 2>/dev/null || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

sync_once() {
  cp "$REPO_DIR/ean-resources.css" "$TMP_DIR/ean-resources.css"
  cp "$REPO_DIR/data.json" "$TMP_DIR/data.json"
  sed 's#https://cdn.jsdelivr.net/gh/exposeaz/website-resources@main/data.json#data.json#' \
    "$REPO_DIR/ean-resources.js" > "$TMP_DIR/ean-resources.js"
}

sync_once
( while true; do sleep 1; sync_once; done ) &
SYNC_PID=$!

cat > "$TMP_DIR/index.html" <<'EOF'
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>EAN resources widget — local preview</title>
<link rel="stylesheet" href="ean-resources.css">
</head>
<body>
<div id="ean-resources-root"></div>
<script src="ean-resources.js"></script>
</body>
</html>
EOF

echo "Serving local preview at http://localhost:$PORT (Ctrl+C to stop)"
echo "Using local data.json — not the live jsDelivr CDN."
echo "Auto-syncing edits every second — just reload the browser, no restart needed."

if command -v open >/dev/null 2>&1; then
  ( sleep 1 && open "http://localhost:$PORT" ) &
elif command -v xdg-open >/dev/null 2>&1; then
  ( sleep 1 && xdg-open "http://localhost:$PORT" ) &
fi

cd "$TMP_DIR"
if command -v python3 >/dev/null 2>&1; then
  python3 -m http.server "$PORT"
elif command -v python >/dev/null 2>&1; then
  python -m SimpleHTTPServer "$PORT"
else
  echo "Need python3 (or python) on PATH to serve files locally." >&2
  exit 1
fi
