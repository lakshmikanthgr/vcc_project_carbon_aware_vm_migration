"""
fetch_history.py — Fetch historical carbon intensity data for TCN training.

Pulls up to 24 hours of hourly readings from the ElectricityMaps
/carbon-intensity/history endpoint and saves one CSV per zone to
data/carbon_history/. The TCN forecaster loads these CSVs at startup.

Run once before training:
    python fetch_history.py

If the API is unavailable, synthetic data is generated instead so the
TCN can still be trained — the synthetic data uses a realistic diurnal
sine pattern with noise.

Output files:
    data/carbon_history/DK-DK1.csv
    data/carbon_history/SE.csv
    data/carbon_history/DE.csv
    data/carbon_history/US-AK.csv
"""

import csv
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import requests

from config.settings import (
    ELECTRICITYMAPS_API_KEY,
    DATA_CENTERS,
    CARBON_HISTORY_DIR,
)

OUTPUT_DIR = Path(CARBON_HISTORY_DIR)
EM_HISTORY_URL = "https://api.electricitymaps.com/v3/carbon-intensity/history"

# Typical base carbon intensities per zone (gCO2/kWh) for synthetic fallback
ZONE_BASE = {
    "DK-DK1": 250.0,
    "SE":       50.0,
    "DE":      350.0,
    "US-AK":   200.0,
}


#  Live fetch ─

def fetch_live(zone: str, api_key: str) -> Optional[List[Tuple[str, float]]]:
    """Fetch up to 24 hours of hourly readings from ElectricityMaps."""
    try:
        resp = requests.get(
            EM_HISTORY_URL,
            headers={"auth-token": api_key},
            params={"zone": zone},
            timeout=15,
        )
        resp.raise_for_status()
        records = resp.json().get("history", [])
        result = []
        for r in records:
            dt  = r.get("datetime", "")
            val = r.get("carbonIntensity")
            if dt and val is not None:
                result.append((dt, float(val)))
        result.sort(key=lambda x: x[0])
        return result
    except Exception as exc:
        print(f"  [warn] ElectricityMaps API error for {zone}: {exc}")
        return None


#  Synthetic fallback ─

def generate_synthetic(zone: str, n_hours: int = 48) -> List[Tuple[str, float]]:
    """
    Generate n_hours of synthetic hourly carbon data using a diurnal sine
    pattern with Gaussian noise. Suitable for TCN training when the live
    API is unavailable.
    """
    base = ZONE_BASE.get(zone, 250.0)
    now  = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    records = []
    rng = random.Random(hash(zone))
    for h in range(n_hours, 0, -1):
        ts  = now - timedelta(hours=h)
        t   = ts.hour / 24.0
        val = max(20.0, base + math.sin(2 * math.pi * t) * base * 0.35 + rng.gauss(0, 12))
        records.append((ts.isoformat(), round(val, 1)))
    return records


#  Save CSV ─

def save_csv(zone: str, records: List[Tuple[str, float]]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{zone}.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["datetime", "carbonIntensity"])
        writer.writerows(records)
    return path


#  Main ─

def fetch_and_save_all() -> None:
    print("=== CALM-SLA: Fetching carbon history ===\n")
    use_live = bool(ELECTRICITYMAPS_API_KEY)
    if not use_live:
        print("[warn] ELECTRICITYMAPS_API_KEY not set — using synthetic data.\n")

    for zone in DATA_CENTERS:
        print(f"  Zone: {zone}")
        records = None

        if use_live:
            print(f"    Fetching from ElectricityMaps...", end=" ", flush=True)
            records = fetch_live(zone, ELECTRICITYMAPS_API_KEY)
            if records:
                print(f"got {len(records)} records.")
            else:
                print("failed, falling back to synthetic.")

        if not records:
            print(f"    Generating {48} synthetic hourly records...", end=" ", flush=True)
            records = generate_synthetic(zone, n_hours=48)
            print("done.")

        path = save_csv(zone, records)
        print(f"    Saved {len(records)} rows → {path}\n")

    print("=== Done. Run python train_tcn.py next. ===")


if __name__ == "__main__":
    fetch_and_save_all()
