from dotenv import load_dotenv

from orchestrator import Orchestrator
from simulation import simulate_happy_sad_and_sla_blocked_paths, simulate_real_case


def main() -> None:
    # Load environment variables from .env file
    load_dotenv()
    orchestrator = Orchestrator()
    sample_vms = [
        {
            "id": "vm-1",
            "current_zone": "us-east",
            "size_gb": 32.0,
            "steady_power_kw": 1.25,
            "forecast_horizon_hours": 3.0,
            "sla_contract": {"latency_ms": 15, "critical": True},
            "runtime_metrics": {"cpu_utilization": 72.0, "dirty_rate": 20.0, "headroom": 25.0},
        },
        {
            "id": "vm-2",
            "current_zone": "eu-central",
            "size_gb": 16.0,
            "steady_power_kw": 0.9,
            "forecast_horizon_hours": 4.0,
            "sla_contract": {"latency_ms": 40, "critical": False},
            "runtime_metrics": {"cpu_utilization": 52.0, "dirty_rate": 10.0, "headroom": 50.0},
        },
        {
            "id": "vm-3",
            "current_zone": "us-west",
            "size_gb": 8.0,
            "steady_power_kw": 0.7,
            "forecast_horizon_hours": 2.0,
            "sla_contract": {"latency_ms": 100, "critical": False},
            "runtime_metrics": {"cpu_utilization": 35.0, "dirty_rate": 5.0, "headroom": 75.0},
        },
    ]

    results = orchestrator.run_cycle(sample_vms)
    for item in results:
        decision = item["decision"]
        print(f"VM {decision.vm_id}: {decision.reason}")
        if item["migration"]:
            print(f"  migration: {item['migration']}")


if __name__ == "__main__":
    main()
    print("\n--- Simulation Scenarios ---")
    simulate_happy_sad_and_sla_blocked_paths()
    simulate_real_case()
