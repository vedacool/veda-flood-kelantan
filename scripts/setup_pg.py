"""Set up VEDA's Postgres store (veda-pg) and register it in Zetaris. Idempotent: safe to re-run.

    python scripts/setup_pg.py

Steps: container running on 127.0.0.1 only -> on Zetaris network -> roles (read-only for Zetaris, writer for
ingest) -> schema -> constraints -> Zetaris datasource -> register tables -> smoke check every table through
run_sql(). Needs .env: VEDA_PG_PASSWORD, VEDA_PG_RO_PASSWORD, VEDA_PG_WRITER_PASSWORD, ZETARIS_*.
Not used in SAMPLE_MODE.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql as pgsql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import config, trace  # noqa: E402
from app.adapters import zetaris  # noqa: E402

CONTAINER = "veda-pg"
IMAGE = "postgres:16-alpine"
HOST_PORT = config.PG_PORT
BIND = f"127.0.0.1:{HOST_PORT}:5432"     # never all interfaces: the superuser must not be reachable from the LAN
ZETARIS_NET = "zetaris_default"
DATASOURCE = "veda_pg"
RO_ROLE = "veda_zetaris"                  # Zetaris reads as this role (SELECT only)
WRITER_ROLE = "veda_writer"               # ingest jobs write as this role (INSERT/UPDATE on ingest tables only)
WRITER_GRANTS = {"stations": "SELECT, INSERT, UPDATE", "river_levels": "SELECT, INSERT, UPDATE",
                 "station_links": "SELECT, INSERT, UPDATE, DELETE",   # seed_stations replaces all links each run
                 "historic_peaks": "SELECT, INSERT, UPDATE, DELETE",  # seed_peaks replaces all peaks each run
                 "rain_points": "SELECT, INSERT, UPDATE, DELETE",     # setup_wx replaces all points each run
                 "places": "SELECT, INSERT, UPDATE, DELETE",          # seed_places replaces the gazetteer each run
                 "place_aliases": "SELECT, INSERT, UPDATE, DELETE",
                 "place_gauges": "SELECT, INSERT, UPDATE, DELETE"}
WRITER_TABLES = list(WRITER_GRANTS)
SCHEMA = ROOT / "db" / "schema.sql"
TABLES = ["stations", "river_levels", "places", "historic_peaks", "source_registry", "station_links", "rain_points",
          "place_aliases", "place_gauges"]
PASSWORD_OK = re.compile(r"^[A-Za-z0-9_-]{16,}$")  # role passwords go into DDL / JDBC options: keep them plain
DOCKER_TIMEOUT_S = 60
AGENT = "Setup"

# Constraints added to existing databases too (CREATE TABLE IF NOT EXISTS never changes an existing table).
# (name, table, definition) - added only when a constraint with that name does not exist yet.
CONSTRAINTS = [
    ("river_levels_station_fk", "river_levels",
     "FOREIGN KEY (station_key) REFERENCES stations (station_key)"),
    ("places_station_fk", "places",
     "FOREIGN KEY (nearest_station_key) REFERENCES stations (station_key) ON DELETE SET NULL"),
    ("river_levels_level_range", "river_levels", "CHECK (level_m IS NULL OR level_m BETWEEN -50 AND 1000)"),
    ("river_levels_not_future", "river_levels", "CHECK (observed_at <= scraped_at + interval '1 day')"),
    ("historic_peaks_station_fk", "historic_peaks", "FOREIGN KEY (station_key) REFERENCES stations (station_key)"),
    ("historic_peaks_source_type", "historic_peaks",
     "CHECK (source_type IS NULL OR source_type IN ('official', 'news'))"),
    ("historic_peaks_range", "historic_peaks", "CHECK (peak_m BETWEEN -50 AND 1000)"),
    ("stations_threshold_range", "stations",
     "CHECK ((normal_m IS NULL OR normal_m BETWEEN -50 AND 1000) AND (alert_m IS NULL OR alert_m BETWEEN -50 AND 1000)"
     " AND (warning_m IS NULL OR warning_m BETWEEN -50 AND 1000) AND (danger_m IS NULL OR danger_m BETWEEN -50 AND 1000))"),
]


def docker(*args, env=None):
    """Run a docker command with a timeout; returns CompletedProcess. Raises RuntimeError if Docker hangs."""
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, env=env, timeout=DOCKER_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"docker {args[0]} did not answer within {DOCKER_TIMEOUT_S}s - is Docker running?") from e


def _run_container():
    env = {**os.environ, "POSTGRES_PASSWORD": os.environ["VEDA_PG_PASSWORD"]}  # passed by env, not argv
    r = docker("run", "-d", "--name", CONTAINER, "-e", "POSTGRES_PASSWORD", "-e", "POSTGRES_DB=veda",
               "-p", BIND, "-v", "veda-pg-data:/var/lib/postgresql/data", "--restart", "unless-stopped", IMAGE, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"docker run failed: {r.stderr.strip()[:200]}")


def ensure_container():
    """Create veda-pg if missing (bound to 127.0.0.1), re-create it if it is published on all interfaces
    (data stays in the veda-pg-data volume), start it if stopped. Returns what happened."""
    state = docker("inspect", "-f", "{{.State.Status}}", CONTAINER)
    if state.returncode != 0:
        _run_container()
        return "created (127.0.0.1 only)"
    ports = docker("inspect", "-f", "{{json .HostConfig.PortBindings}}", CONTAINER).stdout
    if '"HostIp":"127.0.0.1"' not in ports.replace(" ", ""):
        for args in (("stop", CONTAINER), ("rm", CONTAINER)):
            r = docker(*args)
            if r.returncode != 0:
                raise RuntimeError(f"docker {args[0]} failed: {r.stderr.strip()[:200]}")
        _run_container()
        return "re-created bound to 127.0.0.1 (data kept in volume veda-pg-data)"
    if state.stdout.strip() != "running":
        r = docker("start", CONTAINER)
        if r.returncode != 0:
            raise RuntimeError(f"docker start failed: {r.stderr.strip()[:200]}")
        return "started"
    return "already running (127.0.0.1 only)"


def ensure_network():
    """Join veda-pg to the Zetaris network so Zetaris reaches it at veda-pg:5432."""
    nets = docker("inspect", "-f", "{{json .NetworkSettings.Networks}}", CONTAINER).stdout
    if ZETARIS_NET in nets:
        return "already on network"
    r = docker("network", "connect", ZETARIS_NET, CONTAINER)
    if r.returncode != 0:
        raise RuntimeError(f"docker network connect failed: {r.stderr.strip()[:200]}")
    return "joined network"


def check_passwords():
    """Role passwords must exist and be plain [A-Za-z0-9_-]{16,} (they are placed inside DDL options)."""
    for key in ("VEDA_PG_PASSWORD", "VEDA_PG_RO_PASSWORD", "VEDA_PG_WRITER_PASSWORD"):
        value = os.getenv(key, "").strip()
        if not value:
            raise RuntimeError(f"{key} is not set in .env")
        if key != "VEDA_PG_PASSWORD" and not PASSWORD_OK.match(value):
            raise RuntimeError(f"{key} must be 16+ letters/digits/_/- only")


def connect(wait_s=30):
    """Connect as the postgres superuser, waiting (bounded) for the server to accept connections."""
    deadline = time.time() + wait_s
    while True:
        try:
            return psycopg.connect(host=config.PG_HOST, port=HOST_PORT, dbname=config.PG_DB, user="postgres",
                                   password=os.environ["VEDA_PG_PASSWORD"], autocommit=True, connect_timeout=5)
        except psycopg.OperationalError:
            if time.time() > deadline:
                raise
            time.sleep(1)


def schema_statements():
    """Statements from db/schema.sql: '--' comments removed and split on ';' - both only OUTSIDE quotes."""
    text, out, cur, i, quote = SCHEMA.read_text(encoding="utf-8"), [], [], 0, None
    while i < len(text):
        c = text[i]
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
            cur.append(c)
        elif text.startswith("--", i):
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        elif c == ";":
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur).strip())
    return [s for s in out if s]


def _role(conn, name, password_env):
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone():
        conn.execute(pgsql.SQL("CREATE ROLE {} LOGIN").format(pgsql.Identifier(name)))
    conn.execute(pgsql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
        pgsql.Identifier(name), pgsql.Literal(os.environ[password_env].strip())))


def apply_schema(conn):
    """Roles (each with its own password), schema, constraints, writer grants. Returns (tables, constraints added)."""
    _role(conn, RO_ROLE, "VEDA_PG_RO_PASSWORD")
    _role(conn, WRITER_ROLE, "VEDA_PG_WRITER_PASSWORD")
    for stmt in schema_statements():
        conn.execute(stmt)
    added = []
    for name, table, definition in CONSTRAINTS:
        if not conn.execute("SELECT 1 FROM pg_constraint WHERE conname = %s", (name,)).fetchone():
            conn.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} {definition}")
            added.append(name)
    conn.execute(pgsql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(pgsql.Identifier(WRITER_ROLE)))
    for t, privileges in WRITER_GRANTS.items():
        conn.execute(pgsql.SQL("GRANT " + privileges + " ON {} TO {}").format(
            pgsql.Identifier(t), pgsql.Identifier(WRITER_ROLE)))
    tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")]
    return tables, added


def register_in_zetaris():
    """CREATE DATASOURCE (once) + REGISTER DATASOURCE TABLES (every run, picks up new tables)."""
    created = zetaris.run_ddl(
        f'CREATE DATASOURCE {DATASOURCE} DESCRIBE BY "VEDA_operational_store" OPTIONS ('
        f'jdbcdriver "org.postgresql.Driver", jdbcurl "jdbc:postgresql://{CONTAINER}:5432/veda", '
        f'username "{RO_ROLE}", password "{os.environ["VEDA_PG_RO_PASSWORD"].strip()}", schema "public", '
        f'fetchsize "1000")',
        agent=AGENT, purpose=f"register datasource {DATASOURCE} -> {CONTAINER}:5432", setup=True)
    zetaris.run_ddl(f"REGISTER DATASOURCE TABLES FROM {DATASOURCE}", agent=AGENT,
                    purpose=f"register tables of {DATASOURCE}", setup=True)
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
    if config.sample_mode():
        print("SAMPLE_MODE is on - Postgres setup is for live mode only.")
        return 1
    trace.start_run("setup veda-pg + Zetaris datasource")
    try:
        check_passwords()
        trace.step(AGENT, "docker.container", output_summary=f"{CONTAINER}: {ensure_container()}")
        trace.step(AGENT, "docker.network", output_summary=f"{CONTAINER}: {ensure_network()}")
        with connect() as conn:
            tables, added = apply_schema(conn)
        trace.step(AGENT, "pg.schema", output_summary=f"tables: {', '.join(tables)}; constraints added: "
                   f"{', '.join(added) or 'none (all present)'}",
                   decision=f"{RO_ROLE} SELECT only; {WRITER_ROLE} writes {', '.join(WRITER_TABLES)}")
        trace.step(AGENT, "zetaris.datasource", output_summary=f"{DATASOURCE}: {register_in_zetaris()}")
        counts = smoke_check()
        trace.step(AGENT, "smoke_check", output_summary=", ".join(f"{t}={n}" for t, n in counts.items()),
                   decision="Every table answers through Zetaris")
    except (RuntimeError, psycopg.Error, zetaris.ZetarisError, KeyError) as e:
        trace.end_run("failed", f"{type(e).__name__}: {e}")
        print(f"SETUP FAILED: {type(e).__name__}: {trace.redact(str(e))}")
        return 1
    trace.end_run("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
