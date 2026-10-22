"""Set up VEDA's Postgres store (veda-pg) and register it in Zetaris. Idempotent: safe to re-run.

    python scripts/setup_pg.py

Steps: container running -> on Zetaris network -> read-only role -> schema -> Zetaris datasource
-> register tables -> smoke check every table through run_sql(). Needs .env: VEDA_PG_PASSWORD,
VEDA_PG_RO_PASSWORD, ZETARIS_*. Not used in SAMPLE_MODE.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql as pgsql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import trace  # noqa: E402
from app.adapters import zetaris  # noqa: E402

CONTAINER = "veda-pg"
IMAGE = "postgres:16-alpine"
HOST_PORT = 5433
ZETARIS_NET = "zetaris_default"
DATASOURCE = "veda_pg"
RO_ROLE = "veda_zetaris"
SCHEMA = ROOT / "db" / "schema.sql"
TABLES = ["stations", "river_levels", "places", "historic_peaks", "source_registry"]
AGENT = "Setup"


def docker(*args, env=None):
    """Run a docker command; returns CompletedProcess (never raises)."""
    return subprocess.run(["docker", *args], capture_output=True, text=True, env=env)


def ensure_container():
    """Create veda-pg if missing, start it if stopped. Returns a short description of what happened."""
    state = docker("inspect", "-f", "{{.State.Status}}", CONTAINER)
    if state.returncode != 0:
        env = {**os.environ, "POSTGRES_PASSWORD": os.environ["VEDA_PG_PASSWORD"]}  # passed by env, not argv
        r = docker("run", "-d", "--name", CONTAINER, "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_DB=veda",
                   "-p", f"{HOST_PORT}:5432", "-v", "veda-pg-data:/var/lib/postgresql/data",
                   "--restart", "unless-stopped", IMAGE, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"docker run failed: {r.stderr.strip()[:200]}")
        return "created"
    if state.stdout.strip() != "running":
        docker("start", CONTAINER)
        return "started"
    return "already running"


def ensure_network():
    """Join veda-pg to the Zetaris network so Zetaris reaches it at veda-pg:5432."""
    nets = docker("inspect", "-f", "{{json .NetworkSettings.Networks}}", CONTAINER).stdout
    if ZETARIS_NET in nets:
        return "already on network"
    r = docker("network", "connect", ZETARIS_NET, CONTAINER)
    if r.returncode != 0:
        raise RuntimeError(f"docker network connect failed: {r.stderr.strip()[:200]}")
    return "joined network"


def connect(wait_s=30):
    """Connect as the postgres superuser, waiting for the server to accept connections."""
    deadline = time.time() + wait_s
    while True:
        try:
            return psycopg.connect(host="localhost", port=HOST_PORT, dbname="veda", user="postgres",
                                   password=os.environ["VEDA_PG_PASSWORD"], autocommit=True)
        except psycopg.OperationalError:
            if time.time() > deadline:
                raise
            time.sleep(1)


def schema_statements():
    """Statements from db/schema.sql (comments removed, split on ';')."""
    text = "\n".join(line.split("--")[0] for line in SCHEMA.read_text(encoding="utf-8").splitlines())
    return [s.strip() for s in text.split(";") if s.strip()]


def apply_schema(conn):
    """Read-only role with its own password, then the schema. Returns the tables now present."""
    ro_pw = os.environ["VEDA_PG_RO_PASSWORD"]
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (RO_ROLE,)).fetchone():
        conn.execute(pgsql.SQL("CREATE ROLE {} LOGIN").format(pgsql.Identifier(RO_ROLE)))
    conn.execute(pgsql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(pgsql.Identifier(RO_ROLE),
                                                                          pgsql.Literal(ro_pw)))
    for stmt in schema_statements():
        conn.execute(stmt)
    return [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")]


def register_in_zetaris():
    """CREATE DATASOURCE (once) + REGISTER DATASOURCE TABLES (every run, picks up new tables)."""
    created = zetaris.run_ddl(
        f'CREATE DATASOURCE {DATASOURCE} DESCRIBE BY "VEDA_operational_store" OPTIONS ('
        f'jdbcdriver "org.postgresql.Driver", jdbcurl "jdbc:postgresql://{CONTAINER}:5432/veda", '
        f'username "{RO_ROLE}", password "{os.environ["VEDA_PG_RO_PASSWORD"]}", schema "public", fetchsize "1000")',
        agent=AGENT, purpose=f"register datasource {DATASOURCE} -> {CONTAINER}:5432", setup=True)
    zetaris.run_ddl(f"REGISTER DATASOURCE TABLES FROM {DATASOURCE}", agent=AGENT,
                    purpose=f"register tables of {DATASOURCE}")
    return "created" if created else "already registered"


def smoke_check():
    """COUNT(*) on every table through Zetaris. Returns {table: rows}."""
    counts = {}
    for t in TABLES:
        r = zetaris.run_sql(f"SELECT COUNT(*) AS n FROM {DATASOURCE}.{t}", agent=AGENT,
                            purpose=f"smoke check {DATASOURCE}.{t}")
        counts[t] = r.rows[0][0]
    return counts


def main():
    """Run every setup step, tracing each one."""
    load_dotenv(ROOT / ".env")
    if os.getenv("SAMPLE_MODE", "false").lower() == "true":
        print("SAMPLE_MODE is on - Postgres setup is for live mode only.")
        return 1
    trace.start_run("setup veda-pg + Zetaris datasource")
    try:
        trace.step(AGENT, "docker.container", output_summary=f"{CONTAINER}: {ensure_container()}")
        trace.step(AGENT, "docker.network", output_summary=f"{CONTAINER}: {ensure_network()}")
        with connect() as conn:
            tables = apply_schema(conn)
        trace.step(AGENT, "pg.schema", output_summary=f"tables: {', '.join(tables)}",
                   decision=f"role {RO_ROLE} has SELECT only")
        trace.step(AGENT, "zetaris.datasource", output_summary=f"{DATASOURCE}: {register_in_zetaris()}")
        counts = smoke_check()
        trace.step(AGENT, "smoke_check", output_summary=", ".join(f"{t}={n}" for t, n in counts.items()),
                   decision="Every table answers through Zetaris")
    except (RuntimeError, psycopg.Error, zetaris.ZetarisError, KeyError) as e:
        trace.end_run("failed", f"{type(e).__name__}: {e}")
        print(f"SETUP FAILED: {type(e).__name__}: {e}")
        return 1
    trace.end_run("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
