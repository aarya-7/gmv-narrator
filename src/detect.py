"""
Rolling median + MAD anomaly detection on the daily GMV total series.
Operates on detrended residuals so the growth ramp doesn't trigger false positives.

Why MAD over std-dev: a single large spike inflates std-dev and widens the band,
masking the next anomaly. MAD only looks at the median of absolute deviations and
is therefore resistant to the very outliers we're trying to catch.
"""
import os
import pathlib
import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

from config import ROLLING_WINDOW_DAYS, ANOMALY_THRESHOLD, SEVERITY_HIGH


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "Olist"),
        user=os.getenv("PG_USER", "reflex"),
        password=os.getenv("PG_PASSWORD", "") or None,
    )


def fetch_total_series(conn, table="gmv_total_shocked") -> pd.DataFrame:
    df = pd.read_sql(
        f"SELECT metric_date, gmv FROM {table} ORDER BY metric_date",
        conn,
        parse_dates=["metric_date"],
    )
    df = df.set_index("metric_date").sort_index()
    return df


def compute_anomaly_scores(df: pd.DataFrame, window: int = ROLLING_WINDOW_DAYS) -> pd.DataFrame:
    gmv = df["gmv"].astype(float)

    rolling_median = gmv.rolling(window=window, min_periods=window // 2, center=False).median()
    residual = gmv - rolling_median

    rolling_mad = residual.rolling(window=window, min_periods=window // 2, center=False).apply(
        lambda x: np.median(np.abs(x - np.median(x))), raw=True
    )

    # 0.6745 scales MAD to be comparable to a standard deviation under normality
    robust_z = 0.6745 * residual / rolling_mad.replace(0, np.nan)

    result = df.copy()
    result["rolling_median"] = rolling_median
    result["residual"]       = residual
    result["rolling_mad"]    = rolling_mad
    result["robust_z"]       = robust_z
    return result


def detect_anomaly(series_df: pd.DataFrame, date, threshold: float = ANOMALY_THRESHOLD):
    """Return an anomaly dict for the given date, or None if not anomalous."""
    scored = compute_anomaly_scores(series_df)

    if isinstance(date, str):
        import datetime
        date = datetime.date.fromisoformat(date)

    ts = pd.Timestamp(date)
    if ts not in scored.index:
        return None

    row = scored.loc[ts]
    z = row["robust_z"]
    if pd.isna(z) or abs(z) < threshold:
        return None

    direction  = "drop" if z < 0 else "spike"
    severity   = "high" if abs(z) >= SEVERITY_HIGH else "medium"
    baseline   = float(row["rolling_median"])
    actual     = float(row["gmv"])
    pct_change = (actual - baseline) / baseline * 100 if baseline else None

    return {
        "date":           str(date),
        "metric":         "GMV",
        "direction":      direction,
        "severity":       severity,
        "z_score":        round(float(z), 2),
        "actual_value":   round(actual, 2),
        "baseline_value": round(baseline, 2),
        "pct_change":     round(pct_change, 2) if pct_change is not None else None,
    }


def detect_all_anomalies(conn, threshold: float = ANOMALY_THRESHOLD) -> list[dict]:
    series = fetch_total_series(conn)
    scored = compute_anomaly_scores(series)
    anomalies = []
    for ts, row in scored.iterrows():
        z = row["robust_z"]
        if pd.isna(z) or abs(z) < threshold:
            continue
        direction  = "drop" if z < 0 else "spike"
        severity   = "high" if abs(z) >= SEVERITY_HIGH else "medium"
        baseline   = float(row["rolling_median"])
        actual     = float(row["gmv"])
        pct_change = (actual - baseline) / baseline * 100 if baseline else None
        anomalies.append({
            "date":           str(ts.date()),
            "metric":         "GMV",
            "direction":      direction,
            "severity":       severity,
            "z_score":        round(float(z), 2),
            "actual_value":   round(actual, 2),
            "baseline_value": round(baseline, 2),
            "pct_change":     round(pct_change, 2) if pct_change is not None else None,
        })
    return anomalies


if __name__ == "__main__":
    conn = get_conn()
    anomalies = detect_all_anomalies(conn)
    conn.close()
    print(f"Detected {len(anomalies)} anomalies:")
    for a in anomalies:
        print(f"  {a['date']}  {a['direction']:5s}  z={a['z_score']:+.2f}  "
              f"sev={a['severity']:6s}  pct={a['pct_change']:+.1f}%")
