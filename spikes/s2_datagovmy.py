"""Spike 2 — data.gov.my x3 as Zetaris REST tables (meta=true), stale flood-warning check, 429 check."""
import json

from _common import ROOT, log, run_sql

S = "s2"
BASE = "https://api.data.gov.my"
TABLES = {
    # trailing slash matters: without it data.gov.my answers 301
    "mygov_forecast": f"{BASE}/weather/forecast/?meta=true&limit=5000",
    "mygov_warning": f"{BASE}/weather/warning/?meta=true&limit=200",
    "mygov_flood": f"{BASE}/flood-warning/?meta=true&ifilter=kelantan@state&limit=500",
}

for name, url in TABLES.items():
    ok, out, secs = run_sql(f'''CREATE LIGHTNING REST TABLE {name} FROM VEDA_SPIKE REQUEST(
        endpoint "{url}", method "get", response_type "json", http_encoding "URLENCODED") HEADER () BODY ()''', S)
    print("create", name, ok, secs, "" if ok else out[:200])

queries = {
    "forecast_kelantan": """SELECT f.location.location_name, f.date, f.summary_forecast, f.min_temp, f.max_temp
        FROM veda_spike.mygov_forecast LATERAL VIEW explode(data) AS f
        WHERE f.location.location_name IN ('Kota Bharu','Pasir Mas','Tumpat','Kuala Krai','Tanah Merah')
        ORDER BY f.date""",
    "warning": """SELECT w.warning_issue.issued, w.warning_issue.title_en, w.valid_from, w.valid_to
        FROM veda_spike.mygov_warning LATERAL VIEW explode(data) AS w""",
    "flood_kelantan_age": """SELECT COUNT(*) AS n, MAX(s.water_level_update_datetime) AS newest,
        MIN(s.water_level_update_datetime) AS oldest
        FROM veda_spike.mygov_flood LATERAL VIEW explode(data) AS s""",
    "flood_kelantan_stations": """SELECT s.station_id, s.station_code, s.station_name, s.district,
        s.water_level_danger_level, s.water_level_update_datetime
        FROM veda_spike.mygov_flood LATERAL VIEW explode(data) AS s""",
}
results = {}
for name, q in queries.items():
    ok, rows, secs = run_sql(q, S)
    results[name] = rows if ok else None
    print(f"\n{name}: ok={ok} {secs}s rows={len(rows) if ok else '-'}")
    print(rows[:5] if ok else rows[:300])

# station list is reused by spike 5 (JPS id match)
if results["flood_kelantan_stations"]:
    out = ROOT / "data" / "cache" / "spike_mygov_flood_stations.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results["flood_kelantan_stations"], ensure_ascii=False, indent=1), encoding="utf-8")

# 429 check: 6 uncached back-to-back reads of the same REST table (API limit is ~4 req/min)
burst = []
for _ in range(6):
    ok, rows, secs = run_sql(queries["warning"], S)
    burst.append({"ok": ok, "secs": secs, "err": None if ok else rows[:120]})
print("\nburst:", burst)

log(S, "result", forecast_rows=len(results["forecast_kelantan"] or []), warning_rows=len(results["warning"] or []),
    flood_age=results["flood_kelantan_age"], burst_ok=sum(b["ok"] for b in burst), burst_n=len(burst))
