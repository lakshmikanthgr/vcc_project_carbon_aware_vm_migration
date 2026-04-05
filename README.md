# CALM-SLA

## Carbon-Aware Live VM Migration Framework with SLA Guarantees

Modern cloud environments host thousands of VMs across geographically distributed data centers with varying energy mixes. Traditional schedulers optimize for cost or utilization, but ignore grid carbon intensity. CALM-SLA continuously monitors carbon signals and migrates VMs only when savings outweigh migration overhead while preserving SLA constraints.

## Components

- `Carbon Intensity Monitor`
  - Polls ElectricityMaps and WattTime APIs for zone-level `gCO2eq/kWh`
  - Exposes current readings and history for each data center

- `TCN Carbon Forecaster`
  - Trainable PyTorch Temporal Convolutional Network
  - Projects carbon intensity 1–4 hours ahead per zone

- `SLA-Tier Classifier`
  - Labels VMs as `Gold`, `Silver`, or `Bronze`
  - Uses SLA contract terms plus live runtime metrics such as CPU utilization, dirty rate, and headroom

- `Migration Cost Estimator`
  - Models pre-copy migration overhead
  - Estimates bandwidth consumption, downtime, and carbon cost of migration traffic

- `Decision Engine`
  - Computes net carbon benefit of live migration
  - Accounts for forecasted intensities, migration overhead, and SLA guarantees

- `Migration Engine`
  - Executes migration actions when the decision engine approves them

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
