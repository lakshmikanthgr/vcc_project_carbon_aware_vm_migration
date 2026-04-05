import argparse
from typing import Any, Dict, List

from decision_engine import DecisionEngine
from migration_cost_estimator import MigrationCostEstimator
from orchestrator import Orchestrator
from sla_classifier import SlaTierClassifier


def print_decision(decision: Any) -> None:
    print(f"VM {decision.vm_id}: {decision.reason}")
    if decision.should_migrate:
        print(f"  Migrate from {decision.source_zone} to {decision.target_zone}")
        print(f"  Estimated downtime: {decision.estimated_downtime:.1f}s")
        print(f"  Net carbon saving: {decision.net_carbon_saving:.1f} gCO2")
    else:
        print("  No migration planned.")


def simulate_happy_path(engine: DecisionEngine) -> None:
    happy_vm = {
        "id": "vm-happy",
        "current_zone": "us-east",
        "size_gb": 8.0,
        "steady_power_kw": 1.0,
        "forecast_horizon_hours": 4.0,
        "sla_contract": {"latency_ms": 40, "critical": False},
        "runtime_metrics": {"cpu_utilization": 45.0, "dirty_rate": 8.0, "headroom": 60.0},
    }
    happy_current_intensities = {"us-east": 320.0, "us-west": 260.0, "eu-central": 110.0}
    happy_forecasts = {
        "us-east": {1: 320.0, 2: 315.0, 3: 310.0, 4: 305.0},
        "us-west": {1: 260.0, 2: 255.0, 3: 250.0, 4: 245.0},
        "eu-central": {1: 110.0, 2: 108.0, 3: 106.0, 4: 104.0},
    }

    print("=== Happy Path Scenario ===")
    decision = engine.evaluate(
        vm=happy_vm,
        source_zone=happy_vm["current_zone"],
        candidate_zones=list(happy_current_intensities.keys()),
        current_intensities=happy_current_intensities,
        forecasted_intensities=happy_forecasts,
    )
    print_decision(decision)


def simulate_sad_path(engine: DecisionEngine) -> None:
    sad_vm = {
        "id": "vm-sad",
        "current_zone": "us-east",
        "size_gb": 16.0,
        "steady_power_kw": 1.2,
        "forecast_horizon_hours": 3.0,
        "sla_contract": {"latency_ms": 15, "critical": True},
        "runtime_metrics": {"cpu_utilization": 88.0, "dirty_rate": 120.0, "headroom": 15.0},
    }
    sad_current_intensities = {"us-east": 280.0, "us-west": 250.0, "eu-central": 240.0}
    sad_forecasts = {
        "us-east": {1: 280.0, 2: 282.0, 3: 285.0, 4: 288.0},
        "us-west": {1: 250.0, 2: 252.0, 3: 254.0, 4: 256.0},
        "eu-central": {1: 240.0, 2: 242.0, 3: 245.0, 4: 248.0},
    }

    print("=== Sad Path Scenario ===")
    decision = engine.evaluate(
        vm=sad_vm,
        source_zone=sad_vm["current_zone"],
        candidate_zones=list(sad_current_intensities.keys()),
        current_intensities=sad_current_intensities,
        forecasted_intensities=sad_forecasts,
    )
    print_decision(decision)


def simulate_sla_blocked_path(engine: DecisionEngine) -> None:
    sla_blocked_vm = {
        "id": "vm-sla-blocked",
        "current_zone": "us-east",
        "size_gb": 64.0,
        "steady_power_kw": 1.5,
        "forecast_horizon_hours": 4.0,
        "sla_contract": {"latency_ms": 15, "critical": True},
        "runtime_metrics": {"cpu_utilization": 90.0, "dirty_rate": 95.0, "headroom": 10.0},
    }
    sla_blocked_intensities = {"us-east": 320.0, "us-west": 180.0, "eu-central": 170.0}
    sla_blocked_forecasts = {
        "us-east": {1: 320.0, 2: 318.0, 3: 315.0, 4: 312.0},
        "us-west": {1: 180.0, 2: 178.0, 3: 176.0, 4: 175.0},
        "eu-central": {1: 170.0, 2: 168.0, 3: 166.0, 4: 165.0},
    }

    print("=== SLA-Blocked Scenario ===")
    decision = engine.evaluate(
        vm=sla_blocked_vm,
        source_zone=sla_blocked_vm["current_zone"],
        candidate_zones=list(sla_blocked_intensities.keys()),
        current_intensities=sla_blocked_intensities,
        forecasted_intensities=sla_blocked_forecasts,
    )
    print_decision(decision)


def simulate_happy_sad_and_sla_blocked_paths() -> None:
    engine = DecisionEngine(MigrationCostEstimator(network_capacity_mbps=1000.0), SlaTierClassifier())
    simulate_happy_path(engine)
    print()
    simulate_sad_path(engine)
    print()
    simulate_sla_blocked_path(engine)


def simulate_real_case() -> None:
    orchestrator = Orchestrator()
    vm_inventory: List[Dict[str, Any]] = [
        {
            "id": "vm-real-01",
            "current_zone": "us-east",
            "size_gb": 24.0,
            "steady_power_kw": 1.2,
            "forecast_horizon_hours": 3.0,
            "sla_contract": {"latency_ms": 30, "critical": False},
            "runtime_metrics": {"cpu_utilization": 65.0, "dirty_rate": 25.0, "headroom": 35.0},
        },
        {
            "id": "vm-real-02",
            "current_zone": "eu-central",
            "size_gb": 48.0,
            "steady_power_kw": 1.6,
            "forecast_horizon_hours": 4.0,
            "sla_contract": {"latency_ms": 20, "critical": True},
            "runtime_metrics": {"cpu_utilization": 82.0, "dirty_rate": 60.0, "headroom": 18.0},
        },
    ]

    print("=== Real Case Scenario ===")
    results = orchestrator.run_cycle(vm_inventory)
    for item in results:
        decision = item["decision"]
        print_decision(decision)
        if item["migration"]:
            print(f"  migration: {item['migration']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CALM-SLA simulation scenarios.")
    parser.add_argument("--happy", action="store_true", help="Run the happy-path scenario.")
    parser.add_argument("--sad", action="store_true", help="Run the sad-path scenario.")
    parser.add_argument("--sla-blocked", action="store_true", help="Run the SLA-blocked scenario.")
    parser.add_argument("--real", action="store_true", help="Run the real-case Orchestrator scenario.")
    parser.add_argument("--all", action="store_true", help="Run all scenarios.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = DecisionEngine(MigrationCostEstimator(network_capacity_mbps=1000.0), SlaTierClassifier())

    if not any((args.happy, args.sad, args.sla_blocked, args.real, args.all)):
        args.all = True

    if args.all or args.happy:
        simulate_happy_path(engine)
    if args.all or args.sad:
        if args.all or args.happy:
            print()
        simulate_sad_path(engine)
    if args.all or args.sla_blocked:
        if args.all or args.happy or args.sad:
            print()
        simulate_sla_blocked_path(engine)
    if args.all or args.real:
        if args.all or args.happy or args.sad or args.sla_blocked:
            print()
        simulate_real_case()


if __name__ == "__main__":
    main()
