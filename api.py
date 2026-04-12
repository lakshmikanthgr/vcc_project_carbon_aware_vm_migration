"""
api.py — FastAPI REST API for CALM-SLA.

Endpoints:
  GET /status               framework health + last poll time
  GET /carbon/current       latest intensity per zone
  GET /carbon/history/{zone} historical readings from DB
  GET /vms                  current VM fleet snapshot
  GET /decisions            recent migration log from DB
  GET /metrics/summary      total carbon saved, migration counts
  GET /metrics/baseline     CALM-SLA vs greedy vs no-migration comparison
  POST /cycle               trigger one orchestration cycle manually

Run:
  uvicorn api:app --host 0.0.0.0 --port 8199 --reload
"""
import time
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database import (
    init_db, get_migration_log, get_recent_readings,
    get_summary, get_baseline_comparison,
)
from orchestrator import Orchestrator
from sla_classifier import SlaTierClassifier
from simulation.vm_simulator import vm_fleet

app = FastAPI(
    title="CALM-SLA API",
    description="Carbon-Aware Live VM Migration with SLA Guarantees",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise DB and shared state at startup
init_db()
_orchestrator = Orchestrator()
_sla_classifier = SlaTierClassifier()
_start_time = time.time()

# Canonical 10-VM fleet shared with the orchestrator loop
# (SimulatedVM objects — converted to dicts when passed to decision engine)
_vm_fleet = vm_fleet


@app.get("/status")
def status() -> Dict[str, Any]:
    uptime = round(time.time() - _start_time, 1)
    zones = _orchestrator.monitor.zones
    latest = _orchestrator.monitor.latest
    last_poll = _orchestrator.monitor.last_poll
    return {
        "status": "running",
        "uptime_seconds": uptime,
        "zones_monitored": zones,
        "last_poll_ago_seconds": round(time.time() - last_poll, 1) if last_poll else None,
        "current_intensities": latest,
    }


@app.get("/carbon/current")
def carbon_current() -> Dict[str, Any]:
    intensities = _orchestrator.monitor.latest
    if not any(v > 0 for v in intensities.values()):
        intensities = _orchestrator.monitor.poll_once()
    return {
        "zones": {
            zone: {
                "intensity_gco2_kwh": intensity,
                "measurements": _orchestrator.monitor.get_measurements(zone),
            }
            for zone, intensity in intensities.items()
        }
    }


@app.get("/carbon/history/{zone}")
def carbon_history(zone: str, limit: int = 48) -> Dict[str, Any]:
    if zone not in _orchestrator.monitor.zones:
        raise HTTPException(status_code=404, detail=f"Zone '{zone}' not monitored.")
    db_history = get_recent_readings(zone, limit)
    mem_history = _orchestrator.monitor.get_history(zone)
    return {
        "zone": zone,
        "db_readings": db_history,
        "in_memory_count": len(mem_history),
        "latest_intensity": _orchestrator.monitor.latest.get(zone, 0.0),
    }


@app.get("/vms")
def vms() -> Dict[str, Any]:
    fleet = []
    for vm in _vm_fleet:
        d = vm.to_dict()
        tier = _sla_classifier.classify(d["sla_contract"], d["runtime_metrics"])
        fleet.append({**d, "sla_tier": tier.value, "name": vm.name, "tier": vm.tier})
    return {"vm_count": len(fleet), "vms": fleet}


@app.get("/decisions")
def decisions(limit: int = 20) -> Dict[str, Any]:
    log = get_migration_log(limit)
    return {"count": len(log), "decisions": log}


@app.get("/metrics/summary")
def metrics_summary() -> Dict[str, Any]:
    return get_summary()


@app.get("/metrics/baseline")
def metrics_baseline() -> Dict[str, Any]:
    return get_baseline_comparison()


@app.post("/cycle")
def run_cycle() -> Dict[str, Any]:
    """Manually trigger one orchestration cycle and persist results."""
    from database import log_carbon_readings, log_migration_decision
    from migration_cost_estimator import MigrationCostEstimator

    for vm in _vm_fleet:
        vm.update_metrics()
    results = _orchestrator.run_cycle([vm.to_dict() for vm in _vm_fleet])

    # Persist carbon readings
    for zone in _orchestrator.monitor.zones:
        measurements = _orchestrator.monitor.get_measurements(zone)
        if measurements:
            log_carbon_readings(zone, measurements)

    # Persist decisions
    cost_estimator = MigrationCostEstimator(network_capacity_mbps=1000.0)
    decisions_out = []
    for item in results:
        decision = item["decision"]
        vm_obj = next((v for v in _vm_fleet if v.vm_id == decision.vm_id), None)
        vm = vm_obj.to_dict() if vm_obj else {}
        tier = _sla_classifier.classify(
            vm.get("sla_contract", {}), vm.get("runtime_metrics", {})
        )
        metrics = cost_estimator.estimate(
            vm_size_gb=float(vm.get("size_gb", 16.0)),
            dirty_rate_mb_s=float(vm.get("runtime_metrics", {}).get("dirty_rate", 10.0)),
            intensity_gco2=_orchestrator.monitor.latest.get(decision.source_zone, 220.0),
        )
        log_migration_decision(decision, tier.value, metrics["carbon_cost_gco2"])
        decisions_out.append({
            "vm_id": decision.vm_id,
            "should_migrate": decision.should_migrate,
            "target_zone": decision.target_zone,
            "net_carbon_saving": decision.net_carbon_saving,
            "reason": decision.reason,
        })

    return {"cycle_complete": True, "decisions": decisions_out}
