import os
import time
from typing import Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth


ZONE_COORDINATES: Dict[str, Tuple[float, float]] = {
    "us-east": (38.9072, -77.0369),
    "us-west": (37.7749, -122.4194),
    "eu-central": (50.1109, 8.6821),
}


class ElectricityMapsClient:
    BASE_URL = "https://api.electricitymaps.com/v3/carbon-intensity/latest"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session() if api_key else None
        self._cache: Dict[str, Tuple[float, float]] = {}  # zone -> (intensity, timestamp)

    def get_intensity(self, zone: str) -> float:
        if not self.api_key:
            raise RuntimeError("ElectricityMaps API key is not configured.")

        # Check cache (valid for 5 minutes)
        if zone in self._cache:
            intensity, timestamp = self._cache[zone]
            if time.time() - timestamp < 300:
                return intensity

        headers = {"auth-token": self.api_key}
        params = {"zone": zone}
        response = self.session.get(self.BASE_URL, headers=headers, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        intensity = float(payload.get("data", {}).get("carbonIntensity", 0.0))
        self._cache[zone] = (intensity, time.time())
        return intensity


class WattTimeClient:
    REGISTER_URL = "https://api.watttime.org/register"
    LOGIN_URL = "https://api.watttime.org/login"
    REGION_FROM_LOC_URL = "https://api.watttime.org/v3/region-from-loc"
    FORECAST_URL = "https://api.watttime.org/v3/forecast"
    BA_LOOKUP_URL = "https://api.watttime.org/v2/ba"  # Keep v2 for backward compatibility
    BA_LATEST_URL = "https://api.watttime.org/v2/ba/{ba_id}/latest"  # Keep v2 for backward compatibility

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, user_email: Optional[str] = None, org: Optional[str] = None, timeout: int = 10):
        self.username = username
        self.password = password
        self.user_email = user_email
        self.org = org
        self.timeout = timeout
        self.session = requests.Session()
        self.token: Optional[str] = None
        self._cache: Dict[Tuple[float, float], Tuple[str, float]] = {}  # coordinates -> (ba_id, timestamp)
        self._region_cache: Dict[Tuple[float, float], Tuple[str, float]] = {}  # coordinates -> (region, timestamp)

        if self.username and self.password and self.user_email and self.org:
            self.token = self.authenticate()

    def authenticate(self) -> str:
        # Register if needed
        register_params = {
            'username': self.username,
            'password': self.password,
            'email': self.user_email,
            'org': self.org
        }
        register_response = self.session.post(self.REGISTER_URL, json=register_params, timeout=self.timeout)
        if register_response.status_code not in [200, 201, 409]:  # 409 means already registered
            register_response.raise_for_status()

        # Login
        login_response = self.session.get(self.LOGIN_URL, auth=HTTPBasicAuth(self.username, self.password), timeout=self.timeout)
        login_response.raise_for_status()
        token = login_response.json().get('token')
        if not token:
            raise RuntimeError("WattTime login response did not include a token.")
        return str(token)

    def _ensure_token(self) -> str:
        if not self.token:
            raise RuntimeError("WattTime API token is not configured. Provide username, password, email, and org.")
        return self.token

    def get_region(self, coordinates: Tuple[float, float], signal_type: str = "co2_moer") -> Optional[str]:
        # Check cache (valid for 1 hour)
        if coordinates in self._region_cache:
            region, timestamp = self._region_cache[coordinates]
            if time.time() - timestamp < 3600:
                return region

        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "signal_type": signal_type,
            "latitude": coordinates[0],
            "longitude": coordinates[1]
        }
        response = self.session.get(self.REGION_FROM_LOC_URL, headers=headers, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        region = payload.get("region")
        if region:
            self._region_cache[coordinates] = (region, time.time())
        return region

    def get_forecast(self, coordinates: Tuple[float, float], signal_type: str = "co2_moer", horizon_hours: int = 24) -> List[Dict[str, any]]:
        region = self.get_region(coordinates, signal_type)
        if not region:
            raise RuntimeError(f"Unable to resolve WattTime region for coordinates {coordinates}.")

        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "region": region,
            "signal_type": signal_type,
            "horizon_hours": min(horizon_hours, 72)  # Max 72 hours
        }
        response = self.session.get(self.FORECAST_URL, headers=headers, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", [])

    def get_ba_id(self, coordinates: Tuple[float, float]) -> Optional[str]:
        # Check cache (valid for 1 hour)
        if coordinates in self._cache:
            ba_id, timestamp = self._cache[coordinates]
            if time.time() - timestamp < 3600:
                return ba_id

        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        params = {"latitude": coordinates[0], "longitude": coordinates[1]}
        response = self.session.get(self.BA_LOOKUP_URL, headers=headers, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", [])
        ba_id = items[0].get("id") if items else None
        if ba_id:
            self._cache[coordinates] = (ba_id, time.time())
        return ba_id

    def get_intensity(self, zone: str, coordinates: Tuple[float, float]) -> float:
        ba_id = self.get_ba_id(coordinates)
        if not ba_id:
            raise RuntimeError(f"Unable to resolve WattTime BA for zone {zone}.")

        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = self.BA_LATEST_URL.format(ba_id=ba_id)
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        return float(payload.get("data", {}).get("carbonIntensity", 0.0))


class CarbonIntensityMonitor:
    def __init__(self, zones: Optional[List[str]] = None, poll_interval: int = 300):
        self.zones = zones or ["us-east", "us-west", "eu-central"]
        self.poll_interval = poll_interval  # seconds between polls
        self.latest = {zone: 0.0 for zone in self.zones}
        self.history = {zone: [] for zone in self.zones}
        self.last_poll = 0.0
        self.electricitymaps_client = ElectricityMapsClient(os.getenv("ELECTRICITYMAPS_API_KEY"))
        self.watttime_client = WattTimeClient(
            username=os.getenv("WATTTIME_USERNAME"),
            password=os.getenv("WATTTIME_PASSWORD"),
            user_email=os.getenv("WATTTIME_USER_EMAIL"),
            org=os.getenv("WATTTIME_ORG")
        )

    def _synthesize_intensity(self, zone: str, base: float) -> float:
        # More realistic synthetic data with some variation
        import random
        random.seed(hash(zone) + int(time.time() // 3600))  # Hourly variation
        return max(0.0, base + random.uniform(-50, 50))

    def fetch_electricitymaps(self, zone: str) -> Dict[str, float]:
        try:
            gco2 = self.electricitymaps_client.get_intensity(zone)
            source = "ElectricityMaps"
        except Exception as e:
            print(f"ElectricityMaps API error for {zone}: {e}")
            gco2 = self._synthesize_intensity(zone, 220.0)
            source = "ElectricityMaps(Fallback)"

        return {"zone": zone, "source": source, "gco2": gco2}

    def fetch_watttime(self, zone: str) -> Dict[str, float]:
        coordinates = ZONE_COORDINATES.get(zone, (0.0, 0.0))
        try:
            gco2 = self.watttime_client.get_intensity(zone, coordinates)
            source = "WattTime"
        except Exception as e:
            print(f"WattTime API error for {zone}: {e}")
            gco2 = self._synthesize_intensity(zone, 230.0)
            source = "WattTime(Fallback)"

        return {"zone": zone, "source": source, "gco2": gco2}

    def aggregate_intensity(self, measurements: List[Dict[str, float]]) -> float:
        return sum(measurement["gco2"] for measurement in measurements) / len(measurements)

    def poll_once(self) -> Dict[str, float]:
        current_time = time.time()
        if current_time - self.last_poll < self.poll_interval:
            return self.latest  # Return cached if too soon

        zone_intensities: Dict[str, float] = {}
        for zone in self.zones:
            measurements = [self.fetch_electricitymaps(zone), self.fetch_watttime(zone)]
            intensity = self.aggregate_intensity(measurements)
            self.latest[zone] = intensity
            self.history[zone].append(intensity)
            zone_intensities[zone] = intensity
        self.last_poll = current_time
        return zone_intensities

    def get_forecast(self, zone: str, horizon_hours: int = 24) -> List[Dict[str, any]]:
        coordinates = ZONE_COORDINATES.get(zone, (0.0, 0.0))
        try:
            forecast_data = self.watttime_client.get_forecast(coordinates, horizon_hours=horizon_hours)
            return forecast_data
        except Exception as e:
            print(f"WattTime forecast API error for {zone}: {e}")
            # Return empty forecast as fallback
            return []

    def get_latest_intensity(self, zone: str) -> float:
        return self.latest.get(zone, 0.0)

    def get_history(self, zone: str) -> List[float]:
        return self.history.get(zone, [])

