import psycopg2
from psycopg2 import sql
from config import load_config

def get_logs_conn(cfg):
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"]
    )

def ensure_solution_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS log_solutions (
            id SERIAL PRIMARY KEY,
            table_name TEXT,
            log_id TEXT,
            solution TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT now()
        )
    """)
    conn.commit()
    cur.close()

