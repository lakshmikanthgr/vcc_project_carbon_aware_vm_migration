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
   - Supports WattTime v3 API with region-from-loc and signal-index endpoints
   - Aggregates readings from multiple sources for reliability
   - Maintains history for forecasting
   - Falls back to synthetic data if APIs are unavailable
   - Currently monitors zones: DK-DK1 (Denmark), DE (Germany), SE (Sweden), US-AK (Alaska)

2. **TCN Carbon Forecaster** (`services/carbon_forecaster.py`)
   - Trainable PyTorch-based Temporal Convolutional Network (TCN)
   - Forecasts carbon intensity 1–4 hours ahead per data center
   - Automatically trains on historical data when sufficient samples are available
   - Falls back to simple trend extrapolation if untrained

3. **SLA-Tier Classifier** (`sla_classifier.py`)
   - Classifies VMs as Gold, Silver, or Bronze based on SLA contracts and runtime metrics
   - Gold: Critical workloads (e.g., latency <20ms, high CPU utilization) - max 60s downtime
   - Silver: Moderate sensitivity - max 180s downtime
   - Bronze: Flexible workloads - no strict downtime limits

4. **Migration Cost Estimator** (`migration_cost_estimator.py`)
   - Models pre-copy migration overhead
   - Estimates bandwidth consumption, downtime, and carbon cost of migration traffic
   - Accounts for VM size, dirty rate, and network capacity

5. **Decision Engine** (`decision_engine.py`)
   - Evaluates migration candidates using carbon savings vs. costs
   - Enforces SLA-aware downtime limits per tier
   - Computes net carbon benefit over forecast horizon
   - Only migrates when net savings > 0 and SLA constraints satisfied

6. **Migration Engine** (`migration_engine.py`)
   - Executes approved migrations (currently a stub; can be extended for real VM orchestration)

7. **Orchestrator** (`orchestrator.py`)
   - Coordinates all components in a cycle
   - Polls carbon data, trains forecaster, evaluates VMs, and triggers migrations

8. **Report Generator** (`report_generator.py`)
   - Generates detailed HTML reports with migration decision analysis
   - Shows live API data vs. simulation test scenarios
   - Includes carbon intensity comparisons, SLA checks, and cost calculations
   - Provides visual breakdown of why migrations are approved or rejected

9. **Simulation Module** (`simulation.py`)
   - Provides happy/sad/SLA-blocked/real-case scenarios for testing
   - CLI flags for individual scenario runs
   - Demonstrates different migration outcomes with artificial test data

## Current Status & Limitations

### ✅ Implemented Features
- Real-time carbon intensity monitoring from ElectricityMaps and WattTime APIs
- SLA-aware migration decision engine with Gold/Silver/Bronze tiers
- TCN-based carbon forecasting with automatic training
- Comprehensive HTML report generation with live data analysis
- Simulation scenarios for testing different migration outcomes
- Fallback to synthetic data when APIs are unavailable

### ⚠️ Current Limitations
- Migration engine is currently a stub (logs decisions but doesn't execute real migrations)
- Limited to 4 geographic zones (DK-DK1, DE, SE, US-AK)
- Requires manual API key configuration for live data
- No persistent storage for historical data across runs
- Report generation requires manual opening of HTML file

### 🎯 Decision Logic Summary
VMs are migrated only when ALL conditions are met:
1. **Carbon Savings**: Target zone has lower carbon intensity than source
2. **Net Benefit**: Migration carbon cost < operational savings over forecast horizon
3. **SLA Compliance**: Estimated downtime respects tier limits (Gold: ≤60s, Silver: ≤180s, Bronze: flexible)
4. **Technical Feasibility**: VM size and dirty rate allow migration within constraints

## Requirements

### Software Requirements
- **Python**: >=3.10
- **Core Dependencies** (from `pyproject.toml`):
  - `loguru>=0.7.3` (logging)
  - `requests>=2.31.0` (HTTP client for APIs)
  - `numpy>=1.26.0` (numerical computing)
  - `torch>=2.0.0` (PyTorch for TCN forecasting)
  - `python-dotenv>=1.0.0` (environment variable loading)
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
- **WattTime**: `WATTTIME_USERNAME`, `WATTTIME_PASSWORD`, `WATTTIME_USER_EMAIL`, `WATTTIME_ORG` (register at https://watttime.org/)
  - Alternative: `WATTTIME_USING_API_URL` (defaults to https://api2.watttime.org/v3/)
- If not set, the system uses synthetic data for demonstration

### Environment Setup
1. Clone the repo and navigate to the directory
2. Create a virtual environment: `python3 -m venv .venv && source .venv/bin/activate`
3. Install dependencies: `pip install -e .`
4. Set API keys as environment variables in `.env` file (optional)
5. Run simulations: `python simulation.py --happy` or `python main.py`

## Usage Examples
- **Run all simulations**: `python simulation.py`
- **Run specific scenario**: `python simulation.py --sla-blocked`
- **Run full orchestrator with live data**: `python main.py`
- **View detailed migration report**: Open `migration_report.html` in a web browser after running `main.py`
- **Train and forecast**: The orchestrator auto-trains the TCN when history is sufficient

## Report Features
The framework generates comprehensive HTML reports showing:
- **Live Data Analysis**: Real-time carbon intensity from APIs with detailed calculations
- **Simulation Scenarios**: Test data demonstrating happy/sad/SLA-blocked migration outcomes
- **Decision Breakdown**: Step-by-step reasoning for each migration decision
- **SLA Compliance**: Downtime limits and carbon cost calculations
- **Visual Dashboard**: Color-coded results with professional styling

Reports are automatically saved as `migration_report.html` and can be opened in any web browser.

## Future Enhancements
- Integrate with real VM orchestration platforms (e.g., OpenStack, Kubernetes)
- Add more carbon intensity data sources and regions
- Implement predictive migration scheduling based on carbon forecasts
- Add workload-aware migration policies (e.g., batch vs. interactive workloads)
- Extend report generator with PDF export and historical trend analysis
- Add REST API for external integration and monitoring dashboards
- Add reinforcement learning (DRL) for dynamic decision-making
- Expand to multi-objective optimization (carbon + cost + performance)
- Real-time dashboard for carbon metrics and migration decisions

## Getting Started

Install dependencies and run the sample orchestrator:

```bash
pip install -e .
python main.py
```

This will:
- Run the full orchestrator with live API data (or synthetic fallbacks)
- Generate a detailed HTML report (`migration_report.html`)
- Execute simulation scenarios for comparison

## Simulation Scenarios

The repository includes scenario simulators for testing different migration outcomes:

```bash
# Run all scenarios
python simulation.py

# Run individual scenarios
python simulation.py --happy      # Shows successful migration
python simulation.py --sad        # Shows no migration due to costs
python simulation.py --sla-blocked # Shows SLA constraint blocking
python simulation.py --real       # Uses orchestrator with current data
```

## Notes

- **API Integration**: Set `ELECTRICITYMAPS_API_KEY` and WattTime credentials in `.env` for live data
- **Fallback Behavior**: Uses synthetic data when APIs are unavailable
- **Report Viewing**: Open `migration_report.html` in any web browser after running `main.py`
- **TCN Training**: Automatically trains on historical data when sufficient samples are available
- **Decision Logic**: Only migrates when carbon savings > migration costs AND SLA constraints satisfied

