import os

from dotenv import load_dotenv

from orchestrator import Orchestrator
from report_generator import MigrationDecisionReportGenerator, save_report_to_file
from simulation import simulate_happy_sad_and_sla_blocked_paths, simulate_real_case
from decision_engine import DecisionEngine
from migration_cost_estimator import MigrationCostEstimator
from sla_classifier import SlaTierClassifier
from typing import Any, Dict, List


def capture_simulation_results() -> Dict[str, Any]:
    """Capture simulation scenario results for the report."""
    engine = DecisionEngine(MigrationCostEstimator(network_capacity_mbps=1000.0), SlaTierClassifier())
    sla_classifier = SlaTierClassifier()
    
    scenarios = []
    
    # Happy Path
    happy_vm = {
        "id": "vm-happy",
        "current_zone": "DK-DK1",
        "size_gb": 8.0,
        "steady_power_kw": 1.0,
        "forecast_horizon_hours": 4.0,
        "sla_contract": {"latency_ms": 40, "critical": False},
        "runtime_metrics": {"cpu_utilization": 45.0, "dirty_rate": 8.0, "headroom": 60.0},
    }
    happy_current_intensities = {"DK-DK1": 320.0, "SE": 80.0, "DE": 200.0, "US-AK": 150.0}
    happy_forecasts = {
        "DK-DK1": {1: 320.0, 2: 315.0, 3: 310.0, 4: 305.0},
        "SE": {1: 80.0, 2: 78.0, 3: 76.0, 4: 74.0},
        "DE": {1: 200.0, 2: 198.0, 3: 196.0, 4: 194.0},
        "US-AK": {1: 150.0, 2: 148.0, 3: 146.0, 4: 144.0},
    }
    happy_decision = engine.evaluate(
        vm=happy_vm,
        source_zone=happy_vm["current_zone"],
        candidate_zones=list(happy_current_intensities.keys()),
        current_intensities=happy_current_intensities,
        forecasted_intensities=happy_forecasts,
    )
    scenarios.append({
        'name': 'Happy Path Scenario',
        'vm': happy_vm,
        'current_intensities': happy_current_intensities,
        'forecasted_intensities': happy_forecasts,
        'decision': {
            'vm_id': happy_decision.vm_id,
            'source_zone': happy_decision.source_zone,
            'target_zone': happy_decision.target_zone,
            'should_migrate': happy_decision.should_migrate,
            'net_carbon_saving': happy_decision.net_carbon_saving,
            'estimated_downtime': happy_decision.estimated_downtime,
            'reason': happy_decision.reason
        },
        'sla_tier': sla_classifier.classify(happy_vm["sla_contract"], happy_vm["runtime_metrics"]).value.upper()
    })
    
    # Sad Path
    sad_vm = {
        "id": "vm-sad",
        "current_zone": "DK-DK1",
        "size_gb": 16.0,
        "steady_power_kw": 1.2,
        "forecast_horizon_hours": 3.0,
        "sla_contract": {"latency_ms": 15, "critical": True},
        "runtime_metrics": {"cpu_utilization": 88.0, "dirty_rate": 120.0, "headroom": 15.0},
    }
    sad_current_intensities = {"DK-DK1": 280.0, "SE": 90.0, "DE": 210.0, "US-AK": 160.0}
    sad_forecasts = {
        "DK-DK1": {1: 280.0, 2: 282.0, 3: 285.0, 4: 288.0},
        "SE": {1: 90.0, 2: 92.0, 3: 94.0, 4: 96.0},
        "DE": {1: 210.0, 2: 212.0, 3: 215.0, 4: 218.0},
        "US-AK": {1: 160.0, 2: 162.0, 3: 165.0, 4: 168.0},
    }
    sad_decision = engine.evaluate(
        vm=sad_vm,
        source_zone=sad_vm["current_zone"],
        candidate_zones=list(sad_current_intensities.keys()),
        current_intensities=sad_current_intensities,
        forecasted_intensities=sad_forecasts,
    )
    scenarios.append({
        'name': 'Sad Path Scenario',
        'vm': sad_vm,
        'current_intensities': sad_current_intensities,
        'forecasted_intensities': sad_forecasts,
        'decision': {
            'vm_id': sad_decision.vm_id,
            'source_zone': sad_decision.source_zone,
            'target_zone': sad_decision.target_zone,
            'should_migrate': sad_decision.should_migrate,
            'net_carbon_saving': sad_decision.net_carbon_saving,
            'estimated_downtime': sad_decision.estimated_downtime,
            'reason': sad_decision.reason
        },
        'sla_tier': sla_classifier.classify(sad_vm["sla_contract"], sad_vm["runtime_metrics"]).value.upper()
    })
    
    # SLA Blocked
    sla_blocked_vm = {
        "id": "vm-sla-blocked",
        "current_zone": "DK-DK1",
        "size_gb": 64.0,
        "steady_power_kw": 1.5,
        "forecast_horizon_hours": 4.0,
        "sla_contract": {"latency_ms": 15, "critical": True},
        "runtime_metrics": {"cpu_utilization": 90.0, "dirty_rate": 95.0, "headroom": 10.0},
    }
    sla_blocked_intensities = {"DK-DK1": 320.0, "SE": 100.0, "DE": 180.0, "US-AK": 140.0}
    sla_blocked_forecasts = {
        "DK-DK1": {1: 320.0, 2: 318.0, 3: 315.0, 4: 312.0},
        "SE": {1: 100.0, 2: 98.0, 3: 96.0, 4: 94.0},
        "DE": {1: 180.0, 2: 178.0, 3: 176.0, 4: 174.0},
        "US-AK": {1: 140.0, 2: 138.0, 3: 136.0, 4: 134.0},
    }
    sla_blocked_decision = engine.evaluate(
        vm=sla_blocked_vm,
        source_zone=sla_blocked_vm["current_zone"],
        candidate_zones=list(sla_blocked_intensities.keys()),
        current_intensities=sla_blocked_intensities,
        forecasted_intensities=sla_blocked_forecasts,
    )
    scenarios.append({
        'name': 'SLA-Blocked Scenario',
        'vm': sla_blocked_vm,
        'current_intensities': sla_blocked_intensities,
        'forecasted_intensities': sla_blocked_forecasts,
        'decision': {
            'vm_id': sla_blocked_decision.vm_id,
            'source_zone': sla_blocked_decision.source_zone,
            'target_zone': sla_blocked_decision.target_zone,
            'should_migrate': sla_blocked_decision.should_migrate,
            'net_carbon_saving': sla_blocked_decision.net_carbon_saving,
            'estimated_downtime': sla_blocked_decision.estimated_downtime,
            'reason': sla_blocked_decision.reason
        },
        'sla_tier': sla_classifier.classify(sla_blocked_vm["sla_contract"], sla_blocked_vm["runtime_metrics"]).value.upper()
    })
    
    return {'scenarios': scenarios}


