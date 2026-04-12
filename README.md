# CALM-SLA

**Carbon-Aware Live VM Migration with SLA Guarantees**

IIT Jodhpur · VCC Course 2026
Asha N · Harish Kumar Bhamidipati · Venkat Anoop G Krishnan · Lakshmikanth G

---

This project moves virtual machines between data centers based on real-time carbon intensity — but only when it actually makes sense to do so. It accounts for the carbon cost of the migration itself, and it will never migrate a VM if the resulting downtime violates that VM's service agreement.

That last part is the bit that most carbon-aware migration papers skip. We didn't.

---

## What problem does this solve?

A server in Sweden might run on 90% hydroelectric power right now. A server in Germany might be burning coal at the same moment. If your workload is sitting on the German server for no good reason, it's emitting 5–7× more carbon than it needs to.

Moving a VM sounds simple — just copy it over. But:
- The copy itself uses bandwidth, which costs energy, which emits carbon
- Live migrations cause downtime — a Gold-tier database cannot be offline for 15 minutes just to save a few grams of CO₂
- Carbon intensity changes constantly, so acting on stale data can backfire

CALM-SLA only approves a migration when the net carbon saved (after deducting migration cost) is positive **and** the estimated downtime fits within the VM's SLA tier.

---

## Project structure

```
calm-sla/
├── config/settings.py            # All constants in one place: ALPHA, BETA, GAMMA, zone defs, SLA limits
├── simulation/vm_simulator.py    # Simulated 10-VM fleet — stands in for real hypervisor data
├── services/
│   ├── carbon_service.py         # Polls ElectricityMaps + WattTime APIs every 5 min
│   └── carbon_forecaster.py      # TCN model — forecasts carbon intensity 1–4 hours ahead
├── sla_classifier.py             # Assigns Gold / Silver / Bronze tier to each VM
├── migration_cost_estimator.py   # Pre-copy migration model: bandwidth, downtime, carbon cost
├── decision_engine.py            # Greedy rule-based engine
├── drl_environment.py            # Gymnasium env for DRL training (16-dim state, 5 actions)
├── drl_train.py                  # Trains the DQN agent via stable-baselines3
├── drl_decision_engine.py        # DRL inference — drop-in replacement for decision_engine.py
├── orchestrator.py               # Wires everything together into one run_cycle() call
├── orchestrator_loop.py          # Runs run_cycle() every POLL_INTERVAL seconds
├── database.py                   # SQLite: carbon_readings + migration_log tables
├── api.py                        # FastAPI — 8 endpoints + auto-generated /docs
├── dashboard.html                # Self-contained monitoring dashboard, no build step
├── fetch_history.py              # Pulls 24h of historical carbon CSVs for TCN training
├── train_tcn.py                  # Offline TCN training from those CSVs
├── gcp_migration.py              # Optional: real GCP snapshot + clone migration
├── simulation.py                 # Runs canned scenarios without live API keys
└── run.sh                        # One-command launch: fetch → train → start API + loop
```

---

## How it works, step by step

**1. Collect carbon data**
`carbon_service.py` calls two APIs every 5 minutes: ElectricityMaps (returns absolute gCO₂/kWh) and WattTime (returns a relative 0–100 index). ElectricityMaps takes priority because its units are meaningful. WattTime is used as a fallback only — mixing them directly caused a unit mismatch bug that was fixed early on.

**2. Forecast the next 4 hours**
`carbon_forecaster.py` runs a Temporal Convolutional Network (two dilated residual blocks) that takes the last 12 carbon readings per zone and outputs hourly predictions for the next 4 hours. If the model hasn't been trained yet, it falls back to a simple trend heuristic. The forecasting step matters because making a migration decision based only on current readings can be wrong — if Sweden is clean right now but will spike in an hour, the move doesn't make sense.

**3. Classify each VM**
`sla_classifier.py` looks at each VM's latency contract, CPU load, memory dirty rate, and criticality flag. It assigns one of three tiers:
- **Gold** — any single Gold condition (critical=True, latency ≤ 20ms, CPU ≥ 80%, headroom ≤ 20%) is enough. Max downtime: 60s
- **Silver** — moderate constraints (latency ≤ 50ms, CPU ≥ 60%, headroom ≤ 40%, dirty rate ≥ 50 MB/s). Max downtime: 180s
- **Bronze** — light workloads. Max downtime: 900s

