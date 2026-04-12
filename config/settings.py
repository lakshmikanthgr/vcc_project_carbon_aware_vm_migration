"""
config/settings.py — Central configuration for CALM-SLA.

All tunable constants live here. Import from this module rather than
hardcoding values in individual components.
"""
import os
from dotenv import load_dotenv

load_dotenv()

#  API credentials 
ELECTRICITYMAPS_API_KEY = os.getenv("ELECTRICITYMAPS_API_KEY")
WATTTIME_USERNAME       = os.getenv("WATTTIME_USERNAME")
WATTTIME_PASSWORD       = os.getenv("WATTTIME_PASSWORD")
WATTTIME_USER_EMAIL     = os.getenv("WATTTIME_USER_EMAIL")
WATTTIME_ORG            = os.getenv("ORG") or os.getenv("WATTTIME_ORG")

#  Data center configuration 
# Maps logical DC names to ElectricityMaps zone strings and coordinates.
# Zone availability: https://app.electricitymaps.com
DATA_CENTERS = {
    "DK-DK1": {"zone": "DK-DK1", "name": "Denmark West",  "lat": 56.0,    "lon": 8.5},
    "SE":      {"zone": "SE",     "name": "Sweden",         "lat": 60.1282, "lon": 18.6435},
    "DE":      {"zone": "DE",     "name": "Germany",        "lat": 51.1657, "lon": 10.4515},
    "US-AK":   {"zone": "US-AK",  "name": "Alaska",         "lat": 64.2008, "lon": -152.2782},
}

#  Timing ─
POLL_INTERVAL_SECONDS     = int(os.getenv("POLL_INTERVAL", "300"))   # carbon API poll frequency
DECISION_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL", "300"))   # orchestrator cycle frequency
FORECAST_HORIZON_HOURS    = 4                                          # TCN prediction window

#  DRL reward weights 
# These mirror the deployment guide spec exactly.
ALPHA = 1.0   # weight on carbon savings (positive reward)
BETA  = 0.3   # weight on migration overhead (negative reward)
GAMMA = {     # SLA violation penalty per tier
    "Gold":   10.0,   # Critical  — never migrate carelessly
    "Silver":  3.0,   # Standard  — migrate with care
    "Bronze":  0.5,   # Flexible  — migrate freely
}

#  SLA downtime limits (seconds) 
SLA_DOWNTIME_LIMITS = {
    "Gold":   60.0,    # Critical workloads  ≤ 60 s
    "Silver": 180.0,   # Standard workloads  ≤ 180 s
    "Bronze": 900.0,   # Flexible workloads  ≤ 900 s (no strict limit)
}

#  Network / cost model ─
NETWORK_CAPACITY_MBPS = 1000.0   # WAN link capacity for migration traffic
ENERGY_PER_GB_KWH     = 0.25     # kWh consumed per GB transferred

#  TCN forecaster 
TCN_SEQ_LEN      = 12    # input sequence length (steps)
TCN_HORIZON_HRS  = FORECAST_HORIZON_HOURS
TCN_NUM_CHANNELS = [16, 32]
TCN_KERNEL_SIZE  = 3
TCN_DROPOUT      = 0.1

#  DRL training ─
DRL_TOTAL_STEPS        = 500_000
DRL_LEARNING_RATE      = 3e-4
DRL_BUFFER_SIZE        = 100_000
DRL_BATCH_SIZE         = 128
DRL_GAMMA              = 0.99
DRL_EXPLORATION_FRAC   = 0.45
DRL_EXPLORATION_EPS    = 0.02
DRL_N_ENVS             = 4
DRL_MODEL_PATH         = "data/models/drl_agent"

#  Paths ─
DB_PATH             = "data/calm_sla.db"
CARBON_HISTORY_DIR  = "data/carbon_history"
MODELS_DIR          = "data/models"
