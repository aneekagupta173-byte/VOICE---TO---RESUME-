"""
history.py
Lightweight local history for the résumé roast feature — plain SQLite,
no external service. Powers two rubric-relevant UI pieces on the roast
result screen:
  - an st.metric score with a delta vs. your previous roast
  - an st.data_editor table of every roast you've run, backed by a real
    pandas DataFrame (not just a static list)
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "roast_history.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roast_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            spice_level TEXT,
            score REAL,
            overall TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_roast(spice_level: str, score: float, overall: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO roast_history (created_at, spice_level, score, overall) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), spice_level, score, overall),
    )
    conn.commit()
    conn.close()


def get_history_df() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT created_at, spice_level, score, overall FROM roast_history ORDER BY created_at ASC",
        conn,
    )
    conn.close()
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df


def get_last_score() -> float | None:
    """The most recently saved score, used as the delta baseline for the
    NEXT roast (call this before saving the new one)."""
    df = get_history_df()
    if df.empty:
        return None
    return float(df.iloc[-1]["score"])
