from typing import Any, Dict, List

from migration_cost_estimator import MigrationCostEstimator
from migration_engine import MigrationEngine
from services.carbon_forecaster import CarbonForecaster
from services.carbon_service import CarbonIntensityMonitor
from sla_classifier import SlaTierClassifier
from decision_engine import DecisionEngine


class Orchestrator:
    def __init__(self):
        self.monitor = CarbonIntensityMonitor()
        self.forecaster = CarbonForecaster(horizon_hours=4)
        self.sla_classifier = SlaTierClassifier()
        self.cost_estimator = MigrationCostEstimator(network_capacity_mbps=1000.0)
        self.decision_engine = DecisionEngine(self.cost_estimator, self.sla_classifier)
        self.migration_engine = MigrationEngine()

    def run_cycle(self, vm_inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        current_intensities = self.monitor.poll_once()
        forecasted_intensities: Dict[str, Dict[int, float]] = {}

        for zone in self.monitor.zones:
            history = self.monitor.get_history(zone)
            if len(history) >= self.forecaster.seq_len + self.forecaster.horizon_hours:
                self.forecaster.train(history, epochs=10)
            forecasted_intensities[zone] = self.forecaster.forecast(history)

        outcomes: List[Dict[str, Any]] = []
        for vm in vm_inventory:
            decision = self.decision_engine.evaluate(
                vm=vm,
                source_zone=vm["current_zone"],
                candidate_zones=self.monitor.zones,
                current_intensities=current_intensities,
                forecasted_intensities=forecasted_intensities,
            )

            if decision.should_migrate:
                migration_result = self.migration_engine.execute(
                    vm_id=decision.vm_id,
                    source_zone=decision.source_zone,
                    target_zone=decision.target_zone,
                    downtime_seconds=decision.estimated_downtime,
                )
                outcomes.append({"decision": decision, "migration": migration_result})
            else:
                outcomes.append({"decision": decision, "migration": None})

        return outcomes
