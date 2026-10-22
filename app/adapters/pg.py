"""Postgres write connection to veda-pg: used only by ingest jobs (never agents - they read via Zetaris).

    from app.adapters import pg
    with pg.connect() as conn:
        conn.execute("INSERT ...")
"""
import os

import psycopg

HOST = "localhost"
PORT = 5433
DBNAME = "veda"


class PgError(Exception):
    """veda-pg is not configured or not reachable."""


def connect(autocommit=False):
    """Open a write connection as the postgres superuser (VEDA_PG_PASSWORD). Raises PgError."""
    password = os.getenv("VEDA_PG_PASSWORD", "").strip()
    if not password:
        raise PgError("VEDA_PG_PASSWORD is not set")
    try:
        return psycopg.connect(host=HOST, port=PORT, dbname=DBNAME, user="postgres", password=password,
                               autocommit=autocommit, connect_timeout=10)
    except psycopg.OperationalError as e:
        raise PgError(f"cannot reach veda-pg on {HOST}:{PORT} ({type(e).__name__}) - run scripts/setup_pg.py") from e
