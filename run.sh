#!/bin/bash
# run.sh — Full CALM-SLA launch script
# Runs the complete pipeline in the correct order:
#   1. fetch_history.py  — populate carbon history CSVs
#   2. train_tcn.py      — train TCN forecaster from CSVs
#   3. api.py            — start FastAPI REST backend
#   4. orchestrator_loop — start continuous decision loop
#
# Environment variables:
#   USE_DRL=true         — use trained DRL agent instead of greedy engine
#   POLL_INTERVAL=60     — override poll interval in seconds (default 300)
#
# Usage:
#   bash run.sh                  # standard launch
#   USE_DRL=true bash run.sh     # launch with DRL engine
#   POLL_INTERVAL=60 bash run.sh # faster cycles for demo

set -e
cd "$(dirname "$0")"

# Activate venv if present
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "=== CALM-SLA Framework Starting ==="
echo ""

# Step 1 — fetch carbon history (generates CSVs for TCN training)
echo "[1/4] Fetching carbon history..."
python fetch_history.py
echo ""

# Step 2 — train TCN forecaster from CSVs (skip if models already exist)
if [ ! -f "data/models/tcn_SE.pt" ]; then
    echo "[2/4] Training TCN forecaster..."
    python train_tcn.py --epochs 50
else
    echo "[2/4] TCN models already exist — skipping training (delete data/models/tcn_*.pt to retrain)"
fi
echo ""

# Step 3 — initialise database
echo "[3/4] Initialising database..."
python -c "from database import init_db; init_db(); print('  DB ready → data/calm_sla.db')"
echo ""

# Step 4 — start services
echo "[4/4] Starting services..."
uvicorn api:app --host 0.0.0.0 --port 8199 --log-level warning &
API_PID=$!
echo "  API started (PID $API_PID) → http://localhost:8199"
echo "  Interactive docs           → http://localhost:8199/docs"
sleep 2

python orchestrator_loop.py &
ORCH_PID=$!
echo "  Orchestrator started (PID $ORCH_PID)"
echo ""
echo "=== CALM-SLA Running ==="
echo "  Dashboard  : open dashboard.html in browser"
echo "  Metrics    : curl http://localhost:8199/metrics/summary"
echo "  Trigger    : curl -X POST http://localhost:8199/cycle"
echo "  DRL mode   : USE_DRL=true bash run.sh"
echo ""
echo "Press Ctrl+C to stop all services"

trap "echo ''; echo 'Stopping...'; kill $API_PID $ORCH_PID 2>/dev/null; exit 0" INT TERM
wait