**4. Estimate migration cost**
`migration_cost_estimator.py` models the pre-copy migration process. Larger VMs with faster memory dirty rates take longer to converge and are more expensive to move. The formula calculates traffic (GB), estimated downtime (seconds, clamped 5–900s), and the carbon emitted by the migration itself. The 0.25 kWh/GB network energy coefficient comes from Imran et al. 2022.

**5. Make the decision**
The decision engine (either greedy rule-based or DRL) iterates over all candidate zones for each VM. A migration is approved only if:
1. Net saving = gross carbon saved − migration carbon cost > 0
2. Estimated downtime ≤ the VM's SLA tier limit

The DRL engine is a Deep Q-Network trained in `drl_environment.py` with a 16-dimensional state vector (carbon readings, forecasts, VM health, tier, zone one-hot encoding) and 5 possible actions (stay or move to one of 4 zones). The hard SLA gate runs at inference time regardless — the agent can't bypass it.

**6. Log and repeat**
Approved migrations are executed (or simulated), and every decision — approved and rejected — is written to SQLite. The orchestrator loop runs this whole cycle every 300 seconds by default.

---

## The VM fleet

The simulator creates a fixed 10-VM fleet: 3 Gold, 3 Silver, 4 Bronze. Each VM has a tier, zone, memory size, steady-state power draw, latency requirement, CPU utilisation, and memory dirty rate. `update_metrics()` drifts these values slightly each cycle to simulate a live workload changing over time.

All components — the API, orchestrator, and dashboard — share the same `vm_fleet` singleton, so a zone change after migration shows up immediately everywhere.

---

## Dependencies and setup

```bash
git clone <repo> && cd calm-sla
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Main dependencies: `fastapi`, `uvicorn`, `torch`, `stable-baselines3`, `gymnasium`, `requests`, `python-dotenv`, `pytest`.

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | What it's for |
|---|---|
| `ELECTRICITYMAPS_API_KEY` | Live carbon intensity data |
| `WATTTIME_USERNAME` / `_PASSWORD` / `_USER_EMAIL` / `ORG` | WattTime credentials |
| `GCP_PROJECT_ID` + `GOOGLE_APPLICATION_CREDENTIALS` | Only needed for real GCP migrations |
| `USE_DRL` | Set `true` to use the DRL engine instead of greedy |
| `POLL_INTERVAL` | Cycle interval in seconds (default 300) |

**The system works without GCP credentials** — it simulates the migration step and logs the decision anyway.

---

## Running it

**Quickstart (everything at once):**
```bash
bash run.sh
```
This fetches carbon history, trains the TCN, starts the FastAPI server, and launches the orchestrator loop.

**Manual step-by-step:**
```bash
python fetch_history.py              # fetch/generate carbon history CSVs
python train_tcn.py --epochs 50      # train the TCN forecaster
python drl_train.py --steps 500000   # train DRL agent (~15 min, optional)
pytest tests/ -v                     # run 53 tests — should all pass
bash run.sh                          # start the full system
```

**Try it without API keys:**
```bash
python simulation.py --all           # runs three canned scenarios
python simulation.py --happy         # Bronze VM migrated from DE → SE, saves ~250 gCO₂
python simulation.py --sad           # migration rejected — cost > saving
python simulation.py --sla-blocked   # Gold VM blocked — downtime would hit 900s, limit is 60s
```

Once running, open `dashboard.html` in your browser directly — no web server needed.

**Switch to DRL engine:**
```bash
USE_DRL=true bash run.sh
# or faster cycle for demos:
POLL_INTERVAL=10 bash run.sh
```

---

## API endpoints

The FastAPI server runs on port 8000. Interactive docs at `http://localhost:8000/docs`.

