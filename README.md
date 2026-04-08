# CALM-SLA: Carbon-Aware Live VM Migration Framework with SLA Guarantees

## Project Overview

CALM-SLA is a Python framework for reducing the carbon footprint of VM workloads while preserving Service Level Agreements (SLAs). It uses live grid carbon-intensity signals, SLA classification, migration cost modeling, and forecasted savings to recommend or execute migrations only when the result is net carbon positive and SLA-safe.

The framework supports both:
- **Live data reports** using real API measurements from WattTime and ElectricityMaps
- **Simulated reports** using synthetic scenarios for testing and demonstrations

**Primary goals:**
- Reduce carbon emissions from VM placement
- Avoid SLA violations for latency-sensitive workloads
- Make migration decisions transparent with detailed report output
- Support optional real migration execution for Google Cloud Platform (GCP)

## Architecture

The main orchestration flow is:
1. `Orchestrator` collects carbon intensities from `CarbonIntensityMonitor`
2. `CarbonForecaster` predicts future intensities for each region
3. `SlaTierClassifier` assigns each VM a Gold/Silver/Bronze tier
4. `DecisionEngine` evaluates candidate migrations using carbon savings, migration costs, and SLA rules
5. If approved, the configured migration engine executes the migration
6. `ReportGenerator` writes detailed HTML reports for live and simulated runs

## Project Components

1. **Carbon Intensity Monitor** (`services/carbon_service.py`)
   - Polls ElectricityMaps and WattTime APIs for zone-level carbon intensity data
   - Stores individual measurements for transparency in reports
   - Aggregates readings from multiple sources to improve reliability
   - Maintains a history buffer for forecasting
   - Falls back to synthetic values when APIs are unavailable

2. **TCN Carbon Forecaster** (`services/carbon_forecaster.py`)
   - Uses a Temporal Convolutional Network to forecast carbon intensity
   - Forecasts 1–4 hours ahead per monitored region
   - Trains automatically when enough historical samples exist
   - Falls back to simple forecast heuristics if the model is not ready

3. **SLA-Tier Classifier** (`sla_classifier.py`)
   - Classifies VMs into `Gold`, `Silver`, or `Bronze`
   - Uses SLA contract fields and runtime metrics (`latency_ms`, `critical`, `cpu_utilization`, `dirty_rate`, `headroom`)
   - Enforces stricter downtime limits for Gold and Silver workloads

4. **Migration Cost Estimator** (`migration_cost_estimator.py`)
   - Estimates migration overhead and carbon cost
   - Includes VM size, dirty page rate, and network capacity

5. **Decision Engine** (`decision_engine.py`)
   - Computes projected carbon savings and migration cost
   - Applies SLA constraints for each candidate migration
   - Uses forecasted intensities to estimate net benefit over the migration horizon

6. **Migration Engine** (`migration_engine.py`)
   - Default fallback engine with no real migration behavior

7. **GCP Migration Engine** (`gcp_migration.py`)
   - Optional real migration support for Google Cloud Platform
   - Creates a boot disk snapshot, clones it into the target zone, and launches a new instance
   - Enabled when `GCP_PROJECT_ID` is set and `google-auth` + `google-api-python-client` are installed

8. **Orchestrator** (`orchestrator.py`)
   - Coordinates polling, forecasting, decision-making, and migration execution
   - Automatically chooses `GcpMigrationEngine` when GCP credentials are configured
   - Falls back to the stub `MigrationEngine` otherwise

9. **Report Generator** (`report_generator.py`)
   - Creates HTML reports with per-VM decision details
   - Generates both `migration_report_live.html` and `migration_report_simulated.html`
   - Includes API measurement tables and candidate-zone evaluations

10. **Simulation Module** (`simulation.py`)
    - Produces test cases for happy, sad, and SLA-blocked migration decisions
    - Supports CLI flags to run specific scenarios

## Live vs Simulated Reports

