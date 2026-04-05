from dataclasses import dataclass
from typing import Any, Dict, List

from migration_cost_estimator import MigrationCostEstimator
from sla_classifier import SlaTier, SlaTierClassifier


@dataclass
class Decision:
    vm_id: str
    source_zone: str
    target_zone: str
    should_migrate: bool
    net_carbon_saving: float
    estimated_downtime: float
    reason: str


class DecisionEngine:
    def __init__(self, cost_estimator: MigrationCostEstimator, sla_classifier: SlaTierClassifier):
        self.cost_estimator = cost_estimator
        self.sla_classifier = sla_classifier

    def evaluate(
        self,
        vm: Dict[str, Any],
        source_zone: str,
        candidate_zones: List[str],
        current_intensities: Dict[str, float],
        forecasted_intensities: Dict[str, Dict[int, float]],
    ) -> Decision:
        sla_tier = self.sla_classifier.classify(vm["sla_contract"], vm["runtime_metrics"])
        source_intensity = current_intensities[source_zone]
        source_forecast = forecasted_intensities.get(source_zone, {})
        source_avg = (sum(source_forecast.values()) / len(source_forecast)) if source_forecast else source_intensity

        best_decision = Decision(
            vm_id=vm["id"],
            source_zone=source_zone,
            target_zone=source_zone,
            should_migrate=False,
            net_carbon_saving=0.0,
            estimated_downtime=0.0,
            reason="No candidate zone produced net carbon savings while preserving SLA guarantees.",
        )

        for target_zone in candidate_zones:
            if target_zone == source_zone:
                continue

            target_forecast = forecasted_intensities.get(target_zone, {})
            target_avg = (sum(target_forecast.values()) / len(target_forecast)) if target_forecast else current_intensities[target_zone]
            estimated_runtime_hours = float(vm.get("forecast_horizon_hours", 2.0))
            steady_power_kw = float(vm.get("steady_power_kw", 1.0))
            projected_savings = max(0.0, source_avg - target_avg) * steady_power_kw * estimated_runtime_hours

            migration_metrics = self.cost_estimator.estimate(
                vm_size_gb=float(vm.get("size_gb", 16.0)),
                dirty_rate_mb_s=float(vm["runtime_metrics"].get("dirty_rate", 10.0)),
                intensity_gco2=source_intensity,
            )

            net_saving = projected_savings - migration_metrics["carbon_cost_gco2"]
            downtime_seconds = migration_metrics["downtime_seconds"]

            if sla_tier == SlaTier.GOLD and downtime_seconds > 60.0:
                continue
            if sla_tier == SlaTier.SILVER and downtime_seconds > 180.0:
                continue

            if net_saving > best_decision.net_carbon_saving and net_saving > 0.0:
                best_decision = Decision(
                    vm_id=vm["id"],
                    source_zone=source_zone,
                    target_zone=target_zone,
                    should_migrate=True,
                    net_carbon_saving=net_saving,
                    estimated_downtime=downtime_seconds,
                    reason=(
                        f"Move from {source_zone} to {target_zone} yields {net_saving:.1f} gCO2 savings "
                        f"with estimated downtime {downtime_seconds:.1f}s for SLA tier {sla_tier.value}."
                    ),
                )

        return best_decision
