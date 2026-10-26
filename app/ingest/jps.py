"""JPS river-level collector: JPS Public Infobanjir (Kelantan) -> veda-pg `stations` + `river_levels`.

fetch (<= 1x per 15 min, snapshot saved) -> parse (+ health check) -> store (idempotent).
Agents never call this; they read the stored rows through Zetaris (veda_pg.river_levels).

    python -m app.ingest.jps                     # one cycle (reuses a snapshot < 15 min old)
    python -m app.ingest.jps --from-file F.html  # ingest a saved snapshot (the only mode allowed in SAMPLE_MODE)
    python -m app.ingest.jps --loop              # one cycle every 15 min until Ctrl+C; survives any failed cycle
"""
import argparse
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from app import config, trace
from app.adapters import pg

URL = ("https://publicinfobanjir.water.gov.my/aras-air/data-paras-air/aras-air-data/"
       "?state=KEL&district=ALL&station=ALL&lang=en")
USER_AGENT = "VEDA-hackathon/0.1 (+https://github.com/vedacool/veda-kelantan; flood-risk research, low-rate, cached)"
CACHE_DIR = trace.ROOT / "data" / "cache" / "jps"
MIN_INTERVAL_S = 15 * 60          # scrape rule: at most once per 15 minutes
TIMEOUT_S = 60
MAX_PAGE_BYTES = 2_000_000        # the real page is ~28 KB; anything huge is not the JPS table
MYT = config.MYT                  # JPS times are Malaysia time (no DST)
LEVEL_RANGE = (-50.0, 1000.0)     # plausible metres for levels and thresholds (Kelantan gauges: ~0-700 m datum)
STATION_KEY = re.compile(r"^[A-Za-z0-9_]{1,40}$")
AGENT = "JPSCollector"
REQUIRED_COLUMNS = {"Station ID", "Station Name", "District", "Sub River Basin (mm)", "Last Update", "wl",
                    "Normal", "Alert", "Warning", "Danger"}
_now = time.time                   # patched in tests


class JpsParseError(Exception):
    """The JPS page no longer looks like we expect (layout change, empty table, duplicate ids, too big)."""


class JpsConfigError(Exception):
    """The collector may not run like this (e.g. a live fetch in SAMPLE_MODE)."""


@dataclass
class Reading:
    """One parsed JPS row: the station plus its latest level."""
    station_key: str              # JPS graph-link id, e.g. '_DKBR0007' (never blank; matches data.gov.my for 24/36)
    jps_id: str | None            # visible 'Station ID' column, e.g. '0730671WL' (blank for 8/36)
    name: str
    name_norm: str
    district: str | None
    river: str | None
    observed_at: datetime | None  # UTC
    level_m: float | None
    normal_m: float | None
    alert_m: float | None
    warning_m: float | None
    danger_m: float | None


