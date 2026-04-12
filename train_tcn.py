"""
train_tcn.py — Train the TCN carbon forecaster offline from CSV history.

Loads carbon history CSVs produced by fetch_history.py, trains one TCN
model per zone, and saves .pt checkpoints to data/models/.

Run order:
    1. python fetch_history.py
    2. python train_tcn.py
    3. python orchestrator_loop.py   (or bash run.sh)

Usage:
    python train_tcn.py                # train all zones, 50 epochs
    python train_tcn.py --epochs 100   # more epochs
    python train_tcn.py --eval-only    # evaluate existing models
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List

import numpy as np

from config.settings import (
    DATA_CENTERS,
    CARBON_HISTORY_DIR,
    MODELS_DIR,
    TCN_SEQ_LEN,
    TCN_HORIZON_HRS,
    TCN_NUM_CHANNELS,
    TCN_KERNEL_SIZE,
    TCN_DROPOUT,
)
from services.carbon_forecaster import CarbonForecaster

HISTORY_DIR = Path(CARBON_HISTORY_DIR)
MODEL_DIR   = Path(MODELS_DIR)


# ── Load CSV ───────────────────────────────────────────────────────────────────

def load_csv(zone: str) -> List[float]:
    path = HISTORY_DIR / f"{zone}.csv"
    if not path.exists():
        return []
    values = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                values.append(float(row["carbonIntensity"]))
            except (KeyError, ValueError):
                pass
    return values


# ── Evaluate a trained forecaster ─────────────────────────────────────────────

def evaluate_forecaster(forecaster: CarbonForecaster, history: List[float]) -> Dict[str, float]:
    """Compute MAE on held-out last 10% of history."""
    n = len(history)
    split = max(TCN_SEQ_LEN + TCN_HORIZON_HRS, int(n * 0.9))
    test_seq = history[split - TCN_SEQ_LEN : split]
    test_target = history[split : split + TCN_HORIZON_HRS]

    if len(test_seq) < TCN_SEQ_LEN or len(test_target) < TCN_HORIZON_HRS:
        return {"mae": float("nan"), "n_test": 0}

    preds = forecaster.forecast(test_seq)
    pred_vals = [preds.get(h, 0.0) for h in range(1, TCN_HORIZON_HRS + 1)]
    mae = float(np.mean(np.abs(np.array(pred_vals) - np.array(test_target))))
    return {"mae": round(mae, 2), "n_test": len(test_target)}


# ── Main ───────────────────────────────────────────────────────────────────────

def train_all(epochs: int = 50, eval_only: bool = False) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    stats = {}

    print(f"\n{'='*52}")
    print(f"  TCN Carbon Forecaster — {'Evaluation' if eval_only else f'Training ({epochs} epochs)'}")
    print(f"  Zones: {list(DATA_CENTERS.keys())}")
    print(f"{'='*52}\n")

    for zone in DATA_CENTERS:
        print(f"  [{zone}]")
        history = load_csv(zone)

        if not history:
            print(f"    No CSV found at {HISTORY_DIR}/{zone}.csv — run fetch_history.py first.")
            continue

        print(f"    Loaded {len(history)} hourly readings from CSV.")

        model_path = str(MODEL_DIR / f"tcn_{zone}.pt")
        forecaster = CarbonForecaster(
            horizon_hours=TCN_HORIZON_HRS,
            seq_len=TCN_SEQ_LEN,
            num_channels=TCN_NUM_CHANNELS,
            kernel_size=TCN_KERNEL_SIZE,
            dropout=TCN_DROPOUT,
        )

        if eval_only:
            try:
                forecaster.load(model_path)
                print(f"    Loaded model from {model_path}")
            except Exception as exc:
                print(f"    No saved model ({exc}) — cannot evaluate.")
                continue
        else:
            min_needed = TCN_SEQ_LEN + TCN_HORIZON_HRS
            if len(history) < min_needed:
                print(f"    Need ≥{min_needed} samples, have {len(history)} — skipping training.")
                continue

            print(f"    Training for {epochs} epochs...", end=" ", flush=True)
            # Use 90% for training
            train_data = history[: int(len(history) * 0.9)]
            forecaster.train(train_data, epochs=epochs)
            forecaster.save(model_path)
            print(f"saved → {model_path}")

        # Evaluate
        result = evaluate_forecaster(forecaster, history)
        mae_str = f"{result['mae']:.2f} gCO2/kWh" if not np.isnan(result['mae']) else "n/a"
        print(f"    MAE on held-out test set: {mae_str}  (n={result['n_test']})")

        # Spot-check forecast
        recent = history[-TCN_SEQ_LEN:]
        fc = forecaster.forecast(recent)
        fc_vals = [f"{fc.get(h, 0):.0f}" for h in range(1, 5)]
        print(f"    Forecast (h+1..h+4): {' | '.join(fc_vals)} gCO2/kWh")

        stats[zone] = result
        print()

    # Save stats
    stats_path = MODEL_DIR / "tcn_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Stats saved → {stats_path}")
    print(f"\n{'='*52}")
    print("  Training complete. Next step: bash run.sh")
    print(f"{'='*52}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train TCN carbon forecaster from CSV history.")
    parser.add_argument("--epochs",    type=int,  default=50,    help="Training epochs per zone")
    parser.add_argument("--eval-only", action="store_true",       help="Skip training, evaluate existing models")
    args = parser.parse_args()
    train_all(epochs=args.epochs, eval_only=args.eval_only)


if __name__ == "__main__":
    main()
