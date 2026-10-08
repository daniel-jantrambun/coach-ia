import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    id               TEXT PRIMARY KEY,   -- "<source>:<id source>"
    source           TEXT NOT NULL,      -- fit | garmin | strava
    sport            TEXT NOT NULL,      -- running, cycling, swimming...
    start_time       TEXT NOT NULL,      -- ISO 8601 UTC
    duration_s       REAL NOT NULL,
    distance_m       REAL,
    elevation_gain_m REAL,
    avg_hr           REAL,
    max_hr           REAL,
    avg_power        REAL,
    file_path        TEXT
);
CREATE INDEX IF NOT EXISTS activities_start_time ON activities (start_time);

CREATE TABLE IF NOT EXISTS plans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    goal_json  TEXT NOT NULL,
    plan_json  TEXT NOT NULL
);

-- Texte rédigé par le LLM, séparé des chiffres : il ne peut jamais modifier le plan.
CREATE TABLE IF NOT EXISTS plan_texts (
    plan_id    INTEGER NOT NULL REFERENCES plans (id) ON DELETE CASCADE,
    week       INTEGER NOT NULL,
    text       TEXT NOT NULL,
    model      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (plan_id, week)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


ACTIVITY_COLUMNS = (
    "id", "source", "sport", "start_time", "duration_s", "distance_m",
    "elevation_gain_m", "avg_hr", "max_hr", "avg_power", "file_path",
)


def upsert_activity(conn: sqlite3.Connection, activity: dict) -> None:
    cols = ", ".join(ACTIVITY_COLUMNS)
    params = ", ".join(f":{c}" for c in ACTIVITY_COLUMNS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in ACTIVITY_COLUMNS if c != "id")
    row = {c: activity.get(c) for c in ACTIVITY_COLUMNS}
    conn.execute(
        f"INSERT INTO activities ({cols}) VALUES ({params}) ON CONFLICT (id) DO UPDATE SET {updates}", row
    )
