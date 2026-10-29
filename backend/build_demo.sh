#!/bin/sh
# Build the demo data once (used at image build time): start the sandbox bank, seed, stop it.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python}"
BANK_PORT="${NIDHI_BANK_PORT:-8200}"
export NIDHI_BANK_BASE="http://127.0.0.1:${BANK_PORT}"
[ -f pki/bank-ca.pem ] || "$PY" scripts/fdrgen.py pki
"$PY" -m uvicorn bank_sandbox.app:app --host 127.0.0.1 --port "$BANK_PORT" --log-level warning &
BANK=$!
for i in $(seq 1 60); do
  "$PY" -c "import urllib.request; urllib.request.urlopen('${NIDHI_BANK_BASE}/health')" 2>/dev/null && break
  sleep 0.5
done
"$PY" scripts/seed_demo.py > /dev/null
kill "$BANK" 2>/dev/null || true
echo "demo data ready"
