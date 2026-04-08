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
   - Tracks individual API measurements (WattTime CO2 and ElectricityMaps CO2) for transparency
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
   - Creates two report types:
     - Live data report: Real API measurements from WattTime and ElectricityMaps
     - Simulated data report: Test scenarios with predefined intensities
   - Displays individual API measurements with source attribution:
     - WattTime CO2 intensity values (gCO2/MWh)
     - ElectricityMaps CO2 intensity values (gCO2/MWh)
     - Status indicators (✓ Live or ⚠️ Fallback)
   - Shows carbon intensity comparisons across zones
   - Includes SLA checks and migration cost calculations
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
- **View live data report**: Open `migration_report_live.html` in a web browser (shows real API data)
- **View simulated test report**: Open `migration_report_simulated.html` in a web browser (shows test scenarios)
- **Compare reports**: Open both reports side-by-side to compare live vs. simulated scenarios
- **Train and forecast**: The orchestrator auto-trains the TCN when history is sufficient

## Report Features

The framework generates two comprehensive HTML reports with detailed migration analysis:

### 📊 Report Types

#### 1. **Live Data Report** (`migration_report_live.html`)
Analyzes real-time carbon intensity data fetched from external APIs:
- **Real Carbon Intensity Data**: WattTime and ElectricityMaps CO2 measurements (gCO2/MWh)
- **Live API Measurements Table**: Shows individual readings from each data source
  - WattTime API: Real-time carbon signal index
  - ElectricityMaps API: Carbon intensity from grid monitoring
  - Data source status indicators (✓ Live or ⚠️ Fallback)
- **Zone Comparison**: Current and forecasted intensities across all regions
- **Migration Decisions**: Based on actual live carbon data
- **Aggregated Data**: Average of WattTime and ElectricityMaps for final decision-making

#### 2. **Simulated Data Report** (`migration_report_simulated.html`)
Demonstrates different migration scenarios with predefined test data:
- **Happy Path**: VM successfully migrates with carbon savings
- **Sad Path**: No migration due to insufficient carbon benefits
- **SLA-Blocked Path**: Migration blocked by strict SLA constraints
- **Test Intensities**: Artificial carbon values to showcase different outcomes

### 📡 API Data Displayed in Reports

Each VM analysis includes a dedicated **API Measurements** section showing:

| Data Source | CO2 Intensity (gCO2/MWh) | Status |
|---|---|---|
| **ElectricityMaps** | Real value from API | ✓ Live |
| **WattTime** | Real value from API | ✓ Live |

**Example Output** (from Live Report):
- DK-DK1: ElectricityMaps (0.0) | WattTime (97.0 gCO2/MWh)
- DE: ElectricityMaps (0.0) | WattTime (26.0 gCO2/MWh)
- SE: ElectricityMaps (0.0) | WattTime (68.0 gCO2/MWh)

### 📋 Report Contents

Both reports include:

1. **Summary Dashboard**
   - Total VMs analyzed
   - Number of migrations recommended
   - Total potential carbon savings (gCO2)

2. **Per-VM Analysis**
   - VM metadata (ID, zone, size, power consumption, SLA tier)
   - Current and forecasted carbon intensities
   - **🔍 API Measurements**: Individual readings from WattTime and ElectricityMaps APIs
   - **📡 Data Sources**: Explanation of data sources and aggregation method
   - Candidate zone evaluation table with:
     - Target zone intensity (average)
     - Projected carbon savings
     - Migration cost in gCO2
     - Net carbon saving (savings - cost)
     - SLA compliance check
     - Feasibility status

3. **Decision Breakdown**
   - ✓ MIGRATE or ✗ NO MIGRATION decision
   - Reason for decision (why migration was approved/rejected)
   - If migrating: target zone, downtime, and net savings

4. **Data Source Attribution**
   - Update frequency (polled every 5 minutes)
   - Fallback behavior when APIs are unavailable
   - Aggregation method (average of both sources)

### 🔧 How API Data is Processed

```
WattTime API → Fetch signal-index (gCO2/MWh for region)
ElectricityMaps API → Fetch carbon-intensity (gCO2/MWh for zone)
                     ↓
          Aggregate: (WattTime + ElectricityMaps) / 2
                     ↓
            Final Carbon Intensity Value
                     ↓
        Used in Migration Decision Logic
```

### 📍 Zones & Coordinates Monitored

The reports track carbon intensities across these regions:
- **DK-DK1**: Denmark (56.0°N, 8.5°E)
- **DE**: Germany (51.17°N, 10.45°E)
- **SE**: Sweden (60.13°N, 18.64°E)
- **US-AK**: Alaska (64.20°N, -152.28°W)

### 💡 Key Metrics Explained

- **gCO2/MWh**: Grams of CO2 equivalent per megawatt-hour of electricity
- **Projected Savings**: (Source Intensity - Target Intensity) × Power × Runtime
- **Migration Cost**: Carbon cost of transferring data during migration
- **Net Saving**: Operational savings minus migration overhead
- **SLA Tier Limits**:
  - Gold: ≤60 seconds downtime (critical workloads)
  - Silver: ≤180 seconds downtime (moderate sensitivity)
  - Bronze: Flexible (non-sensitive workloads)

Reports are automatically saved as `migration_report_live.html` and `migration_report_simulated.html` and can be opened in any web browser.

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
- **Report Viewing**: Open `migration_report_live.html` or `migration_report_simulated.html` in any web browser
  - Live report shows real API measurements (WattTime and ElectricityMaps CO2 values)
  - Simulated report demonstrates different migration scenarios with test data
- **API Measurements Table**: Both reports display individual API readings with source attribution and status indicators
- **Data Sources**: Each VM section includes a table showing:
  - WattTime API CO2 intensity (gCO2/MWh)
  - ElectricityMaps API CO2 intensity (gCO2/MWh)
  - Live/Fallback status for each source
- **TCN Training**: Automatically trains on historical data when sufficient samples are available
- **Decision Logic**: Only migrates when carbon savings > migration costs AND SLA constraints satisfied
- **Report Generation**: Generates two reports in parallel:
  - `migration_report_live.html`: Real-time data from APIs
  - `migration_report_simulated.html`: Test scenarios for validation

