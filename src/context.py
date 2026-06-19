"""
Assembles the structured fact packet that is the ONLY thing the LLM sees.
No raw data, no dataframes, no SQL results — just pre-computed scalars and lists.
"""
import json
import pathlib
from datetime import date, timedelta

RUNS_LOG = pathlib.Path(__file__).parent.parent / "outputs" / "runs.jsonl"


def _find_historical_note(current_date: str, direction: str) -> str | None:
    """
    Look up the nearest prior anomaly of the same direction from the runs log.
    Returns a formatted note string, or None if no prior anomaly exists.
    """
    if not RUNS_LOG.exists():
        return None

    prior = []
    with open(RUNS_LOG) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                entry.get("direction") == direction
                and entry.get("date") < current_date
            ):
                prior.append(entry)

    if not prior:
        return None

    prior.sort(key=lambda x: x["date"], reverse=True)
    nearest = prior[0]
    days_ago = (
        date.fromisoformat(current_date) - date.fromisoformat(nearest["date"])
    ).days
    return (
        f"A {direction} of similar severity occurred on {nearest['date']} "
        f"({days_ago} days prior), z={nearest['z_score']:+.2f}."
    )


def _days_since_last_anomaly(current_date: str) -> int | None:
    if not RUNS_LOG.exists():
        return None
    dates = []
    with open(RUNS_LOG) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("date") < current_date:
                dates.append(entry["date"])
    if not dates:
        return None
    most_recent = max(dates)
    return (date.fromisoformat(current_date) - date.fromisoformat(most_recent)).days


def build_context(anomaly: dict, drivers: list[dict], segment_dim: str) -> dict:
    """
    Merge anomaly detection output and decomposition output into a single
    clean packet. All values are primitives or lists of primitives.
    """
    current_date = anomaly["date"]
    direction    = anomaly["direction"]

    top_drivers = [
        {
            "segment":          d["segment_value"],
            "gmv_delta":        round(float(d["gmv_delta"]), 2),
            "contribution_pct": round(float(d["contribution_pct"]), 1) if d["contribution_pct"] else None,
            "pct_change":       round(float(d["pct_change"]), 1)       if d["pct_change"]       else None,
            "direction":        d["direction"],
        }
        for d in drivers
    ]

    return {
        "date":            current_date,
        "metric":          anomaly["metric"],
        "direction":       direction,
        "severity":        anomaly["severity"],
        "z_score":         anomaly["z_score"],
        "pct_change":      anomaly["pct_change"],
        "baseline_value":  anomaly["baseline_value"],
        "actual_value":    anomaly["actual_value"],
        "decomposed_by":   segment_dim,
        "top_drivers":     top_drivers,
        "historical_note": _find_historical_note(current_date, direction),
        "days_since_last_anomaly": _days_since_last_anomaly(current_date),
    }
