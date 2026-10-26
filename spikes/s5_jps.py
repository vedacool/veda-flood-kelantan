"""Spike 5 — JPS Public Infobanjir (Kelantan): fetch ONCE, save raw snapshot, parse data-th table,
find our 5 stations, and check station-id match against data.gov.my /flood-warning (from spike 2)."""
import json
import re
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from _common import ROOT, log, short

S = "s5"
URL = ("https://publicinfobanjir.water.gov.my/aras-air/data-paras-air/aras-air-data/"
       "?state=KEL&district=ALL&station=ALL&lang=en")
UA = "VEDA-hackathon/0.1 (+https://github.com/vedacool/veda-kelantan; flood-risk research, low-rate, cached)"
SNAP_DIR = ROOT / "data" / "snapshots" / "jps"
OURS = {  # BUILD_BRIEF §2 coverage, matched by name fragments
    "Golok @ Rantau Panjang": ("golok", "rantau panjang"),
    "Kelantan @ Tambatan Diraja": ("kelantan", "tambatan"),
    "Kelantan @ Jambatan Guillemard": ("kelantan", "guillemard"),
    "Kelantan @ Tangga Krai": ("kelantan", "tangga krai"),
    "Galas @ Dabong": ("galas", "dabong"),
}

# reuse a snapshot from the last 15 minutes instead of re-fetching (scrape rule: <= 1x / 15 min)
recent = sorted(SNAP_DIR.glob("kel-*.html"))
if recent and time.time() - recent[-1].stat().st_mtime < 900 and "--refetch" not in sys.argv:
    snap, html = recent[-1], recent[-1].read_text(encoding="utf-8")
    print("reusing snapshot", snap.name)
else:
    t0 = time.perf_counter()
    r = requests.get(URL, headers={"User-Agent": UA}, timeout=60)
    secs = round(time.perf_counter() - t0, 2)
    log(S, "http.get", url=URL, http=r.status_code, bytes=len(r.content), secs=secs)
    print("fetch", r.status_code, len(r.content), "bytes", secs, "s")
    r.raise_for_status()
    html = r.text
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snap = SNAP_DIR / f"kel-{datetime.now().strftime('%Y%m%d-%H%M')}.html"
    snap.write_text(html, encoding="utf-8")

soup = BeautifulSoup(html, "html.parser")
rows = []
for tr in soup.find_all("tr"):
    cells = tr.find_all("td", attrs={"data-th": True})
    if cells:
        rows.append({c["data-th"].strip(): " ".join(c.get_text(" ").split()) for c in cells})
print("rows parsed:", len(rows))
if rows:
    print("columns:", list(rows[0].keys()))
    print("first row:", rows[0])


def col(row, *keys):
    for k in row:
        if any(key in k.lower() for key in keys):
            return row[k]
    return ""


found = {}
for label, (river, place) in OURS.items():
    for row in rows:
        name = (col(row, "station name") + " " + col(row, "river")).lower()
        if river in name and place in name:
            found[label] = row
            break
print("\nour 5 stations:")
for label in OURS:
    print(" ", "OK " if label in found else "MISSING", label, "->", short(found.get(label, ""), 220))

# station-id match vs data.gov.my /flood-warning (Kelantan rows saved by spike 2)
mygov_path = ROOT / "data" / "cache" / "spike_mygov_flood_stations.json"
match_report = None
if mygov_path.exists() and rows:
    mygov = json.loads(mygov_path.read_text(encoding="utf-8"))  # [station_id, station_code, name, district, danger, dt]
    jps_ids = {col(r, "station id").strip().upper() for r in rows} - {""}

    def norm(x):
        return re.sub(r"[^A-Z0-9]", "", (x or "").upper())

    jps_norm = {norm(i) for i in jps_ids}
    exact = [m for m in mygov if (m[0] or "").upper() in jps_ids]
    by_code = [m for m in mygov if norm(m[1]) in jps_norm or any(norm(m[1]) and norm(m[1]) in j for j in jps_norm)]
    by_id_parts = [m for m in mygov if any(p and p in jps_norm for p in (norm(x) for x in (m[0] or "").split("_")))]
    any_match = {m[0] for m in exact + by_code + by_id_parts}
    match_report = {"mygov_kelantan": len(mygov), "jps_rows": len(rows), "exact_station_id": len(exact),
                    "via_station_code": len(by_code), "via_id_parts": len(by_id_parts),
                    "any": len(any_match), "rate_any": round(len(any_match) / max(len(mygov), 1), 2)}
    print("\nid match:", match_report)
    print("sample JPS ids:", sorted(jps_ids)[:8])
    print("sample mygov ids/codes:", [(m[0], m[1]) for m in mygov[:8]])

log(S, "result", snapshot=snap.name, rows=len(rows), ours_found=sorted(found), ours_missing=sorted(set(OURS) - set(found)),
    id_match=match_report)
