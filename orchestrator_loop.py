"""
orchestrator_loop.py — Continuous orchestration loop for CALM-SLA.

Runs one migration decision cycle every POLL_INTERVAL seconds using the
canonical 10-VM SimulatedVM fleet. VM runtime metrics drift each cycle
to simulate a live workload. All decisions and carbon readings are
persisted to SQLite automatically.

Usage:
  python orchestrator_loop.py              # default 300s interval
  POLL_INTERVAL=60 python orchestrator_loop.py   # faster for testing
  USE_DRL=true python orchestrator_loop.py       # use trained DRL agent
"""
import os
import time
from dotenv import load_dotenv
from orchestrator import Orchestrator
from simulation.vm_simulator import vm_fleet

load_dotenv()

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))


def main():
    print(f"Orchestrator loop starting — {len(vm_fleet)} VMs, interval={POLL_INTERVAL}s")
    orchestrator = Orchestrator(persist=True)
    cycle = 0

    while True:
        cycle += 1
        print(f"\n[Cycle {cycle}] {time.strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            # Drift VM runtime metrics each cycle to simulate live workload
            for vm in vm_fleet:
                vm.update_metrics()

            vm_dicts = [vm.to_dict() for vm in vm_fleet]
            results = orchestrator.run_cycle(vm_dicts)
            migrations = sum(1 for r in results if r["decision"].should_migrate)

            # Show tier breakdown
            tiers: dict = {}
            for vm in vm_fleet:
                tiers[vm.tier] = tiers.get(vm.tier, 0) + 1
            print(f"  Fleet: {tiers}")
            print(f"  {len(results)} VMs evaluated | {migrations} migration(s) approved")

        except Exception as exc:
            print(f"  [ERROR] Cycle failed: {exc}")

        print(f"  Next cycle in {POLL_INTERVAL}s ...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
