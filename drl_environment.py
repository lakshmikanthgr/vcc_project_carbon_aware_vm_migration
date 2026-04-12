"""
drl_environment.py — Gymnasium environment for CALM-SLA DRL agent.

State vector (10 dimensions):
  [0-2]  carbon_now per zone,      normalised /800
  [3-5]  carbon_forecast_mean,     normalised /800
  [6]    cpu_utilisation           0.0-1.0
  [7]    dirty_rate                normalised /200
  [8]    sla_tier_encoding         Gold=1.0, Silver=0.5, Bronze=0.0
  [9]    sla_headroom              normalised (downtime_limit / 900s)

Action space (N+1 discrete):
  0      Stay — do nothing
  1..N   Migrate to zone[i-1]

Reward:
  +ALPHA * net_carbon_saved_normalised
  -BETA  * migration_carbon_cost_normalised
  -GAMMA[tier] * sla_violation_flag

GAMMA: Gold=10.0, Silver=3.0, Bronze=0.5
"""

import math
import random
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from sla_classifier import SlaTier, SlaTierClassifier
from migration_cost_estimator import MigrationCostEstimator

# Zones the agent can migrate between
ZONES = ["DK-DK1", "DE", "SE", "US-AK"]
N_ZONES = len(ZONES)

# Reward weights (from deployment guide)
ALPHA = 1.0   # carbon savings weight
BETA  = 0.3   # migration cost penalty
GAMMA = {     # SLA violation penalty per tier
    SlaTier.GOLD:   10.0,
    SlaTier.SILVER:  3.0,
    SlaTier.BRONZE:  0.5,
}

# Typical carbon profiles per zone (gCO2/kWh base)
ZONE_BASE_CARBON = {
    "DK-DK1": 250.0,   # Denmark — wind-heavy, variable
    "SE":      50.0,    # Sweden  — high renewables
    "DE":      350.0,   # Germany — mixed fossil/renewable
    "US-AK":   200.0,   # Alaska  — mixed
}

_classifier  = SlaTierClassifier()
_cost_engine = MigrationCostEstimator(network_capacity_mbps=1000.0)


