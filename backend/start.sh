#!/bin/sh
# Start NidhiSetu in one container: the sandbox bank (internal), demo data on first boot, then the portal.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python}"
BANK_PORT="${NIDHI_BANK_PORT:-8200}"
export NIDHI_BANK_BASE="http://127.0.0.1:${BANK_PORT}"
[ -f pki/bank-ca.pem ] || "$PY" scripts/fdrgen.py pki
"$PY" -m uvicorn bank_sandbox.app:app --host 127.0.0.1 --port "$BANK_PORT" --log-level warning &
for i in $(seq 1 60); do
  "$PY" -c "import urllib.request; urllib.request.urlopen('${NIDHI_BANK_BASE}/health')" 2>/dev/null && break
  sleep 0.5
done
if [ ! -f bank_sandbox/records.json ] || [ ! -f data/nidhisetu.db ]; then
  echo "Seeding the demo data (fictional institutions and sandbox banks)..."
  "$PY" scripts/seed_demo.py > /dev/null
fi
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8300}" --log-level warning