def generate_live_data_report(orchestrator: Orchestrator, sample_vms: List[Dict[str, Any]]) -> str:
    """Generate report for live data from the orchestrator."""
    print("\nGenerating live data HTML report...")
    report_generator = MigrationDecisionReportGenerator()
    
    # Run migration decision cycle
    print("Running migration decision cycle...")
    results = orchestrator.run_cycle(sample_vms)
    
    # Print console output
    print("\n--- Migration Decisions ---")
    for item in results:
        decision = item["decision"]
        print(f"VM {decision.vm_id}: {decision.reason}")
        if item["migration"]:
            print(f"  migration: {item['migration']}")
    
    # Gather live data for report
    current_intensities = orchestrator.monitor.latest
    forecasted_intensities = {}
    api_measurements = {}
    for zone in orchestrator.monitor.zones:
        history = orchestrator.monitor.get_history(zone)
        watttime_forecast = orchestrator.monitor.get_forecast(zone, horizon_hours=orchestrator.forecaster.horizon_hours)
        if len(history) >= orchestrator.forecaster.seq_len + orchestrator.forecaster.horizon_hours:
            orchestrator.forecaster.train(history, epochs=10)
        forecasted_intensities[zone] = orchestrator.forecaster.forecast(history, watttime_forecast)
        # Gather individual API measurements for each zone
        api_measurements[zone] = orchestrator.monitor.get_measurements(zone)
    
    html_report = report_generator.generate_html_report(
        vm_inventory=sample_vms,
        decisions=results,
        current_intensities=current_intensities,
        forecasted_intensities=forecasted_intensities,
        candidate_zones=orchestrator.monitor.zones,
        simulation_results=None,
        api_measurements=api_measurements,
    )
    
    report_file = save_report_to_file(html_report, "migration_report_live.html")
    print(f"✓ Live data report saved to {report_file}")
    return report_file


