"""
Inject synthetic anomalies into the gmv_fact_shocked / gmv_total_shocked tables.
The clean gmv_fact / gmv_total tables are never touched.
The detector is never shown the shock manifest — it is blind to what was injected.

Shocks are placed on dates that were already near-anomalous in clean data so that
a realistic multiplier reliably crosses the MAD-based z=3.5 threshold:

  1. 2017-07-21  bed_bath_table ×9.0  → expected z≈+4.3  (spike, category driver)
  2. 2018-06-30  Southeast     ×0.80  → expected z≈−3.82 (drop,  region driver)
  3. 2017-05-16  sports_leisure ×4.0  → expected z≈+8.3  (spike, category driver)
"""
import os
import json
import pathlib
import psycopg2
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

MANIFEST_PATH = pathlib.Path(__file__).parent.parent / "outputs" / "shock_manifest.json"

SHOCKS = [
    {
        "date":          "2017-07-21",
        "segment_dim":   "category",
        "segment_value": "bed_bath_table",
        "multiplier":    9.0,    # +800% in category → expected z≈+4.3
        "description":   "Synthetic spike: bed_bath_table ×9 (simulates flash-sale surge)",
    },
    {
        "date":          "2018-06-30",
        "segment_dim":   "region",
        "segment_value": "Southeast",
        "multiplier":    0.80,   # −20% in region → expected z≈−3.82 (MAD is low on this date)
        "description":   "Synthetic drop: Southeast −20% (simulates regional fulfilment outage)",
    },
    {
        "date":          "2017-05-16",
        "segment_dim":   "category",
        "segment_value": "sports_leisure",
        "multiplier":    4.0,    # +300% in category → expected z≈+8.3
        "description":   "Synthetic spike: sports_leisure ×4 (simulates viral sporting-event promotion)",
    },
]


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "Olist"),
        user=os.getenv("PG_USER", "reflex"),
        password=os.getenv("PG_PASSWORD", "") or None,
    )


def apply_shocks(conn):
    results = []
    with conn.cursor() as cur:
        for shock in SHOCKS:
            # Fetch current value
            cur.execute(
                "SELECT gmv FROM gmv_fact_shocked WHERE metric_date=%s AND segment_dim=%s AND segment_value=%s",
                (shock["date"], shock["segment_dim"], shock["segment_value"]),
            )
            row = cur.fetchone()
            if row is None:
                print(f"  WARN: no row found for {shock} — skipping")
                continue
            original_gmv = float(row[0])
            new_gmv = original_gmv * shock["multiplier"]
            delta = new_gmv - original_gmv

            # Update segment row
            cur.execute(
                """UPDATE gmv_fact_shocked
                   SET gmv = %s
                   WHERE metric_date=%s AND segment_dim=%s AND segment_value=%s""",
                (new_gmv, shock["date"], shock["segment_dim"], shock["segment_value"]),
            )

            # Propagate delta to gmv_total_shocked
            cur.execute(
                "UPDATE gmv_total_shocked SET gmv = gmv + %s WHERE metric_date=%s",
                (delta, shock["date"]),
            )

            results.append({**shock, "original_gmv": original_gmv, "new_gmv": new_gmv, "delta": delta})
            print(f"  injected: {shock['date']} {shock['segment_dim']}={shock['segment_value']} "
                  f"gmv {original_gmv:,.0f} → {new_gmv:,.0f} ({shock['multiplier']:.0%})")

    conn.commit()
    return results


def main():
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    print("Resetting shocked tables to clean baseline …")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE gmv_fact_shocked;")
        cur.execute("INSERT INTO gmv_fact_shocked SELECT * FROM gmv_fact;")
        cur.execute("TRUNCATE gmv_total_shocked;")
        cur.execute("INSERT INTO gmv_total_shocked SELECT * FROM gmv_total;")
    conn.commit()

    print("Injecting shocks …")
    results = apply_shocks(conn)

    MANIFEST_PATH.write_text(json.dumps(results, indent=2, default=str))
    print(f"Manifest written to {MANIFEST_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