The repository now generates two report files:
- `migration_report_live.html`: uses real carbon intensity data pulled from the APIs
- `migration_report_simulated.html`: uses artificial scenarios for demonstration

### `main.py` behavior
- `generate_live_data_report()` executes one orchestration cycle and writes the live report
- `generate_simulated_data_report()` captures predefined VM scenarios and writes the simulated report

## GCP Migration Support

Real migration support is triggered when `GCP_PROJECT_ID` is configured and the required GCP Python packages are installed.

### Required environment variables
- `GCP_PROJECT_ID`
- `GOOGLE_APPLICATION_CREDENTIALS` or `GCP_CREDENTIALS_FILE`

### Optional GCP environment settings
- `WATTTIME_USING_API_URL` to override the WattTime base URL

### VM metadata required for the GCP migration path
Each VM entry must include:
- `gcp_instance_name`
- `gcp_source_zone`
- `gcp_target_zone`

Optional metadata fields:
- `gcp_target_instance_name`
- `gcp_target_disk_name`
- `gcp_project_id` to override the default project for a specific VM

### How it works
The GCP migration engine:\n1. Fetches source instance metadata
2. Locates the boot disk
3. Creates a snapshot in the source zone
4. Clones the snapshot into a target disk in the target zone
5. Spins up a new VM instance in the target zone

If GCP configuration is missing or packages are unavailable, the orchestrator uses the default stub engine instead.

## Requirements

### Software
- Python >= 3.10
- Core dependencies in `pyproject.toml`
- Optional packages for GCP migration:
  - `google-auth`
  - `google-api-python-client`

### API Keys
- `ELECTRICITYMAPS_API_KEY`
- `WATTTIME_USERNAME`
- `WATTTIME_PASSWORD`
- `WATTTIME_USER_EMAIL`
- `WATTTIME_ORG`

### Environment Setup
Example `.env` entries:

```ini
ELECTRICITYMAPS_API_KEY=your_electricitymaps_key
WATTTIME_USERNAME=your_watttime_username
WATTTIME_PASSWORD=your_watttime_password
WATTTIME_USER_EMAIL=your_watttime_email
WATTTIME_ORG=your_watttime_org
GCP_PROJECT_ID=your_gcp_project
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

### Install and run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python main.py
```

## Usage Examples
- Run the orchestrator with live data: `python main.py`
- Generate only the simulation report: `python simulation.py`
- Execute a single scenario: `python simulation.py --sla-blocked`
- Open the generated HTML files in a browser:
  - `migration_report_live.html`
  - `migration_report_simulated.html`

## Report Features

### What is included in each report
- VM metadata, SLA tier, and runtime profile
- Current and forecasted carbon intensities per zone
- Candidate target-zone evaluation table
- Migration cost, projected savings, net saving, and feasibility
- Decision explanation for each VM
- Live API measurement visibility when available
- Simulation scenario breakdown for test cases

### API measurement support
The live report shows a per-zone API measurement table for:
- `WattTime` carbon intensity readings
- `ElectricityMaps` carbon intensity readings

Each row includes a source label, the reported intensity, and a status marker:
- `✓ Live` when fresh data is present
- `⚠️ Fallback` when fallback or synthetic data is used

## Technical Notes

### SLA tier rules
- `Gold`: critical workloads, strict downtime limit (≤60s)
- `Silver`: moderate sensitivity, downtime limit (≤180s)
- `Bronze`: flexible workloads with no strict downtime threshold

### How decisions are made
The system only recommends migration when:
- a target zone has lower carbon intensity than the source
- migration carbon cost is less than estimated savings over the forecast horizon
- the estimated downtime passes the VM's SLA tier check

## Future Enhancements
- Add additional carbon intensity sources and regions
- Improve forecast accuracy with richer historical data
- Add persistent storage for historical measurements
- Support more cloud providers beyond GCP
- Add PDF and historical trend exports for reports

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