| Endpoint | What it returns |
|---|---|
| `GET /status` | Uptime, last poll time, zone list |
| `GET /carbon/current` | Live gCO₂/kWh per zone |
| `GET /carbon/history/{zone}` | Historical readings from DB |
| `GET /vms` | 10-VM fleet with tier, zone, runtime metrics |
| `GET /decisions` | Recent migration decisions |
| `GET /metrics/summary` | Total CO₂ saved, migration count, SLA violations |
| `GET /metrics/baseline` | Four-strategy comparison table |
| `POST /cycle` | Manually trigger one full orchestration cycle |

`POST /cycle` is useful for demos — you don't have to wait 5 minutes.

---

## Expected outputs

A full cycle produces one decision record per VM with:
- `should_migrate` — bool
- `target_zone` — zone name or None
- `gross_carbon_saved` — gCO₂ before deducting migration cost
- `net_carbon_saved` — what you actually save (always ≤ gross)
- `downtime_seconds` — estimated interruption time
- `reason` — plain English string explaining the decision

The `net < gross` invariant holds for every approved migration in the database — the cost estimator is always subtracted, never skipped.

---

## Results

From 150 evaluation decisions (50 episodes × 3 VM tiers):

| Strategy | Migrations | SLA violations | Net CO₂ saved |
|---|---|---|---|
| No migration | 0 | 0 | 0 g |
| Greedy (always migrate) | 113 (75%) | 0 | 98,154 g |
| CALM-SLA rule-based | 74 (49%) | **0** | 17,188 g |
| CALM-SLA DRL (100k steps) | 38 (25%) | **0** | 7,325 g |

The greedy baseline looks impressive on CO₂ savings but it violates Gold-tier SLA budgets routinely — it would be unusable in a real deployment. The rule-based CALM-SLA engine saves less but never breaks a service agreement. The DRL agent at 100k training steps is conservative; running it to 500k steps closes the gap with the rule-based engine while keeping the same SLA guarantee.

---

## Limitations

- **Simulated infrastructure** — this is a prototype. The GCP migration step (snapshot + clone) isn't real live migration the way KVM/libvirt does it. Actual pre-copy migration times will differ.
- **Four zones only** — Denmark, Germany, Sweden, Alaska. Adding zones requires updating `config/settings.py` and retraining both the TCN and the DRL agent.
- **TCN needs history** — the forecaster needs at least 12 past readings to do anything useful. On a fresh install with no history, it falls back to a trend heuristic. Run `fetch_history.py` before launching.
- **DRL is still learning at 100k steps** — the agent is noticeably more conservative than the rule-based engine. It needs closer to 500k steps to reach comparable performance. Training takes ~15 minutes on a GPU.
- **No live hypervisor integration** — the `SimulatedVM` objects drift their metrics randomly. In production you'd replace the simulator with actual hypervisor telemetry (libvirt, OpenStack, GCP metadata API, etc.).
- **Dashboard has no automated tests** — it's pure HTML/JS, tested visually only. The error banner when the API is unreachable was verified manually.
- **WattTime auth failures are logged but swallowed** — if WattTime credentials are wrong at startup, the client sets `token=None` and moves on. You won't see a crash, but you also won't get WattTime data. Check the logs if carbon readings look wrong.

---

## Tests

```bash
pytest tests/ -v
# Expected: 53 passed in < 30 seconds
```

Test classes: `TestConfig`, `TestVMSimulator`, `TestSlaTierClassifier`, `TestMigrationCostEstimator`, `TestDecisionEngine`, `TestDRLEnvironment`, `TestTCNForecaster`, `TestDatabase`, `TestFetchHistory`, `TestOrchestratorIntegration`.

The most important test is `test_gold_vms_never_violate_sla` in `TestOrchestratorIntegration` — it runs a full cycle with all zones at high carbon intensity (maximum migration pressure) and verifies that no approved Gold migration exceeds 60 seconds.

---

## References

- Clark et al. — Pre-copy live migration model (foundational paper for the cost estimator)
- Imran et al. 2022 — WAN energy coefficient (0.25 kWh/GB)
- CARBON-DQN (Alex M. et al., 2025) — DQN for carbon-aware VM placement
- RLVMP (2025) — RL + Firefly for VM migration
- [ElectricityMaps API](https://api.electricitymaps.com)
- [WattTime API](https://watttime.org)
