"""
Segment contribution decomposition — no LLM, pure SQL algebra.

For a flagged date, computes each segment's dollar contribution to the total
delta versus its own rolling baseline, then ranks by absolute contribution.
"""
import os
import pathlib
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

SQL_PATH = pathlib.Path(__file__).parent.parent / "sql" / "04_decompose.sql"


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "Olist"),
        user=os.getenv("PG_USER", "reflex"),
        password=os.getenv("PG_PASSWORD", "") or None,
    )


def decompose(
    conn,
    anomaly_date: str,
    segment_dim: str = "category",
    window_days: int = 28,
    table_suffix: str = "_shocked",
) -> list[dict]:
    """
    Returns top-5 segment drivers for the given anomaly date.
    table_suffix: '_shocked' (default) or '' (clean tables).
    """
    import datetime
    date_obj = (
        datetime.date.fromisoformat(anomaly_date)
        if isinstance(anomaly_date, str) else anomaly_date
    )
    window_start = date_obj - datetime.timedelta(days=window_days)
    window_end   = date_obj - datetime.timedelta(days=1)

    sql_template = SQL_PATH.read_text()
    # The SQL uses %(table_suffix)s as a literal string interpolation for table names
    # (not a bind param — psycopg2 can't bind table names)
    sql = sql_template.replace("%(table_suffix)s", table_suffix)

    params = {
        "anomaly_date": date_obj,
        "window_start": window_start,
        "window_end":   window_end,
        "segment_dim":  segment_dim,
    }

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [dict(r) for r in rows]


if __name__ == "__main__":
    conn = get_conn()
    for date, dim in [
        ("2017-07-21", "category"),
        ("2017-05-16", "category"),
        ("2018-06-30", "region"),
    ]:
        print(f"\n── {date} decomposed by {dim} ──")
        drivers = decompose(conn, date, segment_dim=dim)
        for d in drivers:
            print(f"  {d['segment_value']:30s}  delta={d['gmv_delta']:>10,.0f}  "
                  f"contrib={d['contribution_pct']:>+7.1f}%  pct_chg={d['pct_change']:>+6.1f}%")
    conn.close()
