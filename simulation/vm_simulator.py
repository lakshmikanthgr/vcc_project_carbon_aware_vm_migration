"""
simulation/vm_simulator.py — Simulated VM fleet for CALM-SLA.

Defines the SimulatedVM dataclass and a factory that creates a fleet of
10 VMs across three SLA tiers, matching the deployment guide spec:

  3 Gold   (Critical)  — databases,   16 GB, dirty rate 50–150 MB/s
  3 Silver (Standard)  — web servers,  8 GB, dirty rate  5– 30 MB/s
  4 Bronze (Flexible)  — batch jobs,   4 GB, dirty rate  1– 10 MB/s

Runtime metrics drift each cycle via update_metrics() to simulate a
live workload. The fleet is the canonical VM inventory used by the
orchestrator, API, and dashboard.
"""

import random
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

from config.settings import DATA_CENTERS, SLA_DOWNTIME_LIMITS

Tier = Literal["Gold", "Silver", "Bronze"]

_ZONES = list(DATA_CENTERS.keys())


@dataclass
class SimulatedVM:
    vm_id:      str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:       str   = ""
    tier:       Tier  = "Bronze"
    current_zone: str = "DK-DK1"

    # Hardware profile
    size_gb:         float = 4.0
    steady_power_kw: float = 0.5

    # SLA contract
    latency_ms:   float = 200.0
    critical:     bool  = False

    # Runtime metrics (drift each cycle)
    cpu_utilization: float = 0.3   # 0.0–1.0
    dirty_rate:      float = 5.0   # MB/s
    headroom:        float = 70.0  # % slack before SLA breach

    # Lifecycle counters
    migration_count: int = 0
    sla_violations:  int = 0
    is_migrating:    bool = False

    #  Derived horizon ─
    @property
    def forecast_horizon_hours(self) -> float:
        return {"Gold": 2.0, "Silver": 3.0, "Bronze": 4.0}[self.tier]

    @property
    def max_downtime_s(self) -> float:
        return SLA_DOWNTIME_LIMITS[self.tier]

    #  Dict conversion for existing engine interfaces 
    def to_dict(self) -> Dict[str, Any]:
        """Convert to the dict format expected by DecisionEngine.evaluate()."""
        return {
            "id":                   self.vm_id,
            "current_zone":         self.current_zone,
            "size_gb":              self.size_gb,
            "steady_power_kw":      self.steady_power_kw,
            "forecast_horizon_hours": self.forecast_horizon_hours,
            "sla_contract": {
                "latency_ms": self.latency_ms,
                "critical":   self.critical,
            },
            "runtime_metrics": {
                "cpu_utilization": self.cpu_utilization * 100,  # engine expects 0–100
                "dirty_rate":      self.dirty_rate,
                "headroom":        self.headroom,
            },
        }

    #  Metric drift 
    def update_metrics(self) -> None:
        """Drift CPU, dirty rate, and headroom slightly to simulate live load."""
        self.cpu_utilization = float(
            max(0.05, min(0.98, self.cpu_utilization + random.gauss(0, 0.03)))
        )
        self.dirty_rate = float(
            max(0.5, min(200.0, self.dirty_rate + random.gauss(0, 2.0)))
        )
        self.headroom = float(
            max(5.0, min(95.0, self.headroom + random.gauss(0, 2.0)))
        )


#  Factory ─

def create_vm_fleet() -> List[SimulatedVM]:
    """
    Create the canonical 10-VM fleet as specified in the deployment guide.
    Zones are distributed evenly across available data centers at startup.
    """
    fleet: List[SimulatedVM] = []

    # 3 Gold VMs — databases, strict SLA
    for i in range(3):
        fleet.append(SimulatedVM(
            name             = f"db-gold-{i+1}",
            tier             = "Gold",
            current_zone     = _ZONES[i % len(_ZONES)],
            size_gb          = 16.0,
            steady_power_kw  = 1.5,
            latency_ms       = 15.0,
            critical         = True,
            cpu_utilization  = random.uniform(0.65, 0.85),
            dirty_rate       = random.uniform(50.0, 150.0),
            headroom         = random.uniform(10.0, 25.0),
        ))

    # 3 Silver VMs — web servers, moderate SLA
    for i in range(3):
        fleet.append(SimulatedVM(
            name             = f"web-silver-{i+1}",
            tier             = "Silver",
            current_zone     = _ZONES[(i + 1) % len(_ZONES)],
            size_gb          = 8.0,
            steady_power_kw  = 1.0,
            latency_ms       = 50.0,
            critical         = False,
            cpu_utilization  = random.uniform(0.40, 0.65),
            dirty_rate       = random.uniform(5.0, 30.0),
            headroom         = random.uniform(35.0, 55.0),
        ))

    # 4 Bronze VMs — batch jobs, flexible SLA
    for i in range(4):
        fleet.append(SimulatedVM(
            name             = f"batch-bronze-{i+1}",
            tier             = "Bronze",
            current_zone     = _ZONES[(i + 2) % len(_ZONES)],
            size_gb          = 4.0,
            steady_power_kw  = 0.5,
            latency_ms       = 200.0,
            critical         = False,
            cpu_utilization  = random.uniform(0.15, 0.40),
            dirty_rate       = random.uniform(1.0, 10.0),
            headroom         = random.uniform(60.0, 85.0),
        ))

    return fleet


#  Singleton fleet (shared across orchestrator, API, dashboard) 
vm_fleet: List[SimulatedVM] = create_vm_fleet()
