import os
from typing import Any, Dict, List

from migration_cost_estimator import MigrationCostEstimator
from migration_engine import MigrationEngine
from gcp_migration import GcpMigrationEngine
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
        self.migration_engine = self._create_migration_engine()

    def _create_migration_engine(self) -> MigrationEngine:
        project_id = os.getenv("GCP_PROJECT_ID")
        credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GCP_CREDENTIALS_FILE")
        if project_id:
            try:
                return GcpMigrationEngine(project_id=project_id, credentials_file=credentials_file)
            except ImportError as exception:
                print(f"GCP migration engine unavailable: {exception}")
        return MigrationEngine()

    def run_cycle(self, vm_inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        current_intensities = self.monitor.poll_once()
        forecasted_intensities: Dict[str, Dict[int, float]] = {}

        for zone in self.monitor.zones:
            history = self.monitor.get_history(zone)
            # Try to get WattTime forecast data
            watttime_forecast = self.monitor.get_forecast(zone, horizon_hours=self.forecaster.horizon_hours)
            if len(history) >= self.forecaster.seq_len + self.forecaster.horizon_hours:
                self.forecaster.train(history, epochs=10)
            forecasted_intensities[zone] = self.forecaster.forecast(history, watttime_forecast)

        outcomes: List[Dict[str, Any]] = []
        for vm in vm_inventory:
            decision = self.decision_engine.evaluate(
                vm=vm,
                source_zone=vm["current_zone"],
                candidate_zones=self.monitor.zones,
                current_intensities=current_intensities,
                forecasted_intensities=forecasted_intensities,
            )

            print(f"Decision for VM {vm['id']}: should_migrate={decision.should_migrate}, "
                  f"target_zone={decision.target_zone}, net_carbon_saving={decision.net_carbon_saving:.2f} gCO2, "
                  f"estimated_downtime={decision.estimated_downtime:.1f} seconds, reason={decision.reason}")

            if not decision.should_migrate:
                migration_result = self.migration_engine.execute(
                    vm_id=decision.vm_id,
                    source_zone=decision.source_zone,
                    target_zone=decision.target_zone,
                    downtime_seconds=decision.estimated_downtime,
                    vm_metadata=vm,
                )
                outcomes.append({"decision": decision, "migration": migration_result})
            else:
                outcomes.append({"decision": decision, "migration": None})

        return outcomes
