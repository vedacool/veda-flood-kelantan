"""Postgres write connection to veda-pg: used only by ingest jobs (never agents - they read via Zetaris).

Connects as the least-privilege role `veda_writer` (INSERT/UPDATE on the ingest tables only), not the superuser.

    from app.adapters import pg
    with pg.transaction() as conn:          # commits on success, rolls back on error
        conn.execute("INSERT ...")
"""
import os
from contextlib import contextmanager

import psycopg

from app import config

HOST = config.PG_HOST
PORT = config.PG_PORT
DBNAME = config.PG_DB
WRITER_ROLE = "veda_writer"
STATEMENT_TIMEOUT_MS = 30_000


class PgError(Exception):
    """veda-pg is not configured, not reachable, or a database statement failed."""


def check_config():
    """Raise PgError if the writer password is missing (check BEFORE doing any expensive work)."""
    if not os.getenv("VEDA_PG_WRITER_PASSWORD", "").strip():
        raise PgError("VEDA_PG_WRITER_PASSWORD is not set - run scripts/setup_pg.py")


def connect(autocommit=False):
    """Open a write connection as veda_writer. Raises PgError."""
    check_config()
    try:
        return psycopg.connect(host=HOST, port=PORT, dbname=DBNAME, user=WRITER_ROLE,
                               password=os.environ["VEDA_PG_WRITER_PASSWORD"].strip(), autocommit=autocommit,
                               connect_timeout=10, options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}")
    except psycopg.Error as e:
        raise PgError(f"cannot reach veda-pg on {HOST}:{PORT} as {WRITER_ROLE} ({type(e).__name__}) "
                      f"- run scripts/setup_pg.py") from e


@contextmanager
def transaction():
    """One transaction: commit on success, roll back on any error. Every database error surfaces as PgError."""
    conn = connect()
    try:
        with conn:                      # psycopg: commit on success / rollback on exception, then close
            yield conn
    except psycopg.Error as e:
        raise PgError(f"database error ({type(e).__name__}): {str(e).splitlines()[0][:200]}") from e
