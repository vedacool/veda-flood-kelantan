"""Spike 1 — Open-Meteo as a Zetaris Lightning REST table; does CACHE TABLE help and persist?"""
from _common import log, run_sql

S = "s1"
URL = ("https://api.open-meteo.com/v1/forecast?latitude=6.1254&longitude=102.2381"
       "&hourly=precipitation,precipitation_probability&timezone=Asia%2FKuala_Lumpur&forecast_days=3")

steps = [
    ("create_db", 'CREATE LIGHTNING DATABASE VEDA_SPIKE DESCRIBE BY "B-64_spike_tests"'),
    ("create_table", f'''CREATE LIGHTNING REST TABLE om_kota_bharu FROM VEDA_SPIKE REQUEST(
        endpoint "{URL}", method "get", response_type "json", http_encoding "URLENCODED") HEADER () BODY ()'''),
]
for name, sql in steps:
    ok, out, secs = run_sql(sql, S)
    print(name, ok, secs, "" if ok else out[:200])

Q = ("SELECT ts, CAST(hourly.precipitation[i] AS DOUBLE) AS precip_mm "
     "FROM veda_spike.om_kota_bharu LATERAL VIEW posexplode(hourly.time) AS i, ts")

ok, rows, t_uncached = run_sql(Q, S)
print("uncached", ok, t_uncached, len(rows) if ok else rows[:300])
if ok:
    print("sample rows", rows[:3])
ok2, rows2, t_uncached2 = run_sql(Q, S)
print("uncached again", ok2, t_uncached2)

okc, outc, t_cache = run_sql("CACHE TABLE veda_spike.om_kota_bharu", S)
print("cache table", okc, t_cache, "" if okc else outc[:300])

timings = []
for n in range(3):  # each is a separate HTTP call to the Zetaris API
    okn, _, t = run_sql(Q, S)
    timings.append((okn, t))
print("cached runs (separate API calls)", timings)

log(S, "result", uncached_s=[t_uncached, t_uncached2], cache_ok=okc, cached_s=[t for _, t in timings],
    rows=len(rows) if ok else 0)
