from enum import Enum
from typing import Dict, Any


class SlaTier(str, Enum):
    GOLD = "Gold"
    SILVER = "Silver"
    BRONZE = "Bronze"


class SlaTierClassifier:
    def classify(self, sla_contract: Dict[str, Any], runtime_metrics: Dict[str, float]) -> SlaTier:
        latency_ms = float(sla_contract.get("latency_ms", 100.0))
        critical = bool(sla_contract.get("critical", False))
        cpu_utilization = float(runtime_metrics.get("cpu_utilization", 0.0))
        dirty_rate = float(runtime_metrics.get("dirty_rate", 0.0))
        headroom = float(runtime_metrics.get("headroom", 100.0))

        if critical or latency_ms <= 20 or cpu_utilization >= 80.0 or headroom <= 20.0:
            return SlaTier.GOLD

        if latency_ms <= 50 or cpu_utilization >= 60.0 or headroom <= 40.0 or dirty_rate >= 50.0:
            return SlaTier.SILVER

        return SlaTier.BRONZE
