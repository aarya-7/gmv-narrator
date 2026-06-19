"""Load Olist CSVs into PostgreSQL raw tables, then build the fact tables."""
import os
import sys
import pathlib
import psycopg2
from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", "/Users/reflex/Desktop/llm o_list"))
SQL_DIR  = pathlib.Path(__file__).parent.parent / "sql"


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", 5432)),
        dbname=os.getenv("PG_DB", "Olist"),
        user=os.getenv("PG_USER", "reflex"),
        password=os.getenv("PG_PASSWORD", "") or None,
    )


CSV_TABLE_MAP = {
    "olist_orders_dataset.csv":               "raw_orders",
    "olist_order_items_dataset.csv":          "raw_order_items",
    "olist_products_dataset.csv":             "raw_products",
    "product_category_name_translation.csv":  "raw_category_translation",
    "olist_customers_dataset.csv":            "raw_customers",
}


def run_sql_file(conn, path):
    sql = path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"  ran {path.name}")


def load_csv(conn, csv_name, table):
    csv_path = DATA_DIR / csv_name
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing: {csv_path}")
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {table} CASCADE;")
        with open(csv_path) as f:
            cur.copy_expert(f"COPY {table} FROM STDIN WITH CSV HEADER NULL ''", f)
    conn.commit()
    print(f"  loaded {csv_name} → {table}")


def main():
    conn = get_conn()
    print("Creating schema …")
    run_sql_file(conn, SQL_DIR / "01_schema.sql")

    print("Loading CSVs …")
    for csv_name, table in CSV_TABLE_MAP.items():
        load_csv(conn, csv_name, table)

    print("Building fact tables …")
    run_sql_file(conn, SQL_DIR / "03_build_fact.sql")

    # seed shocked tables as copies of clean tables
    with conn.cursor() as cur:
        cur.execute("TRUNCATE gmv_fact_shocked;")
        cur.execute("INSERT INTO gmv_fact_shocked SELECT * FROM gmv_fact;")
        cur.execute("TRUNCATE gmv_total_shocked;")
        cur.execute("INSERT INTO gmv_total_shocked SELECT * FROM gmv_total;")
    conn.commit()
    print("Seeded shocked tables (clean copy — run inject_shocks.py next).")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
