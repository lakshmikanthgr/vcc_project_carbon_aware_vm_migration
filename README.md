# CALM-SLA: Carbon-Aware Live VM Migration Framework with SLA Guarantees

## Project Overview

CALM-SLA is a framework designed to optimize virtual machine (VM) placement in cloud environments by prioritizing carbon efficiency while respecting Service Level Agreements (SLAs). Traditional cloud schedulers focus on cost or resource utilization but ignore the carbon intensity of electricity grids. This leads to VMs running on high-carbon power sources unnecessarily, even when greener alternatives exist.

The framework continuously monitors real-time carbon intensity signals (gCO₂eq/kWh) across geo-distributed data centers, classifies VMs into SLA tiers (Gold/Silver/Bronze) based on latency sensitivity, and uses a decision engine to compute net carbon benefits of live migration. VMs are migrated only when carbon savings outweigh migration overhead and SLA guarantees are preserved.

**Key Goals:**
- Minimize carbon footprint of VM workloads
- Preserve latency-sensitive workloads (e.g., no migration for critical Gold-tier VMs if downtime exceeds thresholds)
- Enable proactive rather than reactive migration using carbon forecasts

## Project Components

1. **Carbon Intensity Monitor** (`services/carbon_service.py`)
   - Polls ElectricityMaps and WattTime APIs for zone-level carbon intensity data
   - Aggregates readings from multiple sources for reliability
   - Maintains history for forecasting
   - Falls back to synthetic data if APIs are unavailable

2. **TCN Carbon Forecaster** (`services/carbon_forecaster.py`)
   - Trainable PyTorch-based Temporal Convolutional Network (TCN)
   - Forecasts carbon intensity 1–4 hours ahead per data center
   - Automatically trains on historical data when sufficient samples are available
   - Falls back to simple trend extrapolation if untrained

3. **SLA-Tier Classifier** (`sla_classifier.py`)
   - Classifies VMs as Gold, Silver, or Bronze based on SLA contracts and runtime metrics
   - Gold: Critical workloads (e.g., latency <20ms, high CPU utilization)
   - Silver: Moderate sensitivity
   - Bronze: Flexible workloads

4. **Migration Cost Estimator** (`migration_cost_estimator.py`)
   - Models pre-copy migration overhead
   - Estimates bandwidth consumption, downtime, and carbon cost of migration traffic
   - Accounts for VM size, dirty rate, and network capacity

5. **Decision Engine** (`decision_engine.py`)
   - Evaluates migration candidates using carbon savings vs. costs
   - Enforces SLA-aware downtime limits (e.g., Gold VMs: <60s downtime)
   - Computes net carbon benefit over forecast horizon

6. **Migration Engine** (`migration_engine.py`)
   - Executes approved migrations (currently a stub; can be extended for real VM orchestration)

7. **Orchestrator** (`orchestrator.py`)
   - Coordinates all components in a cycle
   - Polls carbon data, trains forecaster, evaluates VMs, and triggers migrations

8. **Simulation Module** (`simulation.py`)
   - Provides happy/sad/SLA-blocked/real-case scenarios for testing
   - CLI flags for individual scenario runs

## Architecture

- **Data Flow**: Monitor → Forecaster → Decision Engine → Migration Engine
- **Decision Logic**: For each VM, evaluate all candidate zones; migrate if net carbon savings > 0 and SLA preserved
- **Modular Design**: Components are loosely coupled via dependency injection in the Orchestrator

## Requirements

### Software Requirements
- **Python**: >=3.10
- **Core Dependencies** (from `pyproject.toml`):
  - `loguru>=0.7.3` (logging)
  - `requests>=2.31.0` (HTTP client for APIs)
  - `numpy>=1.26.0` (numerical computing)
  - `torch>=2.0.0` (PyTorch for TCN forecasting)
  - `watttime>=1.3.2` (optional WattTime SDK)
- **Development Dependencies**:
  - `pytest>=9.0.2` (testing)
  - `black>=24.1.0` (code formatting)
  - `ruff>=0.0.0` (linting)

### Hardware Requirements
- Minimal: Standard desktop/laptop with Python support
- For training TCN: GPU recommended for faster convergence (but CPU works)
- Storage: ~100MB for dependencies + model checkpoints

### API Keys (for Real Data)
- **ElectricityMaps**: `ELECTRICITYMAPS_API_KEY` (get from https://electricitymaps.com/)
- **WattTime**: Either `WATTTIME_API_KEY` or `WATTTIME_USERNAME` + `WATTTIME_PASSWORD` (register at https://watttime.org/)
- If not set, the system uses synthetic data for demonstration

### Environment Setup
1. Clone the repo and navigate to the directory
2. Create a virtual environment: `python3 -m venv .venv && source .venv/bin/activate`
3. Install dependencies: `pip install -e .`
4. Set API keys as environment variables (optional)
5. Run simulations: `python simulation.py --happy` or `python main.py`

## Usage Examples
- **Run all simulations**: `python simulation.py`
- **Run specific scenario**: `python simulation.py --sla-blocked`
- **Run full orchestrator**: `python main.py`
- **Train and forecast**: The orchestrator auto-trains the TCN when history is sufficient

## Future Enhancements
- Integrate with real VM orchestration platforms (e.g., OpenStack, Kubernetes)
- Add reinforcement learning (DRL) for dynamic decision-making
- Expand to multi-objective optimization (carbon + cost + performance)
- Real-time dashboard for carbon metrics and migration decisions

## API Integration

Set the following environment variables to enable real API polling:

- `ELECTRICITYMAPS_API_KEY`
- `WATTTIME_API_KEY`
- or `WATTTIME_USERNAME` and `WATTTIME_PASSWORD`

If `WATTTIME_API_KEY` is not configured, the monitor will attempt WattTime authentication using `WATTTIME_USERNAME`/`WATTTIME_PASSWORD`. If neither WattTime credential path is configured, the monitor falls back to synthetic intensity values so the framework remains runnable.

## Getting Started

Install dependencies and run the sample orchestrator:

```bash
pip install -e .
python main.py
```

The repository also includes a scenario simulator for happy, sad, SLA-blocked, and real-case decisions:

```bash
python simulation.py
```

You can run a single scenario with flags:

```bash
python simulation.py --happy
python simulation.py --sad
python simulation.py --sla-blocked
python simulation.py --real
python simulation.py --all
```

The `main.py` entrypoint now runs:
- the orchestrator sample flow
- happy/sad/SLA-blocked simulated scenarios
- a real-case demonstration using the same `Orchestrator` pipeline

## Notes

- `services/carbon_service.py` now includes real connector scaffolds for ElectricityMaps and WattTime.
- `services/carbon_forecaster.py` contains a trainable TCN implementation using PyTorch.
- The orchestrator will train the forecaster when enough zone history is available and then uses the TCN forecast for migration decisions.

