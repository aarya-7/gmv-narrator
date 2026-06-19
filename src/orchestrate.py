"""
End-to-end orchestration: detect → decompose → build context → narrate → save.

Run as a backfill over the full analysis window to produce a body of example
narratives. For each anomalous day the pipeline writes:
  - outputs/narratives/{date}.md  — human-readable narrative + context packet
  - outputs/runs.jsonl             — structured log for historical-note lookups
"""
import json
import sys
import pathlib
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.detect    import get_conn, fetch_total_series, detect_anomaly
from src.decompose import decompose
from src.context   import build_context
from src.narrate   import narrate
from config        import WINDOW_START, WINDOW_END, ROLLING_WINDOW_DAYS

NARRATIVES_DIR = pathlib.Path(__file__).parent.parent / "outputs" / "narratives"
RUNS_LOG       = pathlib.Path(__file__).parent.parent / "outputs" / "runs.jsonl"


def _choose_segment_dim(anomaly: dict, conn) -> str:
    """
    Pick whichever segment dimension has a stronger top driver (higher |contribution_pct|).
    Falls back to 'category' if decomposition fails.
    """
    best_dim   = "category"
    best_score = 0.0
    for dim in ("category", "region"):
        try:
            drivers = decompose(conn, anomaly["date"], segment_dim=dim)
            if drivers and drivers[0]["contribution_pct"] is not None:
                score = abs(float(drivers[0]["contribution_pct"]))
                if score > best_score:
                    best_score = score
                    best_dim   = dim
        except Exception:
            pass
    return best_dim


def _save_outputs(anomaly_date: str, ctx: dict, narrative: str):
    NARRATIVES_DIR.mkdir(parents=True, exist_ok=True)

    # Markdown file: context packet + narrative side-by-side for auditability
    md_path = NARRATIVES_DIR / f"{anomaly_date}.md"
    md = (
        f"# GMV Anomaly — {anomaly_date}\n\n"
        f"## Context Packet\n\n```json\n{json.dumps(ctx, indent=2)}\n```\n\n"
        f"## Narrative\n\n{narrative}\n"
    )
    md_path.write_text(md)

    # Append to JSONL log
    log_entry = {
        "date":      ctx["date"],
        "direction": ctx["direction"],
        "severity":  ctx["severity"],
        "z_score":   ctx["z_score"],
        "pct_change": ctx["pct_change"],
        "segment_dim": ctx["decomposed_by"],
        "top_driver":  ctx["top_drivers"][0]["segment"] if ctx["top_drivers"] else None,
    }
    with open(RUNS_LOG, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


def run_for_date(conn, series_df, date_obj: date) -> dict | None:
    anomaly = detect_anomaly(series_df, date_obj)
    if anomaly is None:
        return None

    seg_dim = _choose_segment_dim(anomaly, conn)
    drivers = decompose(conn, anomaly["date"], segment_dim=seg_dim)
    if not drivers:
        return None

    ctx       = build_context(anomaly, drivers, seg_dim)
    narrative = narrate(ctx)
    _save_outputs(anomaly["date"], ctx, narrative)
    return {"date": anomaly["date"], "direction": anomaly["direction"], "narrative": narrative}


def run_backfill(start: date = WINDOW_START, end: date = WINDOW_END):
    conn      = get_conn()
    series_df = fetch_total_series(conn)

    # Clear runs log so historical notes are built from scratch
    RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
    if RUNS_LOG.exists():
        RUNS_LOG.unlink()

    current = start
    narrated = 0
    while current <= end:
        try:
            result = run_for_date(conn, series_df, current)
            if result:
                print(f"[{current}] {result['direction']:5s} → narrated ({narrated + 1})")
                narrated += 1
        except Exception as e:
            print(f"[{current}] ERROR: {e}")
        current += timedelta(days=1)

    conn.close()
    print(f"\nDone. {narrated} anomalies narrated → {NARRATIVES_DIR}")


if __name__ == "__main__":
    run_backfill()
