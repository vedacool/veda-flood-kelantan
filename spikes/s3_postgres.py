"""Spike 3 — Postgres (veda-pg) as a Zetaris datasource. Which address can Zetaris use to reach it?

A) host.docker.internal:5433 (veda-pg NOT on the Zetaris network)
B) veda-pg:5432 after `docker network connect zetaris_default veda-pg`
Python writes to Postgres directly; the row is read back through Zetaris.
"""
import os
import subprocess
from datetime import datetime, timezone

import psycopg

from _common import log, run_sql

S = "s3"
PW = os.environ["VEDA_PG_PASSWORD"]
NET = "zetaris_default"

# 1. write a row directly (Python -> Postgres), plus a read-only role for Zetaris
with psycopg.connect(host="localhost", port=5433, dbname="veda", user="postgres", password=PW, autocommit=True) as c:
    c.execute("CREATE TABLE IF NOT EXISTS spike_check (id serial PRIMARY KEY, note text, written_at timestamptz)")
    c.execute("INSERT INTO spike_check (note, written_at) VALUES (%s, %s)", ("b64-spike", datetime.now(timezone.utc)))
    if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='veda_zetaris'").fetchone():
        c.execute(psycopg.sql.SQL("CREATE ROLE veda_zetaris LOGIN PASSWORD {}").format(psycopg.sql.Literal(PW)))
    c.execute("GRANT USAGE ON SCHEMA public TO veda_zetaris")
    c.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO veda_zetaris")
    c.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO veda_zetaris")
    n = c.execute("SELECT count(*) FROM spike_check").fetchone()[0]
print("direct write ok, rows in spike_check:", n)
log(S, "pg.direct_write", ok=True, rows=n)


def try_datasource(ds, host_port):
    ok, out, secs = run_sql(f'''CREATE DATASOURCE {ds} DESCRIBE BY "B-64_spike" OPTIONS (
        jdbcdriver "org.postgresql.Driver", jdbcurl "jdbc:postgresql://{host_port}/veda",
        username "veda_zetaris", password "{PW}", schema "public", fetchsize "1000")''', S)
    print(f"[{ds}] create datasource ({host_port}):", ok, secs, "" if ok else out[:300])
    ok_r, out_r, secs = run_sql(f"REGISTER DATASOURCE TABLES FROM {ds}", S)
    print(f"[{ds}] register tables:", ok_r, secs, "" if ok_r else out_r[:300])
    ok_q, rows, secs = run_sql(f"SELECT id, note, written_at FROM {ds}.spike_check ORDER BY id DESC", S, limit=5)
    print(f"[{ds}] read back via Zetaris:", ok_q, secs, rows[:3] if ok_q else rows[:300])
    log(S, "result", datasource=ds, address=host_port, create=ok, register=ok_r, read=ok_q)
    return ok_q


a = try_datasource("veda_pg_host", "host.docker.internal:5433")

nets = subprocess.run(["docker", "inspect", "-f", "{{json .NetworkSettings.Networks}}", "veda-pg"],
                      capture_output=True, text=True).stdout
if NET not in nets:
    r = subprocess.run(["docker", "network", "connect", NET, "veda-pg"], capture_output=True, text=True)
    print("docker network connect:", r.returncode, r.stderr.strip())
b = try_datasource("veda_pg_net", "veda-pg:5432")

print(f"\nA host.docker.internal:5433 -> {'PASS' if a else 'FAIL'}   B veda-pg:5432 on {NET} -> {'PASS' if b else 'FAIL'}")
