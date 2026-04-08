import os
import time
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth

load_dotenv()


ZONE_COORDINATES: Dict[str, Tuple[float, float]] = {
    "DK-DK1": (56.0, 8.5),
    "DE": (51.1657, 10.4515),
    "SE": (60.1282, 18.6435),
    "US-AK": (64.2008, -152.2782),
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
    DEFAULT_BASE_URL = "https://api.watttime.org"
    REGION_FROM_LOC_PATH = "/region-from-loc"
    SIGNAL_INDEX_PATH = "/signal-index"

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, user_email: Optional[str] = None, org: Optional[str] = None, timeout: int = 10):
        self.username = username
        self.password = password
        self.user_email = user_email
        self.org = org
        self.timeout = timeout
        self.session = requests.Session()
        self.token: Optional[str] = None
        self._region_cache: Dict[Tuple[float, float], Tuple[str, float]] = {}  # coordinates -> (region, timestamp)

        base_url = os.getenv("WATTTIME_USING_API_URL") or os.getenv("WATTTIME_API_URL") or self.DEFAULT_BASE_URL
        self.base_url = base_url.rstrip("/")
        self.REGISTER_URL = f"{self.base_url}/register"
        self.LOGIN_URL = f"{self.DEFAULT_BASE_URL}/login"
        self.REGION_FROM_LOC_URL = f"{self.base_url}{self.REGION_FROM_LOC_PATH}"
        self.SIGNAL_INDEX_URL = f"{self.base_url}{self.SIGNAL_INDEX_PATH}"
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
        #print(f"WattTime registration response: {register_response.status_code} - {register_response.text}")
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
            "latitude": coordinates[0],
            "longitude": coordinates[1],
            "signal_type": signal_type,

        }
        response = self.session.get(self.REGION_FROM_LOC_URL, headers=headers, params=params, timeout=self.timeout)
        #print(f"[DEBUG] Region request: {self.REGION_FROM_LOC_URL} coords={coordinates} status={response.status_code}")
        response.raise_for_status()
        payload = response.json()
        region = payload.get("region")
        #print(f"[DEBUG] Got region: {region} from payload: {payload}")
        if region:
            self._region_cache[coordinates] = (region, time.time())
        return region

    def get_signal_index(self, coordinates: Tuple[float, float], signal_type: str = "co2_moer") -> Optional[float]:
        """
        Get current carbon signal index from WattTime signal-index endpoint.
        Returns the raw value directly without needing to parse forecast arrays.
        """
        region = self.get_region(coordinates, signal_type)
        if not region:
            raise RuntimeError(f"Unable to resolve WattTime region for coordinates {coordinates}.")

        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "region": region,
            "signal_type": signal_type,
        }
        response = self.session.get(self.SIGNAL_INDEX_URL, headers=headers, params=params, timeout=self.timeout)
        print(f"[DEBUG] Signal-index request: {self.SIGNAL_INDEX_URL} region={region} status={response.status_code}")
        response.raise_for_status()
        payload = response.json()
        # Signal-index returns data as a list with one point
        data = payload.get("data", [])
        print(f"[Lks] Signal-index response data: {data}")
        if data and isinstance(data, list) and len(data) > 0:
            return float(data[0].get("value", 0.0))
        return None

    def get_intensity(self, zone: str, coordinates: Tuple[float, float]) -> float:
        """
        Get current carbon intensity from WattTime signal-index endpoint.
        Returns the current CO2 MOER value directly.
        """
        try:
            value = self.get_signal_index(coordinates)
            if value is not None:
                return max(0.0, float(value))
        except Exception as e:
            print(f"[DEBUG] WattTime signal-index error for {zone}: {e}")
        
        raise RuntimeError(
            f"Unable to fetch WattTime carbon intensity for zone {zone}. "
            "Ensure region is valid and signal data is available."
        )


class CarbonIntensityMonitor:
    def __init__(self, zones: Optional[List[str]] = None, poll_interval: int = 300):
        self.zones = zones or ["DK-DK1", "DE", "SE", "US-AK"]
        self.poll_interval = poll_interval  # seconds between polls
        self.latest = {zone: 0.0 for zone in self.zones}
        self.history = {zone: [] for zone in self.zones}
        self.latest_measurements = {zone: [] for zone in self.zones}  # Store individual API measurements
        self.last_poll = 0.0
        self.electricitymaps_client = ElectricityMapsClient(os.getenv("ELECTRICITYMAPS_API_KEY"))
        self.watttime_client = WattTimeClient(
            username=os.getenv("WATTTIME_USERNAME"),
            password=os.getenv("WATTTIME_PASSWORD"),
            user_email=os.getenv("WATTTIME_USER_EMAIL"),
            org=os.getenv("WATTTIME_ORG") or os.getenv("ORG")
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
            self.latest_measurements[zone] = measurements  # Store individual measurements
            self.history[zone].append(intensity)
            zone_intensities[zone] = intensity
        self.last_poll = current_time
        return zone_intensities

    def get_forecast(self, zone: str, horizon_hours: int = 24) -> List[Dict[str, any]]:
        # Signal-index provides current intensity only; return empty as no forecast data available
        return []

    def get_latest_intensity(self, zone: str) -> float:
        return self.latest.get(zone, 0.0)

    def get_history(self, zone: str) -> List[float]:
        return self.history.get(zone, [])

    def get_measurements(self, zone: str) -> List[Dict[str, float]]:
        """Get individual API measurements (WattTime, ElectricityMaps) for a zone."""
        return self.latest_measurements.get(zone, [])