def normalize_name(name):
    """Lower-case, drop '(F1)'-style tags and punctuation, collapse spaces."""
    text = re.sub(r"\(.*?\)", " ", name.lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def to_number(text):
    """'7.47' -> 7.47. Missing, ambiguous or impossible values -> None (never 0, never a guess):
    '-', '', 'N/A', 'nan', 'inf', 9999/-9999-style sentinels, out-of-range metres, and decimal commas ('7,47')."""
    t = (text or "").strip().replace("−", "-")          # unicode minus
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", t):        # true thousands separators only
        t = t.replace(",", "")
    elif "," in t:
        return None                                            # '7,47' could be 7.47 or 747 - refuse to guess
    try:
        value = float(t)
    except ValueError:
        return None
    if not math.isfinite(value) or abs(value) >= 9999 or not LEVEL_RANGE[0] <= value <= LEVEL_RANGE[1]:
        return None
    return value


def to_utc(text):
    """'22/10/2026 10:30' (MYT) -> aware UTC datetime; unparseable -> None."""
    try:
        return datetime.strptime((text or "").strip(), "%d/%m/%Y %H:%M").replace(tzinfo=MYT).astimezone(timezone.utc)
    except ValueError:
        return None


def parse(html):
    """Parse the JPS table into Readings. Rows with a malformed station id are skipped (counted in
    parse.rejected). Raises JpsParseError if the page shape is wrong."""
    soup = BeautifulSoup(html, "html.parser")
    readings, rejected = [], 0
    for tr in soup.find_all("tr"):
        cells = {td["data-th"].strip(): td for td in tr.find_all("td", attrs={"data-th": True})}
        if not cells:
            continue
        missing = REQUIRED_COLUMNS - cells.keys()
        if missing:
            raise JpsParseError(f"JPS table is missing columns: {sorted(missing)}")
        link = tr.find("a", href=re.compile(r"stationid="))
        if link is None:
            raise JpsParseError("JPS row without a graph link (station id)")
        key = link["href"].split("stationid=", 1)[1].split("&", 1)[0].strip()
        if not STATION_KEY.match(key):
            rejected += 1
            continue
        text = {k: " ".join(td.get_text(" ").split()) for k, td in cells.items()}
        name = text["Station Name"]
        readings.append(Reading(
            station_key=key, jps_id=text["Station ID"] or None, name=name, name_norm=normalize_name(name),
            district=text["District"] or None, river=text["Sub River Basin (mm)"] or None,
            observed_at=to_utc(text["Last Update"]), level_m=to_number(text["wl"]),
            normal_m=to_number(text["Normal"]), alert_m=to_number(text["Alert"]),
            warning_m=to_number(text["Warning"]), danger_m=to_number(text["Danger"])))
    if not readings:
        raise JpsParseError("no valid station rows found on the JPS page")
    keys = [r.station_key for r in readings]
    if len(set(keys)) != len(keys):
        raise JpsParseError("duplicate station ids on the JPS page")
    parse.rejected = rejected
    return readings


parse.rejected = 0


def newest_snapshot():
    """Most recent cached snapshot path, or None."""
    files = sorted(CACHE_DIR.glob("kel-*.html"), key=lambda p: p.stat().st_mtime) if CACHE_DIR.exists() else []
    return files[-1] if files else None


def _download():
    """One live GET, size-capped. Returns (text, status, bytes)."""
    with requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S, stream=True) as r:
        r.raise_for_status()
        body = bytearray()
        for chunk in r.iter_content(64 * 1024):
            body += chunk
            if len(body) > MAX_PAGE_BYTES:
                raise JpsParseError(f"JPS page larger than {MAX_PAGE_BYTES} bytes - not the expected table")
        return bytes(body).decode(r.encoding or "utf-8", errors="replace"), r.status_code, len(body)


def fetch():
    """Return (html, source, path). Reuses a snapshot < 15 min old, else one live GET saved to the cache."""
    recent = newest_snapshot()
    if recent:
        age = _now() - recent.stat().st_mtime
        if 0 <= age < MIN_INTERVAL_S:                 # a future mtime (clock skew) counts as stale, not fresh
            trace.step(AGENT, "jps.fetch", output_summary=f"reused {recent.name} ({int(age // 60)} min old)",
                       source="jps-cache", decision="Last fetch < 15 min ago - not calling JPS again")
            return recent.read_text(encoding="utf-8"), "jps-cache", recent
    t0 = time.perf_counter()
    try:
        html, status, size = _download()
    except (requests.RequestException, JpsParseError) as e:
        trace.step(AGENT, "jps.fetch", input_summary=URL, output_summary=f"{type(e).__name__}: {e}", status="failed",
                   source="jps-live", duration_ms=int((time.perf_counter() - t0) * 1000),
                   decision="JPS unreachable or wrong page - keep last good data; next cycle retries")
        raise
    ms = int((time.perf_counter() - t0) * 1000)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"kel-{datetime.now(MYT):%Y%m%d-%H%M%S}.html"   # name in MYT
    path.write_text(html, encoding="utf-8")
    trace.step(AGENT, "jps.fetch", input_summary=URL, output_summary=f"HTTP {status}, {size} bytes",
               source="jps-live", duration_ms=ms, details={"snapshot": path.name})
    return html, "jps-live", path


