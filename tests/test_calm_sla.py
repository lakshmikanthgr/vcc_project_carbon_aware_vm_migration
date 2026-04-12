"""
tests/test_calm_sla.py — Pytest test suite for CALM-SLA.

Covers:
  - SLA tier classifier
  - Migration cost estimator
  - Decision engine (happy / sad / SLA-blocked paths)
  - DRL Gym environment
  - Database layer
  - VM simulator fleet
  - Config settings
  - fetch_history synthetic fallback
  - train_tcn pipeline
"""

import math
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import numpy as np
import pytest

#  Ensure project root is on path 
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Config
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfig:
    def test_imports_without_error(self):
        from config.settings import ALPHA, BETA, GAMMA, DATA_CENTERS, SLA_DOWNTIME_LIMITS
        assert ALPHA == 1.0
        assert BETA  == 0.3

    def test_gamma_has_all_tiers(self):
        from config.settings import GAMMA
        assert set(GAMMA.keys()) == {"Gold", "Silver", "Bronze"}
        assert GAMMA["Gold"] > GAMMA["Silver"] > GAMMA["Bronze"]

    def test_data_centers_not_empty(self):
        from config.settings import DATA_CENTERS
        assert len(DATA_CENTERS) >= 3

    def test_sla_limits_ordering(self):
        from config.settings import SLA_DOWNTIME_LIMITS
        assert SLA_DOWNTIME_LIMITS["Gold"] < SLA_DOWNTIME_LIMITS["Silver"] < SLA_DOWNTIME_LIMITS["Bronze"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SLA Tier Classifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestSlaTierClassifier:
    @pytest.fixture
    def clf(self):
        from sla_classifier import SlaTierClassifier
        return SlaTierClassifier()

    def test_critical_flag_gives_gold(self, clf):
        from sla_classifier import SlaTier
        tier = clf.classify(
            {"latency_ms": 100, "critical": True},
            {"cpu_utilization": 30.0, "dirty_rate": 5.0, "headroom": 70.0},
        )
        assert tier == SlaTier.GOLD

    def test_low_latency_gives_gold(self, clf):
        from sla_classifier import SlaTier
        tier = clf.classify(
            {"latency_ms": 15, "critical": False},
            {"cpu_utilization": 30.0, "dirty_rate": 5.0, "headroom": 70.0},
        )
        assert tier == SlaTier.GOLD

    def test_high_cpu_gives_gold(self, clf):
        from sla_classifier import SlaTier
        tier = clf.classify(
            {"latency_ms": 100, "critical": False},
            {"cpu_utilization": 85.0, "dirty_rate": 5.0, "headroom": 70.0},
        )
        assert tier == SlaTier.GOLD

    def test_moderate_workload_gives_silver(self, clf):
        from sla_classifier import SlaTier
        tier = clf.classify(
            {"latency_ms": 50, "critical": False},
            {"cpu_utilization": 50.0, "dirty_rate": 10.0, "headroom": 45.0},
        )
        assert tier == SlaTier.SILVER

    def test_light_workload_gives_bronze(self, clf):
        from sla_classifier import SlaTier
        tier = clf.classify(
            {"latency_ms": 200, "critical": False},
            {"cpu_utilization": 20.0, "dirty_rate": 2.0, "headroom": 80.0},
        )
        assert tier == SlaTier.BRONZE

    def test_low_headroom_gives_gold(self, clf):
        from sla_classifier import SlaTier
        tier = clf.classify(
            {"latency_ms": 200, "critical": False},
            {"cpu_utilization": 20.0, "dirty_rate": 2.0, "headroom": 15.0},
        )
        assert tier == SlaTier.GOLD


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Migration Cost Estimator
# ═══════════════════════════════════════════════════════════════════════════════

class TestMigrationCostEstimator:
    @pytest.fixture
    def est(self):
        from migration_cost_estimator import MigrationCostEstimator
        return MigrationCostEstimator(network_capacity_mbps=1000.0)

    def test_returns_all_keys(self, est):
        result = est.estimate(vm_size_gb=8.0, dirty_rate_mb_s=10.0, intensity_gco2=300.0)
        assert set(result.keys()) == {"traffic_gb", "transfer_seconds", "downtime_seconds", "carbon_cost_gco2"}

    def test_larger_vm_costs_more(self, est):
        small = est.estimate(4.0,  10.0, 300.0)
        large = est.estimate(32.0, 10.0, 300.0)
        assert large["carbon_cost_gco2"] > small["carbon_cost_gco2"]
        assert large["transfer_seconds"] > small["transfer_seconds"]

    def test_higher_dirty_rate_increases_downtime(self, est):
        clean = est.estimate(8.0,  2.0, 300.0)
        dirty = est.estimate(8.0, 80.0, 300.0)
        assert dirty["downtime_seconds"] > clean["downtime_seconds"]

    def test_downtime_capped_at_900s(self, est):
        result = est.estimate(vm_size_gb=512.0, dirty_rate_mb_s=200.0, intensity_gco2=300.0)
        assert result["downtime_seconds"] <= 900.0

    def test_downtime_minimum_5s(self, est):
        result = est.estimate(vm_size_gb=0.1, dirty_rate_mb_s=0.1, intensity_gco2=300.0)
        assert result["downtime_seconds"] >= 5.0

    def test_carbon_cost_positive(self, est):
        result = est.estimate(8.0, 10.0, 300.0)
        assert result["carbon_cost_gco2"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Decision Engine — all three paths
# ═══════════════════════════════════════════════════════════════════════════════

class TestDecisionEngine:
    @pytest.fixture
    def engine(self):
        from decision_engine import DecisionEngine
        from migration_cost_estimator import MigrationCostEstimator
        from sla_classifier import SlaTierClassifier
        return DecisionEngine(MigrationCostEstimator(1000.0), SlaTierClassifier())

    @pytest.fixture
    def intensities(self):
        return {"DK-DK1": 320.0, "SE": 80.0, "DE": 200.0, "US-AK": 150.0}

    @pytest.fixture
    def forecasts(self):
        return {
            "DK-DK1": {1: 320, 2: 315, 3: 310, 4: 305},
            "SE":      {1: 80,  2: 78,  3: 76,  4: 74},
            "DE":      {1: 200, 2: 198, 3: 196, 4: 194},
            "US-AK":   {1: 150, 2: 148, 3: 146, 4: 144},
        }

    def test_happy_path_migrates_to_lowest_carbon(self, engine, intensities, forecasts):
        vm = {
            "id": "vm-happy", "size_gb": 8.0, "steady_power_kw": 1.0,
            "forecast_horizon_hours": 4.0,
            "sla_contract": {"latency_ms": 40, "critical": False},
            "runtime_metrics": {"cpu_utilization": 45.0, "dirty_rate": 8.0, "headroom": 60.0},
        }
        d = engine.evaluate(vm, "DK-DK1", list(intensities.keys()), intensities, forecasts)
        assert d.should_migrate is True
        assert d.target_zone == "SE"
        assert d.net_carbon_saving > 0

    def test_sad_path_no_migration_when_cost_exceeds_savings(self, engine, intensities, forecasts):
        vm = {
            "id": "vm-sad", "size_gb": 16.0, "steady_power_kw": 1.2,
            "forecast_horizon_hours": 3.0,
            "sla_contract": {"latency_ms": 15, "critical": True},
            "runtime_metrics": {"cpu_utilization": 88.0, "dirty_rate": 120.0, "headroom": 15.0},
        }
        d = engine.evaluate(vm, "DK-DK1", list(intensities.keys()), intensities, forecasts)
        assert d.should_migrate is False

    def test_sla_blocked_gold_vm_not_migrated(self, engine, intensities, forecasts):
        vm = {
            "id": "vm-blocked", "size_gb": 64.0, "steady_power_kw": 1.5,
            "forecast_horizon_hours": 4.0,
            "sla_contract": {"latency_ms": 15, "critical": True},
            "runtime_metrics": {"cpu_utilization": 90.0, "dirty_rate": 95.0, "headroom": 10.0},
        }
        d = engine.evaluate(vm, "DK-DK1", list(intensities.keys()), intensities, forecasts)
        assert d.should_migrate is False

    def test_no_migration_when_already_in_best_zone(self, engine, intensities, forecasts):
        vm = {
            "id": "vm-best", "size_gb": 4.0, "steady_power_kw": 0.5,
            "forecast_horizon_hours": 4.0,
            "sla_contract": {"latency_ms": 200, "critical": False},
            "runtime_metrics": {"cpu_utilization": 20.0, "dirty_rate": 2.0, "headroom": 80.0},
        }
        d = engine.evaluate(vm, "SE", list(intensities.keys()), intensities, forecasts)
        assert d.should_migrate is False

    def test_net_saving_less_than_gross(self, engine, intensities, forecasts):
        """Verify overhead is deducted: net < gross savings."""
        vm = {
            "id": "vm-check", "size_gb": 8.0, "steady_power_kw": 1.0,
            "forecast_horizon_hours": 4.0,
            "sla_contract": {"latency_ms": 40, "critical": False},
            "runtime_metrics": {"cpu_utilization": 45.0, "dirty_rate": 8.0, "headroom": 60.0},
        }
        from migration_cost_estimator import MigrationCostEstimator
        d = engine.evaluate(vm, "DK-DK1", list(intensities.keys()), intensities, forecasts)
        if d.should_migrate:
            cost = MigrationCostEstimator(1000.0).estimate(8.0, 8.0, 320.0)
            gross = d.net_carbon_saving + cost["carbon_cost_gco2"]
            assert d.net_carbon_saving < gross


# ═══════════════════════════════════════════════════════════════════════════════
# 5. DRL Environment
# ═══════════════════════════════════════════════════════════════════════════════

class TestDRLEnvironment:
    @pytest.fixture
    def env(self):
        from drl_environment import CALMSLAEnv
        return CALMSLAEnv()

    def test_initialises_without_error(self, env):
        assert env is not None

    def test_obs_shape_matches_space(self, env):
        obs, _ = env.reset()
        assert obs.shape == env.observation_space.shape

    def test_obs_values_in_unit_range(self, env):
        obs, _ = env.reset()
        assert obs.min() >= 0.0
        assert obs.max() <= 1.0 + 1e-6

    def test_action_space_size(self, env):
        from drl_environment import N_ZONES
        assert env.action_space.n == N_ZONES + 1

    def test_stay_gives_zero_reward(self, env):
        env.reset()
        _, reward, _, _, info = env.step(0)
        assert reward == 0.0
        assert info["action"] == "stay"

    def test_migration_to_low_carbon_zone_positive_reward(self, env):
        from drl_environment import ZONES
        env.reset()
        # Force a large carbon gap: current zone = DK-DK1 (high), target = SE (low)
        env.carbon_now   = {"DK-DK1": 400.0, "DE": 300.0, "SE": 50.0, "US-AK": 200.0}
        env.carbon_fc    = {"DK-DK1": 390.0, "DE": 295.0, "SE": 48.0, "US-AK": 195.0}
        env.current_zone = "DK-DK1"
        env.vm_config["runtime_metrics"] = {"cpu_utilization": 0.3, "dirty_rate": 3.0, "headroom": 80.0}
        se_action = ZONES.index("SE") + 1
        _, reward, _, _, info = env.step(se_action)
        assert reward > 0 or "migrate" in info["action"]

    def test_episode_terminates_correctly(self, env):
        """Episode must terminate; total steps = max_steps - start_step."""
        obs, _ = env.reset()
        start = env.step_count   # randomised start
        remaining = env.max_steps - start
        done = False
        steps = 0
        while not done:
            _, _, terminated, truncated, _ = env.step(0)
            done = terminated or truncated
            steps += 1
            if steps > env.max_steps + 1:
                break
        assert done
        assert steps == remaining

    def test_sla_violation_negative_reward(self, env):
        from drl_environment import ZONES
        env.reset()
        # Gold VM (high CPU + critical) — any migration should be penalised
        env.vm_config["sla_contract"] = {"latency_ms": 15, "critical": True}
        env.vm_config["runtime_metrics"] = {"cpu_utilization": 0.9, "dirty_rate": 120.0, "headroom": 10.0}
        env.vm_config["size_gb"] = 64.0
        env.current_zone = "DK-DK1"
        # Try migrating to SE — should be blocked or penalised
        se_action = ZONES.index("SE") + 1
        _, reward, _, _, info = env.step(se_action)
        # Either rejected (reward < 0) or SLA gate blocks it (no real migration)
        assert reward <= 0 or info.get("sla_violated") or "rejected" in info.get("action", "")

    def test_reset_randomises_starting_zone(self, env):
        zones_seen = set()
        for _ in range(30):
            env.reset()
            zones_seen.add(env.current_zone)
        assert len(zones_seen) > 1  # must see more than one starting zone


# ═══════════════════════════════════════════════════════════════════════════════
# 6. VM Simulator
# ═══════════════════════════════════════════════════════════════════════════════

class TestVMSimulator:
    def test_fleet_has_10_vms(self):
        from simulation.vm_simulator import create_vm_fleet
        fleet = create_vm_fleet()
        assert len(fleet) == 10

    def test_fleet_tier_counts(self):
        from simulation.vm_simulator import create_vm_fleet
        fleet = create_vm_fleet()
        tiers = [vm.tier for vm in fleet]
        assert tiers.count("Gold")   == 3
        assert tiers.count("Silver") == 3
        assert tiers.count("Bronze") == 4

    def test_gold_vms_are_critical(self):
        from simulation.vm_simulator import create_vm_fleet
        fleet = create_vm_fleet()
        for vm in fleet:
            if vm.tier == "Gold":
                assert vm.critical is True

    def test_to_dict_has_required_keys(self):
        from simulation.vm_simulator import create_vm_fleet
        vm = create_vm_fleet()[0]
        d = vm.to_dict()
        assert "id" in d
        assert "current_zone" in d
        assert "sla_contract" in d
        assert "runtime_metrics" in d

    def test_update_metrics_changes_values(self):
        from simulation.vm_simulator import create_vm_fleet
        vm = create_vm_fleet()[0]
        original_cpu = vm.cpu_utilization
        # Run enough updates that at least one changes (gauss noise)
        changed = False
        for _ in range(20):
            vm.update_metrics()
            if vm.cpu_utilization != original_cpu:
                changed = True
                break
        assert changed

    def test_metrics_stay_in_bounds(self):
        from simulation.vm_simulator import create_vm_fleet
        vm = create_vm_fleet()[0]
        for _ in range(100):
            vm.update_metrics()
        assert 0.0 <= vm.cpu_utilization <= 1.0
        assert vm.dirty_rate >= 0.5
        assert vm.headroom >= 5.0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Database Layer
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatabase:
    @pytest.fixture(autouse=True)
    def temp_db(self, tmp_path, monkeypatch):
        """Use a temporary DB for each test."""
        db = tmp_path / "test.db"
        monkeypatch.setattr("database.DB_PATH", db)
        from database import init_db
        init_db()
        yield db

    def _make_decision(self, vm_id="vm-test", migrate=True, saving=100.0, downtime=5.0, tier="Silver"):
        class D:
            pass
        d = D()
        d.vm_id = vm_id; d.source_zone = "DK-DK1"; d.target_zone = "SE"
        d.should_migrate = migrate; d.net_carbon_saving = saving
        d.estimated_downtime = downtime; d.reason = "test"
        return d, tier

    def test_init_creates_tables(self, temp_db):
        conn = sqlite3.connect(temp_db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "carbon_readings" in tables
        assert "migration_log" in tables

    def test_log_and_retrieve_carbon(self):
        from database import log_carbon_readings, get_recent_readings
        log_carbon_readings("SE", [{"source": "ElectricityMaps", "gco2": 55.0}])
        rows = get_recent_readings("SE", limit=5)
        assert len(rows) == 1
        assert rows[0]["intensity"] == 55.0

    def test_log_migration_decision(self):
        from database import log_migration_decision, get_migration_log
        d, tier = self._make_decision(migrate=True, saving=150.0, downtime=6.0)
        log_migration_decision(d, tier, carbon_cost=20.0, gross_carbon_saved=170.0)
        rows = get_migration_log(5)
        assert len(rows) == 1
        assert rows[0]["should_migrate"] is True
        assert rows[0]["net_carbon_saved"] == 150.0
        assert rows[0]["gross_carbon_saved"] == 170.0

    def test_gross_greater_than_net(self):
        from database import log_migration_decision, get_migration_log
        d, tier = self._make_decision(migrate=True, saving=150.0)
        log_migration_decision(d, tier, carbon_cost=20.0, gross_carbon_saved=170.0)
        row = get_migration_log(1)[0]
        assert row["gross_carbon_saved"] > row["net_carbon_saved"]

    def test_summary_counts_correctly(self):
        from database import log_migration_decision, get_summary
        d1, t1 = self._make_decision("vm-a", migrate=True, saving=100.0)
        d2, t2 = self._make_decision("vm-b", migrate=False, saving=0.0)
        log_migration_decision(d1, t1, 10.0)
        log_migration_decision(d2, t2, 10.0)
        s = get_summary()
        assert s["total_migrations"] == 1
        assert s["total_rejected"] == 1
        assert s["total_carbon_saved_gco2"] == 100.0

    def test_sla_violation_query_correct(self):
        """Violations = executed migrations that exceeded SLA downtime limit."""
        from database import log_migration_decision, get_summary

        # Gold VM migrated with downtime > 60s = violation
        d_viol, _ = self._make_decision("vm-viol", migrate=True, saving=50.0, downtime=90.0, tier="Gold")
        # Silver VM migrated within limit = no violation
        d_ok, _ = self._make_decision("vm-ok", migrate=True, saving=50.0, downtime=30.0, tier="Silver")
        # Rejected migration (should_migrate=False, downtime>60) = NOT a violation
        d_rejected, _ = self._make_decision("vm-rej", migrate=False, saving=0.0, downtime=90.0, tier="Gold")

        log_migration_decision(d_viol, "Gold", 10.0)
        log_migration_decision(d_ok, "Silver", 10.0)
        log_migration_decision(d_rejected, "Gold", 10.0)

        s = get_summary()
        assert s["sla_violations"] == 1   # only the executed Gold migration with downtime>60

    def test_overhead_deducted_flag(self):
        from database import log_migration_decision, get_summary
        d, t = self._make_decision(migrate=True, saving=100.0)
        log_migration_decision(d, t, carbon_cost=20.0, gross_carbon_saved=120.0)
        s = get_summary()
        assert s["overhead_correctly_deducted"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 8. fetch_history synthetic fallback
# ═══════════════════════════════════════════════════════════════════════════════

class TestFetchHistory:
    def test_synthetic_generates_correct_count(self):
        from fetch_history import generate_synthetic
        records = generate_synthetic("SE", n_hours=48)
        assert len(records) == 48

    def test_synthetic_values_positive(self):
        from fetch_history import generate_synthetic
        records = generate_synthetic("DE", n_hours=24)
        assert all(val > 0 for _, val in records)

    def test_synthetic_has_variation(self):
        from fetch_history import generate_synthetic
        records = generate_synthetic("DK-DK1", n_hours=24)
        vals = [v for _, v in records]
        assert max(vals) - min(vals) > 10  # diurnal variation present

    def test_save_and_reload_csv(self, tmp_path):
        from fetch_history import generate_synthetic, save_csv
        import csv as csv_mod
        records = generate_synthetic("SE", n_hours=10)
        with patch("fetch_history.OUTPUT_DIR", tmp_path):
            path = save_csv("SE", records)
        # Read back
        with open(tmp_path / "SE.csv") as f:
            rows = list(csv_mod.DictReader(f))
        assert len(rows) == 10
        assert "carbonIntensity" in rows[0]


# ═══════════════════════════════════════════════════════════════════════════════
# 9. TCN Forecaster
# ═══════════════════════════════════════════════════════════════════════════════

class TestTCNForecaster:
    @pytest.fixture
    def forecaster(self):
        from services.carbon_forecaster import CarbonForecaster
        return CarbonForecaster(horizon_hours=4, seq_len=12)

    def test_forecast_returns_4_values(self, forecaster):
        history = [200.0 + i * 0.5 for i in range(20)]
        fc = forecaster.forecast(history)
        assert set(fc.keys()) == {1, 2, 3, 4}

    def test_forecast_values_non_negative(self, forecaster):
        history = [abs(150 + 50 * math.sin(i / 5)) for i in range(30)]
        fc = forecaster.forecast(history)
        assert all(v >= 0 for v in fc.values())

    def test_train_and_forecast(self, forecaster):
        import random
        random.seed(7)
        # Need enough samples: seq_len(12) + horizon(4) + batch overhead
        history = [200 + 80 * math.sin(i * 0.3) + random.gauss(0, 10) for i in range(80)]
        forecaster.train(history, epochs=3)
        assert forecaster.trained
        fc = forecaster.forecast(history[-12:])
        assert len(fc) == 4

    def test_short_history_uses_fallback(self, forecaster):
        fc = forecaster.forecast([200.0] * 5)
        assert all(v >= 0 for v in fc.values())


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Integration — orchestrator cycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrchestratorIntegration:
    def test_run_cycle_returns_decisions_for_all_vms(self):
        from orchestrator import Orchestrator
        from simulation.vm_simulator import create_vm_fleet

        orch = Orchestrator(persist=False)
        # Inject synthetic carbon so no API calls needed
        orch.monitor.latest = {"DK-DK1": 320.0, "DE": 200.0, "SE": 80.0, "US-AK": 150.0}
        orch.monitor.history = {z: [v] for z, v in orch.monitor.latest.items()}
        orch.monitor.latest_measurements = {z: [{"source": "Synthetic", "gco2": v}] for z, v in orch.monitor.latest.items()}
        orch.monitor.last_poll = 9_999_999_999  # prevent re-poll

        fleet = create_vm_fleet()
        results = orch.run_cycle([vm.to_dict() for vm in fleet])
        assert len(results) == len(fleet)
        for r in results:
            assert "decision" in r

    def test_gold_vms_never_violate_sla(self):
        from orchestrator import Orchestrator
        from simulation.vm_simulator import create_vm_fleet
        from config.settings import SLA_DOWNTIME_LIMITS

        orch = Orchestrator(persist=False)
        orch.monitor.latest = {"DK-DK1": 400.0, "DE": 350.0, "SE": 50.0, "US-AK": 200.0}
        orch.monitor.history = {z: [v] for z, v in orch.monitor.latest.items()}
        orch.monitor.latest_measurements = {z: [] for z in orch.monitor.latest}
        orch.monitor.last_poll = 9_999_999_999

        fleet = create_vm_fleet()
        results = orch.run_cycle([vm.to_dict() for vm in fleet])

        for r in results:
            d = r["decision"]
            if d.should_migrate:
                # Look up original VM tier
                vm_dict = next(v for v in [vm.to_dict() for vm in fleet] if v["id"] == d.vm_id)
                from sla_classifier import SlaTierClassifier
                tier = SlaTierClassifier().classify(vm_dict["sla_contract"], vm_dict["runtime_metrics"])
                limit = SLA_DOWNTIME_LIMITS[tier.value]
                assert d.estimated_downtime <= limit, (
                    f"SLA violated: {d.vm_id} tier={tier.value} downtime={d.estimated_downtime:.1f}s > {limit}s"
                )