def _simulate_carbon(step: int) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Synthetic sinusoidal carbon intensity with noise — mimics diurnal patterns."""
    t = step / 288.0  # normalise to 0-1 over a 24h day
    carbon_now: Dict[str, float] = {}
    carbon_fc:  Dict[str, float] = {}
    for i, zone in enumerate(ZONES):
        base  = ZONE_BASE_CARBON[zone]
        phase = 2 * math.pi * t + i
        now   = max(20.0, base + math.sin(phase) * (base * 0.4) + random.gauss(0, 15))
        # 4-hour mean forecast
        fc_vals = [
            max(20.0, base + math.sin(2 * math.pi * (t + h / 24) + i) * (base * 0.4))
            for h in range(1, 5)
        ]
        carbon_now[zone] = now
        carbon_fc[zone]  = float(np.mean(fc_vals))
    return carbon_now, carbon_fc


class CALMSLAEnv(gym.Env):
    """
    Single-VM migration environment.
    One episode = 288 steps (24 hours at 5-min intervals).
    """
    metadata = {"render_modes": []}

    def __init__(self, vm_config: Optional[Dict[str, Any]] = None):
        super().__init__()

        # Default VM — Silver tier, moderate workload
        self.vm_config = vm_config or {
            "id": "drl-vm",
            "size_gb": 8.0,
            "steady_power_kw": 1.0,
            "forecast_horizon_hours": 4.0,
            "sla_contract": {"latency_ms": 40, "critical": False},
            "runtime_metrics": {"cpu_utilization": 0.45, "dirty_rate": 8.0, "headroom": 60.0},
        }

        # Observation: 10-dim float32 vector, all in [0, 1]
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(N_ZONES * 3 + 4,), dtype=np.float32
        )
        # Actions: 0=Stay, 1..N=migrate to zone[i-1]
        self.action_space = spaces.Discrete(N_ZONES + 1)

        # Episode state
        self.step_count   = 0
        self.max_steps    = 288
        self.current_zone = ZONES[0]
        self.carbon_now:  Dict[str, float] = {}
        self.carbon_fc:   Dict[str, float] = {}
        self._update_vm_metrics()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _update_vm_metrics(self) -> None:
        """Drift cpu_utilization and dirty_rate slightly each step."""
        rm = self.vm_config["runtime_metrics"]
        rm["cpu_utilization"]  = float(np.clip(rm["cpu_utilization"]  + random.gauss(0, 0.03), 0.05, 0.98))
        rm["dirty_rate"]       = float(np.clip(rm["dirty_rate"]       + random.gauss(0, 1.0),  0.5, 150.0))
        rm["headroom"]         = float(np.clip(rm["headroom"]         + random.gauss(0, 2.0),  5.0, 95.0))

    def _get_tier(self) -> SlaTier:
        return _classifier.classify(
            self.vm_config["sla_contract"],
            self.vm_config["runtime_metrics"],
        )

    def _get_obs(self) -> np.ndarray:
        tier = self._get_tier()
        rm   = self.vm_config["runtime_metrics"]

        # Downtime limit by tier (seconds)
        dt_limit = {SlaTier.GOLD: 60.0, SlaTier.SILVER: 180.0, SlaTier.BRONZE: 900.0}[tier]

        obs = []
        for zone in ZONES:
            obs.append(min(self.carbon_now.get(zone, 300.0) / 800.0, 1.0))
        for zone in ZONES:
            obs.append(min(self.carbon_fc.get(zone, 300.0) / 800.0, 1.0))
        obs.append(float(rm["cpu_utilization"]))
        obs.append(min(rm["dirty_rate"] / 200.0, 1.0))
        obs.append({SlaTier.GOLD: 1.0, SlaTier.SILVER: 0.5, SlaTier.BRONZE: 0.0}[tier])
        obs.append(min(dt_limit / 900.0, 1.0))
        # Current zone one-hot (agent needs to know where it already is)
        for zone in ZONES:
            obs.append(1.0 if zone == self.current_zone else 0.0)
        return np.array(obs, dtype=np.float32)

    # ------------------------------------------------------------------ #
    # Gym interface
    # ------------------------------------------------------------------ #

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.step_count   = 0
        # Randomise starting zone so agent sees all zones equally during training
        self.current_zone = random.choice(ZONES)
        # Randomise starting step so agent sees diverse carbon patterns
        start_step = random.randint(0, 287)
        self.step_count = start_step
        # Randomise VM metrics for diverse training scenarios
        self.vm_config["runtime_metrics"] = {
            "cpu_utilization": random.uniform(0.2, 0.9),
            "dirty_rate":      random.uniform(1.0, 50.0),
            "headroom":        random.uniform(10.0, 90.0),
        }
        self.carbon_now, self.carbon_fc = _simulate_carbon(start_step)
        return self._get_obs(), {}

    def step(self, action: int):
        self.step_count += 1
        self.carbon_now, self.carbon_fc = _simulate_carbon(self.step_count)
        self._update_vm_metrics()

        tier    = self._get_tier()
        reward  = 0.0
        info: Dict[str, Any] = {"action": "stay", "sla_violated": False}

        # Action 0 = stay; or agent chose the same zone
        if action == 0 or ZONES[action - 1] == self.current_zone:
            reward = 0.0   # no benefit, no cost
        else:
            target_zone   = ZONES[action - 1]
            source_carbon = self.carbon_now[self.current_zone]
            target_carbon = self.carbon_now[target_zone]
            rm            = self.vm_config["runtime_metrics"]

            cost_metrics = _cost_engine.estimate(
                vm_size_gb        = float(self.vm_config["size_gb"]),
                dirty_rate_mb_s   = rm["dirty_rate"],
                intensity_gco2    = source_carbon,
            )

            downtime_s    = cost_metrics["downtime_seconds"]
            carbon_cost   = cost_metrics["carbon_cost_gco2"]

            # Carbon savings over forecast horizon
            source_avg    = self.carbon_fc.get(self.current_zone, source_carbon)
            target_avg    = self.carbon_fc.get(target_zone,       target_carbon)
            power_kw      = float(self.vm_config.get("steady_power_kw", 1.0))
            horizon_h     = float(self.vm_config.get("forecast_horizon_hours", 4.0))
            gross_savings = max(0.0, source_avg - target_avg) * power_kw * horizon_h
            net_savings   = gross_savings - carbon_cost

            # SLA check
            dt_limit = {SlaTier.GOLD: 60.0, SlaTier.SILVER: 180.0, SlaTier.BRONZE: 900.0}[tier]
            sla_ok   = downtime_s <= dt_limit

            if sla_ok and net_savings > 0:
                self.current_zone = target_zone
                info["action"]    = f"migrate→{target_zone}"
                # Normalise to keep rewards in a reasonable range
                reward = (ALPHA * (net_savings / 100.0)
                          - BETA  * (carbon_cost / 100.0))
            else:
                violation  = not sla_ok
                info["sla_violated"] = violation
                info["action"]       = f"rejected→{target_zone}"
                reward = -(GAMMA[tier] if violation else BETA * (carbon_cost / 100.0))

        terminated = self.step_count >= self.max_steps
        return self._get_obs(), reward, terminated, False, info

    def render(self):
        tier = self._get_tier()
        print(
            f"Step {self.step_count:3d} | zone={self.current_zone:8s} | tier={tier.value} "
            f"| carbon={self.carbon_now.get(self.current_zone, 0):.0f} gCO2/kWh"
        )
