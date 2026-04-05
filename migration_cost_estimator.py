from typing import Dict


class MigrationCostEstimator:
    def __init__(self, network_capacity_mbps: float = 1000.0, energy_per_gb_kwh: float = 0.25):
        self.network_capacity_mbps = network_capacity_mbps
        self.energy_per_gb_kwh = energy_per_gb_kwh

    def estimate(self, vm_size_gb: float, dirty_rate_mb_s: float, intensity_gco2: float) -> Dict[str, float]:
        traffic_multiplier = 1.0 + min(1.0, dirty_rate_mb_s / 100.0)
        traffic_gb = vm_size_gb * traffic_multiplier
        transfer_seconds = (traffic_gb * 8_000.0) / self.network_capacity_mbps
        downtime_seconds = max(5.0, min(900.0, transfer_seconds * min(1.0, dirty_rate_mb_s / 100.0)))
        carbon_cost = traffic_gb * self.energy_per_gb_kwh * intensity_gco2

        return {
            "traffic_gb": traffic_gb,
            "transfer_seconds": transfer_seconds,
            "downtime_seconds": downtime_seconds,
            "carbon_cost_gco2": carbon_cost,
        }
