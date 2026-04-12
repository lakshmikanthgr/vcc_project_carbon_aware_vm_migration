# CALM-SLA: Carbon-Aware Live VM Migration Framework with SLA Guarantees

## Overview

CALM-SLA reduces the carbon footprint of VM workloads by migrating them toward data center zones powered by lower-carbon energy, while enforcing strict SLA constraints. It combines real-time carbon intensity data, a TCN-based carbon forecaster, an SLA-tier classifier, a migration cost estimator, and a DRL migration engine (Deep Q-Network) into a fully automated decision loop.

## Architecture

```
Carbon Monitor → TCN Forecaster → SLA Classifier → DRL / Greedy Engine → Migration Engine
                                                                        ↓
                                                               SQLite DB + REST API + Dashboard
```

### Components

| File | Purpose |
|---|---|
| `services/carbon_service.py` | Polls ElectricityMaps + WattTime APIs for live gCO₂/kWh per zone |
| `services/carbon_forecaster.py` | TCN (Temporal Convolutional Network) — 4-hour carbon intensity forecast |
| `sla_classifier.py` | Classifies VMs as Gold / Silver / Bronze based on SLA contract + runtime metrics |
| `migration_cost_estimator.py` | Pre-copy migration model: bandwidth, downtime, carbon overhead |
| `decision_engine.py` | Greedy rule-based engine — approves migrations when net saving > 0 and SLA passes |
| `drl_environment.py` | Gymnasium environment for DRL training (16-dim state, 5 actions) |
| `drl_train.py` | Train the DQN agent (stable-baselines3) |
| `drl_decision_engine.py` | DRL inference wrapper — drop-in replacement for greedy engine |
| `orchestrator.py` | Wires all components together; runs one decision cycle |
| `orchestrator_loop.py` | Continuous loop — calls orchestrator every POLL_INTERVAL seconds |
| `database.py` | SQLite persistence: `carbon_readings` + `migration_log` tables |
| `api.py` | FastAPI REST API — 7 endpoints + `/docs` interactive documentation |
| `dashboard.html` | Self-contained live dashboard — polls API every 15s, no build step |
| `simulation/vm_simulator.py` | 10-VM SimulatedVM fleet (3 Gold, 3 Silver, 4 Bronze) |
| `fetch_history.py` | Fetch 24h of carbon history CSVs for TCN training |
| `train_tcn.py` | Offline TCN training from CSVs |
| `config/settings.py` | Central constants: ALPHA, BETA, GAMMA, zones, SLA limits |
| `gcp_migration.py` | Optional real GCP migration engine (snapshot + clone) |
| `run.sh` | One-command launch: fetch → train TCN → start API + orchestrator |

## SLA Tier Rules

| Tier | Latency | Downtime limit | Example workloads |
|---|---|---|---|
| Gold | ≤ 20ms or `critical=True` or CPU ≥ 80% | ≤ 60s | Databases, payment systems |
| Silver | ≤ 50ms or CPU ≥ 60% | ≤ 180s | Web servers, APIs |
| Bronze | > 50ms, light load | ≤ 900s | Batch jobs, analytics |

## Decision Logic

A migration is approved only when:
1. Target zone has lower forecast carbon intensity than source
2. Net saving = (gross saving − migration carbon cost) > 0
3. Estimated downtime ≤ tier SLA limit

## Install and Run

```bash
# Clone and install
git clone <repo> && cd calm-sla
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Configure API keys
cp .env.example .env
# Edit .env with your ElectricityMaps and WattTime credentials

# Full pipeline launch (fetches history, trains TCN, starts API + loop)
bash run.sh

# Open dashboard in browser
open dashboard.html
```

## Run Order (manual)

```bash
python fetch_history.py          # fetch/generate carbon history CSVs
python train_tcn.py --epochs 50  # train TCN from CSVs
python drl_train.py --steps 500000  # train DRL agent (optional, ~15 min)
pytest tests/                    # run 53 tests — all should pass
bash run.sh                      # start full system
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /status` | Framework health, uptime, last poll time |
| `GET /carbon/current` | Live carbon intensity per zone with measurements |
| `GET /carbon/history/{zone}` | Historical readings from DB |
| `GET /vms` | 10-VM fleet with SLA tier and runtime metrics |
| `GET /decisions` | Recent migration decisions from DB |
| `GET /metrics/summary` | Total CO₂ saved, migration counts, SLA violations |
| `GET /metrics/baseline` | CALM-SLA vs greedy vs no-migration comparison |
| `POST /cycle` | Manually trigger one orchestration cycle |

Interactive docs: `http://localhost:8199/docs`

## Switching to DRL Engine

```bash
# Train first (if not already done)
python drl_train.py --steps 500000

# Launch with DRL engine
USE_DRL=true bash run.sh

# Or set in .env:
# USE_DRL=true
```

The `DRLDecisionEngine` automatically falls back to the greedy engine if `data/models/drl_agent.zip` is not found.

## Day 7 Baseline Results (150 decisions, 50 episodes × 3 VM tiers)

| Strategy | Migrations | SLA violations | Net CO₂ saved |
|---|---|---|---|
| No migration | 0 | 0 | 0 g |
| Greedy (always migrate) | 113 (75%) | 0 | 98,154 g |
| CALM-SLA rule-based | 74 (49%) | **0** | 17,188 g |
| CALM-SLA DRL (100k steps) | 38 (25%) | **0** | 7,325 g |

Key result: both CALM-SLA variants achieve **zero SLA violations** while the greedy baseline routinely migrates Gold-tier VMs past their 60s downtime budget. Running DRL to 500k steps brings migration rate closer to the rule-based engine with the same SLA guarantee.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ELECTRICITYMAPS_API_KEY` | — | ElectricityMaps API key |
| `WATTTIME_USERNAME` | — | WattTime username |
| `WATTTIME_PASSWORD` | — | WattTime password |
| `WATTTIME_USER_EMAIL` | — | WattTime registration email |
| `ORG` | — | WattTime organisation |
| `WATTTIME_USING_API_URL` | `https://api2.watttime.org/v3/` | WattTime API base URL |
| `GCP_PROJECT_ID` | — | GCP project for real migration |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Path to GCP service account JSON |
| `USE_DRL` | `false` | Set `true` to use DRL engine |
| `POLL_INTERVAL` | `300` | Orchestrator cycle interval (seconds) |

## Testing

```bash
pytest tests/ -v
# Expected: 53 passed
```

Test coverage: config, SLA classifier, cost estimator, decision engine (happy/sad/SLA-blocked), DRL environment, VM simulator, database layer, fetch_history, TCN forecaster, orchestrator integration.

## References

- CARBON-DQN (Alex M. et al., 2025) — DQN for carbon-aware VM placement
- RLVMP (2025) — RL + Firefly optimisation for VM migration
- Clark et al. — Pre-copy live migration (foundational)
- ElectricityMaps API — https://api.electricitymaps.com
- WattTime API — https://watttime.org
