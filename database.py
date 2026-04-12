"""
database.py — SQLite persistence for CALM-SLA.

Tables:
  carbon_readings  — per-zone intensity snapshots from each poll cycle
  migration_log    — every migration decision (approved or rejected)
"""
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent / "data" / "calm_sla.db"


def init_db() -> None:
    """Create tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS carbon_readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            zone        TEXT    NOT NULL,
            source      TEXT    NOT NULL,
            intensity   REAL    NOT NULL,
            timestamp   REAL    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS migration_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            vm_id               TEXT    NOT NULL,
            sla_tier            TEXT    NOT NULL,
            source_zone         TEXT    NOT NULL,
            target_zone         TEXT    NOT NULL,
            should_migrate      INTEGER NOT NULL,
            gross_carbon_saved  REAL    NOT NULL DEFAULT 0,
            net_carbon_saved    REAL    NOT NULL,
            carbon_cost         REAL    NOT NULL,
            downtime_seconds    REAL    NOT NULL,
            reason              TEXT    NOT NULL,
            timestamp           REAL    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_carbon_zone ON carbon_readings(zone, timestamp);
        CREATE INDEX IF NOT EXISTS idx_migration_ts ON migration_log(timestamp);
    """)
    conn.commit()
    conn.close()


def log_carbon_readings(zone: str, measurements: List[Dict[str, Any]]) -> None:
    conn = sqlite3.connect(DB_PATH)
    rows = [(zone, m["source"], m["gco2"], time.time()) for m in measurements]
    conn.executemany(
        "INSERT INTO carbon_readings (zone, source, intensity, timestamp) VALUES (?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def log_migration_decision(
    decision,
    sla_tier: str,
    carbon_cost: float,
    gross_carbon_saved: float = 0.0,
) -> None:
    conn = sqlite3.connect(DB_PATH)
    # gross = net + cost (before migration overhead deduction)
    gross = gross_carbon_saved if gross_carbon_saved > 0 else decision.net_carbon_saving + carbon_cost
    conn.execute(
        """INSERT INTO migration_log
           (vm_id, sla_tier, source_zone, target_zone, should_migrate,
            gross_carbon_saved, net_carbon_saved, carbon_cost, downtime_seconds, reason, timestamp)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            decision.vm_id,
            sla_tier,
            decision.source_zone,
            decision.target_zone,
            int(decision.should_migrate),
            gross,
            decision.net_carbon_saving,
            carbon_cost,
            decision.estimated_downtime,
            decision.reason,
            time.time(),
        ),
    )
    conn.commit()
    conn.close()


def get_recent_readings(zone: str, limit: int = 48) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT zone, source, intensity, timestamp FROM carbon_readings "
        "WHERE zone=? ORDER BY timestamp DESC LIMIT ?",
        (zone, limit),
    ).fetchall()
    conn.close()
    return [{"zone": r[0], "source": r[1], "intensity": r[2], "timestamp": r[3]} for r in rows]


def get_migration_log(limit: int = 50) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT vm_id, sla_tier, source_zone, target_zone, should_migrate,
                  gross_carbon_saved, net_carbon_saved, carbon_cost, downtime_seconds, reason, timestamp
           FROM migration_log ORDER BY timestamp DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [
        {
            "vm_id": r[0], "sla_tier": r[1], "source_zone": r[2],
            "target_zone": r[3], "should_migrate": bool(r[4]),
            "gross_carbon_saved": r[5], "net_carbon_saved": r[6],
            "carbon_cost": r[7], "downtime_seconds": r[8],
            "reason": r[9], "timestamp": r[10],
        }
        for r in rows
    ]


def get_summary() -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    total_saved = conn.execute(
        "SELECT COALESCE(SUM(net_carbon_saved),0) FROM migration_log WHERE should_migrate=1"
    ).fetchone()[0]
    total_migrations = conn.execute(
        "SELECT COUNT(*) FROM migration_log WHERE should_migrate=1"
    ).fetchone()[0]
    total_rejected = conn.execute(
        "SELECT COUNT(*) FROM migration_log WHERE should_migrate=0"
    ).fetchone()[0]
    by_tier = conn.execute(
        "SELECT sla_tier, COUNT(*) FROM migration_log WHERE should_migrate=1 GROUP BY sla_tier"
    ).fetchall()
    # Real SLA violations: migrations that WERE executed but breached their tier downtime limit
    sla_violations = conn.execute("""
        SELECT COUNT(*) FROM migration_log WHERE should_migrate=1 AND (
            (sla_tier='Gold'   AND downtime_seconds > 60)  OR
            (sla_tier='Silver' AND downtime_seconds > 180) OR
            (sla_tier='Bronze' AND downtime_seconds > 900)
        )
    """).fetchone()[0]
    # Verify overhead is always deducted (net < gross) for executed migrations
    overhead_ok = conn.execute(
        "SELECT COUNT(*) FROM migration_log WHERE should_migrate=1 AND net_carbon_saved >= gross_carbon_saved AND carbon_cost > 0"
    ).fetchone()[0]
    conn.close()
    return {
        "total_carbon_saved_gco2": round(total_saved, 2),
        "total_migrations": total_migrations,
        "total_rejected": total_rejected,
        "sla_violations": sla_violations,
        "overhead_correctly_deducted": overhead_ok == 0,
        "migrations_by_tier": {r[0]: r[1] for r in by_tier},
    }


def get_baseline_comparison() -> Dict[str, Any]:
    """Compare CALM-SLA decisions vs greedy (always migrate) and no-migration baselines."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT should_migrate, net_carbon_saved, carbon_cost, downtime_seconds, sla_tier FROM migration_log"
    ).fetchall()
    conn.close()

    calm_saved = sum(r[1] for r in rows if r[0])
    calm_migrations = sum(1 for r in rows if r[0])

    # Greedy: would have migrated all candidates (should_migrate=0 ones too, ignoring SLA/cost)
    greedy_saved = sum(r[1] - r[2] for r in rows)   # net = gross - cost, even negatives
    greedy_migrations = len(rows)

    # No migration: zero savings, zero migrations
    return {
        "calm_sla":      {"carbon_saved_gco2": round(calm_saved, 2),  "migrations": calm_migrations},
        "greedy":        {"carbon_saved_gco2": round(greedy_saved, 2), "migrations": greedy_migrations},
        "no_migration":  {"carbon_saved_gco2": 0.0,                    "migrations": 0},
    }
