"""Spike 6 — runtime DDL through the API key: create a REST table, re-create (capture 'already exists'),
create/replace a SchemaStore view, then drop. Finally drop all VEDA_SPIKE objects."""
from _common import log, run_sql

S = "s6"
URL = ("https://api.open-meteo.com/v1/forecast?latitude=5.5167&longitude=102.2000"
       "&hourly=precipitation&timezone=Asia%2FKuala_Lumpur&forecast_days=1")
CREATE = f'''CREATE LIGHTNING REST TABLE om_ddl_test FROM VEDA_SPIKE REQUEST(
    endpoint "{URL}", method "get", response_type "json", http_encoding "URLENCODED") HEADER () BODY ()'''

checks = [
    ("create", CREATE),
    ("create_again", CREATE),
    ("query", "SELECT size(hourly.time) AS n FROM veda_spike.om_ddl_test"),
    ("create_container", "CREATE SCHEMASTORE CONTAINER veda_spike_views"),
    ("create_view", "CREATE SCHEMASTORE VIEW ddl_view WITH CONTAINER veda_spike_views AS "
                    "SELECT size(hourly.time) AS n FROM veda_spike.om_ddl_test"),
    ("replace_view", "CREATE OR REPLACE SCHEMASTORE VIEW ddl_view WITH CONTAINER veda_spike_views AS "
                     "SELECT size(hourly.time) * 2 AS n FROM veda_spike.om_ddl_test"),
    ("query_view", "SELECT n FROM veda_spike_views.ddl_view"),
    ("drop_view", "DROP SCHEMASTORE VIEW ddl_view WITH CONTAINER veda_spike_views"),
    ("drop_table", "DROP LIGHTNING DATABASE TABLE VEDA_SPIKE.om_ddl_test"),
    ("drop_again", "DROP LIGHTNING DATABASE TABLE VEDA_SPIKE.om_ddl_test"),
]
results = {}
for name, sql in checks:
    ok, out, secs = run_sql(sql, S)
    results[name] = ok
    print(f"{name:16} ok={ok} {secs}s", out[:3] if ok else out[:250])
log(S, "result", **results)
