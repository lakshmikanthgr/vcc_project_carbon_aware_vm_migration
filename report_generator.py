from typing import Any, Dict, List
from datetime import datetime
from sla_classifier import SlaTierClassifier


class MigrationDecisionReportGenerator:
    def __init__(self):
        self.sla_classifier = SlaTierClassifier()

    def generate_html_report(
        self,
        vm_inventory: List[Dict[str, Any]],
        decisions: List[Dict[str, Any]],
        current_intensities: Dict[str, float],
        forecasted_intensities: Dict[str, Dict[int, float]],
        candidate_zones: List[str],
        simulation_results: Dict[str, Any] = None,
        api_measurements: Dict[str, List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Generate a detailed HTML report showing migration decision calculations.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Carbon-Aware VM Migration Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; }}
        header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        header p {{ opacity: 0.9; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .summary-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid #667eea; }}
        .summary-card h3 {{ font-size: 14px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }}
        .summary-card .value {{ font-size: 28px; font-weight: bold; color: #333; }}
        .vm-section {{ background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 25px; overflow: hidden; }}
        .vm-header {{ background: #f8f9fa; padding: 20px; border-bottom: 2px solid #e9ecef; }}
        .vm-header h2 {{ font-size: 18px; color: #333; margin-bottom: 8px; }}
        .vm-header .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; font-size: 13px; color: #666; }}
        .vm-header .meta-item {{ display: flex; justify-content: space-between; }}
        .vm-header .meta-label {{ font-weight: 600; }}
        .vm-content {{ padding: 25px; }}
        .intensity-values {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .intensity-card {{ background: #f8f9fa; padding: 15px; border-radius: 6px; border-left: 3px solid #667eea; }}
        .intensity-card .zone {{ font-weight: 600; color: #333; margin-bottom: 5px; }}
        .intensity-card .value {{ font-size: 20px; font-weight: bold; color: #667eea; }}
        .intensity-card .unit {{ font-size: 12px; color: #999; }}
        .candidate-zones {{ margin-bottom: 30px; }}
        .candidate-zones h4 {{ font-size: 14px; font-weight: 600; text-transform: uppercase; color: #666; margin-bottom: 15px; letter-spacing: 0.5px; }}
        .candidate-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
        .candidate-table th {{ background: #f0f0f0; padding: 12px; text-align: left; font-weight: 600; font-size: 13px; color: #666; border-bottom: 2px solid #ddd; }}
        .candidate-table td {{ padding: 12px; border-bottom: 1px solid #eee; font-size: 13px; }}
        .candidate-table tr:hover {{ background: #f9f9f9; }}
        .candidate-table .zone-name {{ font-weight: 600; }}
        .candidate-table .positive {{ color: #28a745; font-weight: 600; }}
        .candidate-table .negative {{ color: #dc3545; font-weight: 600; }}
        .candidate-table .neutral {{ color: #999; }}
        .decision-box {{ background: #f9f9f9; padding: 20px; border-radius: 6px; border-left: 4px solid #28a745; margin-bottom: 20px; }}
        .decision-box.rejected {{ border-left-color: #dc3545; }}
        .decision-box h4 {{ margin-bottom: 8px; font-size: 14px; }}
        .decision-box .decision-text {{ line-height: 1.6; color: #555; }}
        .calculation-details {{ background: #f0f7ff; padding: 15px; border-radius: 6px; font-family: 'Courier New', monospace; font-size: 12px; line-height: 1.6; color: #333; margin: 15px 0; white-space: pre-wrap; word-wrap: break-word; }}
        .breakdown {{ background: white; border: 1px solid #e0e0e0; border-radius: 6px; padding: 15px; margin: 15px 0; }}
        .breakdown h5 {{ font-size: 12px; font-weight: 700; text-transform: uppercase; color: #666; margin-bottom: 10px; letter-spacing: 0.5px; }}
        .breakdown-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }}
        .breakdown-row:last-child {{ border-bottom: none; }}
        .breakdown-row .label {{ color: #666; }}
        .breakdown-row .value {{ font-weight: 600; font-family: monospace; }}
        .sla-check {{ padding: 10px; border-radius: 4px; margin: 10px 0; font-size: 12px; }}
        .sla-check.pass {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
        .sla-check.fail {{ background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
        footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; margin-top: 40px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🌱 Carbon-Aware VM Migration Report</h1>
            <p>Generated on {timestamp}</p>
        </header>

        <div class="summary">
            <div class="summary-card">
                <h3>Total VMs Analyzed</h3>
                <div class="value">{len(vm_inventory)}</div>
            </div>
            <div class="summary-card">
                <h3>Migrations Recommended</h3>
                <div class="value">{sum(1 for d in decisions if d.get('decision').should_migrate)}</div>
            </div>
            <div class="summary-card">
                <h3>Total Potential Savings</h3>
                <div class="value">{sum(d.get('decision').net_carbon_saving for d in decisions):.1f} gCO2</div>
            </div>
        </div>
"""

        # Add details for each VM
        for vm in vm_inventory:
            decision_item = next((d for d in decisions if d.get('decision').vm_id == vm['id']), None)
            if not decision_item:
                continue
            
            decision_obj = decision_item['decision']
            sla_tier = self.sla_classifier.classify(vm["sla_contract"], vm["runtime_metrics"])
            source_zone = vm["current_zone"]
            source_intensity = current_intensities.get(source_zone, 0.0)
            
            html += self._generate_vm_section(
                vm=vm,
                decision=decision_obj,
                sla_tier=sla_tier,
                current_intensities=current_intensities,
                forecasted_intensities=forecasted_intensities,
                candidate_zones=candidate_zones,
                api_measurements=api_measurements,
            )

        # Add simulation scenarios section if provided
        if simulation_results:
            html += self._generate_simulation_section(simulation_results)

        html += """
        <footer>
            <p>This report shows detailed carbon intensity and migration cost calculations.</p>
            <p>Carbon intensity data sourced from <strong>WattTime API</strong> and <strong>ElectricityMaps API</strong> with real-time hourly updates.</p>
            <p>All values are based on current API data and forecasting models.</p>
        </footer>
    </div>
</body>
</html>
"""
        return html


    def _generate_simulation_section(self, simulation_results: Dict[str, Any]) -> str:
        """Generate HTML section for simulation scenarios."""
        html = """
        <div class="vm-section">
            <div class="vm-header">
                <h2>🧪 Simulation Scenarios (Test Data)</h2>
                <p style="margin: 10px 0; color: #666; font-size: 14px;">These scenarios use artificial test data to demonstrate different migration outcomes</p>
            </div>

            <div class="vm-content">
        """

        scenarios = simulation_results.get('scenarios', [])
        for scenario in scenarios:
            html += f"""
                <div class="scenario-section" style="margin-bottom: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #17a2b8;">
                    <h3 style="margin-bottom: 15px; color: #17a2b8; font-size: 16px;">{scenario['name']}</h3>
                    
                    <div class="scenario-vm" style="background: white; padding: 15px; border-radius: 6px; margin-bottom: 15px;">
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 15px;">
                            <div><strong>VM:</strong> {scenario['vm']['id']}</div>
                            <div><strong>Current Zone:</strong> {scenario['vm']['current_zone']}</div>
                            <div><strong>Size:</strong> {scenario['vm']['size_gb']} GB</div>
                            <div><strong>Power:</strong> {scenario['vm']['steady_power_kw']} kW</div>
                            <div><strong>SLA Tier:</strong> {scenario.get('sla_tier', 'N/A')}</div>
                        </div>
                        
                        <div class="intensity-values" style="margin-bottom: 20px;">
                            <h4 style="font-size: 14px; font-weight: 600; margin-bottom: 10px;">Test Carbon Intensities (gCO2/MWh)</h4>
        """

            for zone, intensity in scenario['current_intensities'].items():
                html += f"""
                            <div class="intensity-card" style="display: inline-block; margin: 5px; padding: 10px; background: #e9ecef; border-radius: 4px;">
                                <div class="zone" style="font-weight: 600;">{zone}</div>
                                <div class="value" style="font-size: 16px; color: #17a2b8;">{intensity}</div>
                            </div>
        """

            html += f"""
                        </div>
                        
                        <div class="decision-box {'rejected' if not scenario['decision']['should_migrate'] else ''}" style="margin-top: 15px;">
                            <h4>Decision: {'✗ NO MIGRATION' if not scenario['decision']['should_migrate'] else '✓ MIGRATE'}</h4>
                            <div class="decision-text">{scenario['decision']['reason']}</div>
        """

            if scenario['decision']['should_migrate']:
                html += f"""
                            <div class="breakdown" style="margin-top: 15px;">
                                <h5>Migration Details</h5>
                                <div class="breakdown-row">
                                    <div class="label">Source Zone:</div>
                                    <div class="value">{scenario['decision']['source_zone']}</div>
                                </div>
                                <div class="breakdown-row">
                                    <div class="label">Target Zone:</div>
                                    <div class="value">{scenario['decision']['target_zone']}</div>
                                </div>
                                <div class="breakdown-row">
                                    <div class="label">Net Carbon Saving:</div>
                                    <div class="value">{scenario['decision']['net_carbon_saving']:.1f} gCO2</div>
                                </div>
                                <div class="breakdown-row">
                                    <div class="label">Estimated Downtime:</div>
                                    <div class="value">{scenario['decision']['estimated_downtime']:.1f} seconds</div>
                                </div>
                            </div>
        """

            html += """
                        </div>
                    </div>
                </div>
        """

        html += """
            </div>
        </div>
        """
        return html


    def _generate_vm_section(
        self,
        vm: Dict[str, Any],
        decision: Any,
        sla_tier: Any,
        current_intensities: Dict[str, float],
        forecasted_intensities: Dict[str, Dict[int, float]],
        candidate_zones: List[str],
        api_measurements: Dict[str, List[Dict[str, Any]]] = None,
    ) -> str:
        source_zone = vm["current_zone"]
        source_intensity = current_intensities.get(source_zone, 0.0)
        source_forecast = forecasted_intensities.get(source_zone, {})
        source_avg = (sum(source_forecast.values()) / len(source_forecast)) if source_forecast else source_intensity
        
        html = f"""
        <div class="vm-section">
            <div class="vm-header">
                <h2>VM: {vm['id']}</h2>
                <div class="meta">
                    <div class="meta-item"><span class="meta-label">Current Zone:</span> {source_zone}</div>
                    <div class="meta-item"><span class="meta-label">Size:</span> {vm.get('size_gb', 0):.0f} GB</div>
                    <div class="meta-item"><span class="meta-label">Power:</span> {vm.get('steady_power_kw', 0):.2f} kW</div>
                    <div class="meta-item"><span class="meta-label">Forecast Horizon:</span> {vm.get('forecast_horizon_hours', 0):.1f} hours</div>
                    <div class="meta-item"><span class="meta-label">SLA Tier:</span> {sla_tier.value.upper()}</div>
                    <div class="meta-item"><span class="meta-label">Dirty Rate:</span> {vm.get('runtime_metrics', {}).get('dirty_rate', 0):.1f} MB/s</div>
                </div>
            </div>

            <div class="vm-content">
                <h3 style="margin-bottom: 20px; font-size: 16px; color: #333;">Carbon Intensity Analysis</h3>

                <div class="intensity-values">
                    <div class="intensity-card">
                        <div class="zone">{source_zone} (Current)</div>
                        <div class="value">{source_intensity:.1f}</div>
                        <div class="unit">gCO2/MWh (current) | Avg: {source_avg:.1f}</div>
                        <div class="unit">📊 Current Intensity from WattTime/ElectricityMaps API</div>
                    </div>
"""
        
        # Show all candidate zones
        for zone in candidate_zones:
            if zone == source_zone:
                continue
            zone_intensity = current_intensities.get(zone, 0.0)
            zone_forecast = forecasted_intensities.get(zone, {})
            zone_avg = (sum(zone_forecast.values()) / len(zone_forecast)) if zone_forecast else zone_intensity
            diff = source_avg - zone_avg
            diff_pct = (diff / source_avg * 100) if source_avg > 0 else 0
            
            html += f"""
                    <div class="intensity-card">
                        <div class="zone">{zone}</div>
                        <div class="value">{zone_intensity:.1f}</div>
                        <div class="unit">gCO2/MWh (current) | Avg: {zone_avg:.1f} | Diff: {diff:+.1f} ({diff_pct:+.1f}%)</div>
                    </div>
"""
        
        html += """
                </div>
"""
        
        # Add API measurements section if available
        source_zone = vm["current_zone"]
        if api_measurements and source_zone in api_measurements:
            measurements = api_measurements[source_zone]
            html += """
                <div class="candidate-zones" style="margin-top: 30px; padding: 20px; background: #fff3cd; border-radius: 8px; border-left: 4px solid #ffc107;">
                    <h4 style="color: #856404; margin-bottom: 15px;">🔍 API Measurements</h4>
                    <table class="candidate-table">
                        <thead>
                            <tr>
                                <th>Data Source</th>
                                <th>CO2 Intensity (gCO2/MWh)</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
"""
            for measurement in measurements:
                source = measurement.get("source", "Unknown")
                gco2 = measurement.get("gco2", 0.0)
                is_fallback = "Fallback" in source
                status_class = "negative" if is_fallback else "positive"
                status_text = "⚠️ Fallback" if is_fallback else "✓ Live"
                html += f"""
                            <tr>
                                <td class="zone-name">{source}</td>
                                <td>{gco2:.1f}</td>
                                <td><span class="sla-check {status_class}" style="padding: 5px 10px;">{status_text}</span></td>
                            </tr>
"""
            html += """
                        </tbody>
                    </table>
                </div>
"""
        
        html += """
                <div class="candidate-zones" style="margin-top: 30px; padding: 20px; background: #f0f7ff; border-radius: 8px; border-left: 4px solid #17a2b8;">
                    <h4 style="color: #17a2b8; margin-bottom: 15px;">📡 Data Sources</h4>
                    <div style="font-size: 13px; line-height: 1.8; color: #555;">
                        <div style="margin-bottom: 10px;"><strong>WattTime API:</strong> Provides real-time carbon signal index and region-based intensity</div>
                        <div style="margin-bottom: 10px;"><strong>ElectricityMaps API:</strong> Fallback source for carbon intensity data</div>
                        <div style="margin-bottom: 10px;"><strong>Aggregation Method:</strong> Average of both sources for reliability</div>
                        <div><strong>Update Frequency:</strong> Polled every 5 minutes or on-demand</div>
                    </div>
                </div>

                <div class="candidate-zones">
                    <h4>Candidate Zone Evaluation</h4>
                    <table class="candidate-table">
                        <thead>
                            <tr>
                                <th>Target Zone</th>
                                <th>Intensity (Avg)</th>
                                <th>Projected Savings</th>
                                <th>Migration Cost</th>
                                <th>Net Saving</th>
                                <th>SLA Check</th>
                                <th>Feasible?</th>
                            </tr>
                        </thead>
                        <tbody>
"""
        
        # Calculate for each candidate zone
        for target_zone in candidate_zones:
            if target_zone == source_zone:
                continue
            
            target_forecast = forecasted_intensities.get(target_zone, {})
            target_avg = (sum(target_forecast.values()) / len(target_forecast)) if target_forecast else current_intensities.get(target_zone, 0.0)
            
            estimated_runtime_hours = float(vm.get("forecast_horizon_hours", 2.0))
            steady_power_kw = float(vm.get("steady_power_kw", 1.0))
            projected_savings = max(0.0, source_avg - target_avg) * steady_power_kw * estimated_runtime_hours
            
            # Estimate migration cost (simplified from cost_estimator)
            size_gb = float(vm.get("size_gb", 16.0))
            dirty_rate = float(vm["runtime_metrics"].get("dirty_rate", 10.0))
            migration_time_hours = (size_gb / (dirty_rate / 3600)) if dirty_rate > 0 else 0.5
            migration_carbon_gco2 = migration_time_hours * source_intensity * 0.05  # Rough approximation
            
            net_saving = projected_savings - migration_carbon_gco2
            downtime_seconds = migration_time_hours * 3600 * 0.02  # ~2% overhead
            
            sla_ok = True
            sla_msg = "✓ Pass"
            if sla_tier.value == "gold" and downtime_seconds > 60.0:
                sla_ok = False
                sla_msg = f"✗ Fail ({downtime_seconds:.0f}s > 60s)"
            elif sla_tier.value == "silver" and downtime_seconds > 180.0:
                sla_ok = False
                sla_msg = f"✗ Fail ({downtime_seconds:.0f}s > 180s)"
            
            feasible = sla_ok and net_saving > 0.0
            feasible_str = "✓ Yes" if feasible else "✗ No"
            
            savings_class = "positive" if projected_savings > 0 else "neutral"
            net_class = "positive" if net_saving > 0 else "negative"
            sla_class = "pass" if sla_ok else "fail"
            
            html += f"""
                            <tr>
                                <td class="zone-name">{target_zone}</td>
                                <td>{target_avg:.1f}</td>
                                <td class="{savings_class}">{projected_savings:.1f}</td>
                                <td>{migration_carbon_gco2:.1f}</td>
                                <td class="{net_class}">{net_saving:+.1f}</td>
                                <td><span class="sla-check {sla_class}">{sla_msg}</span></td>
                                <td>{feasible_str}</td>
                            </tr>
"""
        
        html += """
                        </tbody>
                    </table>
                </div>

                <div class="decision-box"""
        
        if decision.should_migrate:
            html += ' style="border-left-color: #28a745;"'
        else:
            html += ' class="rejected"'
        
        html += f""">
                    <h4>Decision: {'✓ MIGRATE' if decision.should_migrate else '✗ NO MIGRATION'}</h4>
                    <div class="decision-text">{decision.reason}</div>
"""
        
        if decision.should_migrate:
            html += f"""
                    <div class="breakdown">
                        <h5>Migration Details</h5>
                        <div class="breakdown-row">
                            <div class="label">Source Zone:</div>
                            <div class="value">{decision.source_zone}</div>
                        </div>
                        <div class="breakdown-row">
                            <div class="label">Target Zone:</div>
                            <div class="value">{decision.target_zone}</div>
                        </div>
                        <div class="breakdown-row">
                            <div class="label">Net Carbon Saving:</div>
                            <div class="value">{decision.net_carbon_saving:.1f} gCO2</div>
                        </div>
                        <div class="breakdown-row">
                            <div class="label">Estimated Downtime:</div>
                            <div class="value">{decision.estimated_downtime:.1f} seconds</div>
                        </div>
                    </div>
"""
        
        html += """
                </div>
            </div>
        </div>
"""
        return html


def save_report_to_file(html: str, filename: str = "migration_report.html") -> str:
    """Save HTML report to file and return the filename."""
    with open(filename, "w") as f:
        f.write(html)
    return filename
