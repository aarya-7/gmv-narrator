"""
Gate test: contribution math must be internally consistent before the LLM is used.

Two assertions per shock date:
  (a) All segment contributions sum to ~100% of the total delta (within 1%)
  (b) The segment we injected appears in the top 3 contributors by |gmv_delta|
"""
import os
import sys
import pathlib
import pytest
import psycopg2
import psycopg2.extras

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from src.decompose import get_conn, decompose

# (date, segment_dim, injected_segment)
SHOCK_CASES = [
    ("2017-07-21", "category", "bed_bath_table"),
    ("2017-05-16", "category", "sports_leisure"),
    ("2018-06-30", "region",   "Southeast"),
]


def _decompose_all(conn, anomaly_date, segment_dim, table_suffix="_shocked"):
    """Return ALL segments (no LIMIT) for contribution-sum validation."""
    import datetime
    SQL_PATH = pathlib.Path(__file__).parent.parent / "sql" / "04_decompose.sql"
    sql = SQL_PATH.read_text()
    sql = sql.replace("%(table_suffix)s", table_suffix)
    # Remove LIMIT clause for this validation query
    sql = sql.rsplit("LIMIT", 1)[0].rstrip() + ";"

    date_obj = datetime.date.fromisoformat(anomaly_date)
    params = {
        "anomaly_date": date_obj,
        "window_start": date_obj - datetime.timedelta(days=28),
        "window_end":   date_obj - datetime.timedelta(days=1),
        "segment_dim":  segment_dim,
    }
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


@pytest.fixture(scope="module")
def conn():
    c = get_conn()
    yield c
    c.close()


@pytest.mark.parametrize("date,dim,injected_seg", SHOCK_CASES)
def test_contributions_sum_to_100(conn, date, dim, injected_seg):
    rows = _decompose_all(conn, date, dim)
    assert len(rows) > 0, f"No decomposition rows for {date}/{dim}"

    total_contrib = sum(float(r["contribution_pct"]) for r in rows if r["contribution_pct"] is not None)
    assert abs(total_contrib - 100.0) < 1.0, (
        f"{date}/{dim}: contributions sum to {total_contrib:.2f}%, expected ~100%"
    )


@pytest.mark.parametrize("date,dim,injected_seg", SHOCK_CASES)
def test_injected_segment_in_top3(conn, date, dim, injected_seg):
    rows = decompose(conn, date, segment_dim=dim)  # returns top 5, sorted by |delta|
    top3_segments = [r["segment_value"] for r in rows[:3]]
    assert injected_seg in top3_segments, (
        f"{date}/{dim}: '{injected_seg}' not in top-3 drivers {top3_segments}"
    )