def store(readings, source):
    """Upsert stations (never overwriting a stored value with a missing one) and add or correct river_levels.
    One transaction. Returns (stations, new_or_corrected_levels). Raises pg.PgError."""
    changed = 0
    with pg.transaction() as conn:
        for r in readings:
            conn.execute(
                """INSERT INTO stations (station_key, name, name_norm, river, district, jps_id,
                                         normal_m, alert_m, warning_m, danger_m, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                   ON CONFLICT (station_key) DO UPDATE SET
                     name = EXCLUDED.name, name_norm = EXCLUDED.name_norm,
                     river = COALESCE(EXCLUDED.river, stations.river),
                     district = COALESCE(EXCLUDED.district, stations.district),
                     jps_id = COALESCE(EXCLUDED.jps_id, stations.jps_id),
                     normal_m = COALESCE(EXCLUDED.normal_m, stations.normal_m),
                     alert_m = COALESCE(EXCLUDED.alert_m, stations.alert_m),
                     warning_m = COALESCE(EXCLUDED.warning_m, stations.warning_m),
                     danger_m = COALESCE(EXCLUDED.danger_m, stations.danger_m),
                     updated_at = now()""",
                (r.station_key, r.name, r.name_norm, r.river, r.district, r.jps_id,
                 r.normal_m, r.alert_m, r.warning_m, r.danger_m))
            if r.observed_at is not None and r.level_m is not None:   # no level = no reading to store
                cur = conn.execute(
                    """INSERT INTO river_levels (station_key, observed_at, level_m, source)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (station_key, observed_at) DO UPDATE
                         SET level_m = EXCLUDED.level_m, source = EXCLUDED.source, scraped_at = now()
                         WHERE river_levels.level_m IS DISTINCT FROM EXCLUDED.level_m""",
                    (r.station_key, r.observed_at, r.level_m, source))
                changed += cur.rowcount
    return len(readings), changed


def ingest(from_file=None):
    """One cycle: fetch (or read a file) -> parse -> store. Needs an active trace run. Returns a summary dict."""
    if config.sample_mode() and not from_file:
        raise JpsConfigError("SAMPLE_MODE: no live JPS fetch - use --from-file with a saved snapshot")
    pg.check_config()                                  # fail before touching JPS if we could not store anyway
    if from_file:
        path = Path(from_file)
        html, source = path.read_text(encoding="utf-8"), "jps-snapshot"
        trace.step(AGENT, "jps.fetch", output_summary=f"read saved snapshot {path.name}", source=source)
    else:
        html, source, path = fetch()
    try:
        readings = parse(html)
    except JpsParseError as e:
        trace.step(AGENT, "jps.parse", output_summary=str(e), status="failed", source=source,
                   decision="Page layout changed or empty - keep last good data, do not store")
        raise
    no_time = sum(r.observed_at is None for r in readings)
    no_level = sum(r.level_m is None for r in readings)
    no_thresholds = sum(None in (r.alert_m, r.warning_m, r.danger_m) for r in readings)
    warn = no_thresholds or parse.rejected
    trace.step(AGENT, "jps.parse", output_summary=f"{len(readings)} stations; {no_level} without level, "
               f"{no_time} without time, {no_thresholds} missing a threshold, {parse.rejected} rejected ids",
               source=source, decision=("Health check passed; missing thresholds keep their stored values"
                                        if warn else "Health check passed: columns, ids, row count, value ranges"))
    stations, changed = store(readings, source)
    trace.step(AGENT, "pg.store", output_summary=f"{stations} stations upserted, {changed} new or corrected readings",
               source="veda-pg", details={"snapshot": path.name if path else None})
    return {"source": source, "stations": stations, "new_levels": changed}


def main(argv=None):
    """CLI: one cycle, a saved file, or a 15-minute loop that keeps going after any failed cycle."""
    from dotenv import load_dotenv
    load_dotenv(trace.ROOT / ".env")
    ap = argparse.ArgumentParser(description="Collect JPS Kelantan river levels into veda-pg")
    ap.add_argument("--from-file", help="ingest a saved JPS snapshot instead of fetching")
    ap.add_argument("--loop", action="store_true", help="repeat every 15 minutes until Ctrl+C")
    args = ap.parse_args(argv)
    while True:
        trace.start_run("JPS collect" + (f" from {Path(args.from_file).name}" if args.from_file else ""))
        try:
            summary = ingest(args.from_file)
            trace.end_run("success", f"{summary['new_levels']} new readings ({summary['source']})")
            code = 0
        except KeyboardInterrupt:
            trace.end_run("failed", "interrupted by Ctrl+C - this cycle stored nothing (rolled back)")
            return 0
        except JpsConfigError as e:
            trace.end_run("failed", str(e))
            return 2                                   # a config problem will not fix itself - stop even in --loop
        except Exception as e:                         # noqa: BLE001 - one bad cycle must not end the collector
            trace.end_run("failed", f"{type(e).__name__}: {e}")
            code = 1
        if not args.loop:
            return code
        try:
            time.sleep(MIN_INTERVAL_S)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