def generate_simulated_data_report() -> str:
    """Generate report for simulated test data."""
    print("\nGenerating simulated data HTML report...")
    report_generator = MigrationDecisionReportGenerator()
    
    # Capture simulation results
    simulation_results = capture_simulation_results()
    
    # Create mock VMs from simulation data
    mock_vms = [scenario['vm'] for scenario in simulation_results['scenarios']]
    
    # Create mock decisions from simulation data
    mock_decisions = []
    for scenario in simulation_results['scenarios']:
        decision_obj = scenario['decision']
        mock_decisions.append({
            'decision': type('Decision', (), {
                'vm_id': decision_obj['vm_id'],
                'source_zone': decision_obj['source_zone'],
                'target_zone': decision_obj['target_zone'],
                'should_migrate': decision_obj['should_migrate'],
                'net_carbon_saving': decision_obj['net_carbon_saving'],
                'estimated_downtime': decision_obj['estimated_downtime'],
                'reason': decision_obj['reason']
            })()
        })
    
    # Create mock intensity data from simulation
    candidate_zones = list(scenario['current_intensities'].keys() for scenario in simulation_results['scenarios'])[0]
    mock_current_intensities = simulation_results['scenarios'][0]['current_intensities']
    mock_forecasted_intensities = {}
    for zone in candidate_zones:
        mock_forecasted_intensities[zone] = {1: mock_current_intensities[zone]}
    
    html_report = report_generator.generate_html_report(
        vm_inventory=mock_vms,
        decisions=mock_decisions,
        current_intensities=mock_current_intensities,
        forecasted_intensities=mock_forecasted_intensities,
        candidate_zones=list(candidate_zones),
        simulation_results=simulation_results,
    )
    
    report_file = save_report_to_file(html_report, "migration_report_simulated.html")
    print(f"✓ Simulated data report saved to {report_file}")
    return report_file


def main() -> None:
    # Load environment variables from .env file
    load_dotenv()
    orchestrator = Orchestrator()
    sample_vms = [
        {
            "id": "vm-1",
            "current_zone": "DK-DK1",
            "size_gb": 32.0,
            "steady_power_kw": 1.25,
            "forecast_horizon_hours": 3.0,
            "sla_contract": {"latency_ms": 15, "critical": True},
            "runtime_metrics": {"cpu_utilization": 72.0, "dirty_rate": 20.0, "headroom": 25.0},
            # Optional GCP metadata for real migration execution
            "gcp_project_id": os.getenv("GCP_PROJECT_ID", "your-gcp-project-id"),
            "gcp_instance_name": os.getenv("GCP_INSTANCE_NAME", "your-instance-name"),
            "gcp_source_zone": os.getenv("GCP_SOURCE_ZONE", "europe-north1-b"),
            "gcp_target_zone": os.getenv("GCP_TARGET_ZONE", "europe-north1-c"),
            "gcp_target_instance_name": os.getenv("GCP_TARGET_INSTANCE_NAME", "your-instance-name-migrated"),
        },
        {
            "id": "vm-2",
            "current_zone": "DE",
            "size_gb": 16.0,
            "steady_power_kw": 0.9,
            "forecast_horizon_hours": 4.0,
            "sla_contract": {"latency_ms": 40, "critical": False},
            "runtime_metrics": {"cpu_utilization": 52.0, "dirty_rate": 10.0, "headroom": 50.0},
        },
        {
            "id": "vm-3",
            "current_zone": "SE",
            "size_gb": 8.0,
            "steady_power_kw": 0.7,
            "forecast_horizon_hours": 2.0,
            "sla_contract": {"latency_ms": 100, "critical": False},
            "runtime_metrics": {"cpu_utilization": 35.0, "dirty_rate": 5.0, "headroom": 75.0},
        },
    ]

    # Generate live data report
    generate_live_data_report(orchestrator, sample_vms)
    
    # Generate simulated data report
    generate_simulated_data_report()


if __name__ == "__main__":
    main()
    print("\n--- Simulation Scenarios ---")
    simulate_happy_sad_and_sla_blocked_paths()
    simulate_real_case()
