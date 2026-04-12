"""
drl_decision_engine.py — DRL-powered migration decision engine.

Drop-in replacement for DecisionEngine (greedy rule-based).
Uses the trained DQN model to decide whether and where to migrate each VM.

Falls back to the greedy DecisionEngine if the model file is not found,
so the system always runs — even before training is complete.

Usage:
  from drl_decision_engine import DRLDecisionEngine
  engine = DRLDecisionEngine()
  decision = engine.evaluate(vm, source_zone, candidate_zones,
                             current_intensities, forecasted_intensities)
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from decision_engine import Decision, DecisionEngine
from migration_cost_estimator import MigrationCostEstimator
from sla_classifier import SlaTier, SlaTierClassifier
from drl_environment import CALMSLAEnv, ZONES, N_ZONES

MODEL_PATH = Path("data/models/drl_agent")


class DRLDecisionEngine:
    """
    Wraps a trained SB3 DQN model.
    Falls back to the greedy DecisionEngine when model is unavailable.
    """

    def __init__(
        self,
        model_path: Path = MODEL_PATH,
        cost_estimator: Optional[MigrationCostEstimator] = None,
        sla_classifier: Optional[SlaTierClassifier] = None,
    ):
        self.cost_estimator = cost_estimator or MigrationCostEstimator(network_capacity_mbps=1000.0)
        self.sla_classifier  = sla_classifier or SlaTierClassifier()
        self._greedy = DecisionEngine(self.cost_estimator, self.sla_classifier)
        self.model = None
        self._load_model(model_path)

    def _load_model(self, path: Path) -> None:
        model_zip = path.with_suffix(".zip")
        if not model_zip.exists():
            print(f"[DRL] Model not found at {model_zip} — using greedy fallback.")
            return
        try:
            from stable_baselines3 import DQN
            self.model = DQN.load(str(path))
            print(f"[DRL] Model loaded from {model_zip}")
        except Exception as exc:
            print(f"[DRL] Failed to load model ({exc}) — using greedy fallback.")

    # ------------------------------------------------------------------ #
    # Build the observation vector from live orchestrator data
    # ------------------------------------------------------------------ #
    def _build_obs(
        self,
        vm: Dict[str, Any],
        current_intensities: Dict[str, float],
        forecasted_intensities: Dict[str, Dict[int, float]],
    ) -> np.ndarray:
        rm   = vm.get("runtime_metrics", {})
        tier = self.sla_classifier.classify(vm["sla_contract"], rm)

        dt_limit = {SlaTier.GOLD: 60.0, SlaTier.SILVER: 180.0, SlaTier.BRONZE: 900.0}[tier]

        obs = []
        # Current carbon intensity per zone (normalised /800)
        for zone in ZONES:
            obs.append(min(current_intensities.get(zone, 300.0) / 800.0, 1.0))
        # Mean forecast per zone
        for zone in ZONES:
            fc = forecasted_intensities.get(zone, {})
            mean_fc = float(np.mean(list(fc.values()))) if fc else current_intensities.get(zone, 300.0)
            obs.append(min(mean_fc / 800.0, 1.0))
        # VM metrics
        obs.append(float(np.clip(rm.get("cpu_utilization", 50.0) / 100.0, 0.0, 1.0)))
        obs.append(min(rm.get("dirty_rate", 10.0) / 200.0, 1.0))
        obs.append({SlaTier.GOLD: 1.0, SlaTier.SILVER: 0.5, SlaTier.BRONZE: 0.0}[tier])
        obs.append(min(dt_limit / 900.0, 1.0))
        # Current zone one-hot
        source_zone = vm.get("current_zone", ZONES[0])
        for zone in ZONES:
            obs.append(1.0 if zone == source_zone else 0.0)
        return np.array(obs, dtype=np.float32)

    # ------------------------------------------------------------------ #
    # Public API — same signature as DecisionEngine.evaluate()
    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        vm: Dict[str, Any],
        source_zone: str,
        candidate_zones: List[str],
        current_intensities: Dict[str, float],
        forecasted_intensities: Dict[str, Dict[int, float]],
    ) -> Decision:
        # Fall back to greedy if model not loaded
        if self.model is None:
            return self._greedy.evaluate(
                vm, source_zone, candidate_zones,
                current_intensities, forecasted_intensities,
            )

        obs = self._build_obs(vm, current_intensities, forecasted_intensities)
        action, _ = self.model.predict(obs, deterministic=True)
        action = int(action)

        # Action 0 = stay
        if action == 0:
            return Decision(
                vm_id           = vm["id"],
                source_zone     = source_zone,
                target_zone     = source_zone,
                should_migrate  = False,
                net_carbon_saving = 0.0,
                estimated_downtime= 0.0,
                reason          = "[DRL] Agent chose to stay — no beneficial migration found.",
            )

        # Action 1..N = migrate to ZONES[action-1]
        target_zone = ZONES[action - 1]

        # Guard: don't migrate to same zone
        if target_zone == source_zone:
            return Decision(
                vm_id           = vm["id"],
                source_zone     = source_zone,
                target_zone     = source_zone,
                should_migrate  = False,
                net_carbon_saving = 0.0,
                estimated_downtime= 0.0,
                reason          = "[DRL] Agent selected current zone — no action taken.",
            )

        # Compute cost and savings for the Decision record
        tier = self.sla_classifier.classify(vm["sla_contract"], vm.get("runtime_metrics", {}))
        cost_metrics = self.cost_estimator.estimate(
            vm_size_gb      = float(vm.get("size_gb", 16.0)),
            dirty_rate_mb_s = float(vm.get("runtime_metrics", {}).get("dirty_rate", 10.0)),
            intensity_gco2  = current_intensities.get(source_zone, 220.0),
        )
        downtime_s  = cost_metrics["downtime_seconds"]
        carbon_cost = cost_metrics["carbon_cost_gco2"]

        # SLA gate — hard constraint even after DRL decision
        dt_limit = {SlaTier.GOLD: 60.0, SlaTier.SILVER: 180.0, SlaTier.BRONZE: 900.0}[tier]
        if downtime_s > dt_limit:
            return Decision(
                vm_id            = vm["id"],
                source_zone      = source_zone,
                target_zone      = source_zone,
                should_migrate   = False,
                net_carbon_saving= 0.0,
                estimated_downtime= downtime_s,
                reason=(
                    f"[DRL] Agent suggested {target_zone} but SLA gate blocked: "
                    f"downtime {downtime_s:.1f}s > {dt_limit:.0f}s limit for {tier.value}."
                ),
            )

        # Compute net saving for the decision record
        source_fc  = forecasted_intensities.get(source_zone, {})
        target_fc  = forecasted_intensities.get(target_zone, {})
        source_avg = float(np.mean(list(source_fc.values()))) if source_fc else current_intensities.get(source_zone, 220.0)
        target_avg = float(np.mean(list(target_fc.values()))) if target_fc else current_intensities.get(target_zone, 220.0)
        power_kw   = float(vm.get("steady_power_kw", 1.0))
        horizon_h  = float(vm.get("forecast_horizon_hours", 4.0))
        net_saving = max(0.0, source_avg - target_avg) * power_kw * horizon_h - carbon_cost

        if net_saving <= 0:
            return Decision(
                vm_id            = vm["id"],
                source_zone      = source_zone,
                target_zone      = source_zone,
                should_migrate   = False,
                net_carbon_saving= 0.0,
                estimated_downtime= downtime_s,
                reason=(
                    f"[DRL] Agent suggested {target_zone} but net saving is negative "
                    f"({net_saving:.1f} gCO2) — migration cost exceeds benefit."
                ),
            )

        return Decision(
            vm_id            = vm["id"],
            source_zone      = source_zone,
            target_zone      = target_zone,
            should_migrate   = True,
            net_carbon_saving= net_saving,
            estimated_downtime= downtime_s,
            reason=(
                f"[DRL] Agent recommends {source_zone}→{target_zone}: "
                f"{net_saving:.1f} gCO2 net saving, downtime {downtime_s:.1f}s "
                f"(SLA tier {tier.value})."
            ),
        )
