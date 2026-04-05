import os
from typing import Dict, List, Optional, Tuple

import requests


ZONE_COORDINATES: Dict[str, Tuple[float, float]] = {
    "us-east": (38.9072, -77.0369),
    "us-west": (37.7749, -122.4194),
    "eu-central": (50.1109, 8.6821),
}


class ElectricityMapsClient:
    BASE_URL = "https://api.electricitymaps.com/v3/carbon-intensity/latest"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session() if api_key else None

    def get_intensity(self, zone: str) -> float:
        if not self.api_key:
            raise RuntimeError("ElectricityMaps API key is not configured.")

        headers = {"auth-token": self.api_key}
        params = {"zone": zone}
        response = self.session.get(self.BASE_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        return float(payload.get("data", {}).get("carbonIntensity", 0.0))


class WattTimeClient:
    BA_LOOKUP_URL = "https://api.watttime.org/v2/ba"
    BA_LATEST_URL = "https://api.watttime.org/v2/ba/{ba_id}/latest"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session() if api_key else None

    def get_ba_id(self, coordinates: Tuple[float, float]) -> Optional[str]:
        if not self.api_key:
            raise RuntimeError("WattTime API key is not configured.")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"latitude": coordinates[0], "longitude": coordinates[1]}
        response = self.session.get(self.BA_LOOKUP_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", [])
        return items[0].get("id") if items else None

    def get_intensity(self, zone: str, coordinates: Tuple[float, float]) -> float:
        ba_id = self.get_ba_id(coordinates)
        if not ba_id:
            raise RuntimeError(f"Unable to resolve WattTime BA for zone {zone}.")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = self.BA_LATEST_URL.format(ba_id=ba_id)
        response = self.session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        payload = response.json()
        return float(payload.get("data", {}).get("carbonIntensity", 0.0))


class CarbonIntensityMonitor:
    def __init__(self, zones: Optional[List[str]] = None):
        self.zones = zones or ["us-east", "us-west", "eu-central"]
        self.latest = {zone: 0.0 for zone in self.zones}
        self.history = {zone: [] for zone in self.zones}
        self.electricitymaps_client = ElectricityMapsClient(os.getenv("ELECTRICITYMAPS_API_KEY"))
        self.watttime_client = WattTimeClient(os.getenv("WATTTIME_API_KEY"))

    def _synthesize_intensity(self, zone: str, base: float) -> float:
        return max(0.0, base + (hash(zone) % 40 - 20))

    def fetch_electricitymaps(self, zone: str) -> Dict[str, float]:
        try:
            gco2 = self.electricitymaps_client.get_intensity(zone)
            source = "ElectricityMaps"
        except Exception:
            gco2 = self._synthesize_intensity(zone, 220.0)
            source = "ElectricityMaps(Fallback)"

        return {"zone": zone, "source": source, "gco2": gco2}

    def fetch_watttime(self, zone: str) -> Dict[str, float]:
        coordinates = ZONE_COORDINATES.get(zone, (0.0, 0.0))
        try:
            gco2 = self.watttime_client.get_intensity(zone, coordinates)
            source = "WattTime"
        except Exception:
            gco2 = self._synthesize_intensity(zone, 230.0)
            source = "WattTime(Fallback)"

        return {"zone": zone, "source": source, "gco2": gco2}

    def aggregate_intensity(self, measurements: List[Dict[str, float]]) -> float:
        return sum(measurement["gco2"] for measurement in measurements) / len(measurements)

    def poll_once(self) -> Dict[str, float]:
        zone_intensities: Dict[str, float] = {}
        for zone in self.zones:
            measurements = [self.fetch_electricitymaps(zone), self.fetch_watttime(zone)]
            intensity = self.aggregate_intensity(measurements)
            self.latest[zone] = intensity
            self.history[zone].append(intensity)
            zone_intensities[zone] = intensity
        return zone_intensities

    def get_latest_intensity(self, zone: str) -> float:
        return self.latest.get(zone, 0.0)

    def get_history(self, zone: str) -> List[float]:
        return self.history.get(zone, [])
