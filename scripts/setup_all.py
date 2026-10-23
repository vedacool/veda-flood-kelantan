"""Live-mode setup in one command (B-76): every Zetaris / Postgres step, in order, each idempotent (safe to re-run).

    python scripts/setup_all.py

Needs: Docker running, Zetaris running locally, and .env with ZETARIS_API_URL / ZETARIS_API_KEY / ZETARIS_ORG_ID and
the three VEDA_PG_* passwords (see README "Live setup"). Not needed for SAMPLE_MODE.

Order (each step is its own script, traced; the first failure stops the run):
  1. setup_pg       veda-pg container (127.0.0.1 only) on the Zetaris network, roles, schema, Zetaris datasource
  2. seed_stations  curated JPS gauges + thresholds + links (data/stations_mapping.csv)
  3. seed_peaks     historic peaks incl. Dec 2014 (data/historic_peaks.csv)
  4. seed_places    the place gazetteer (data/places.csv)
  5. setup_wx       Zetaris REST tables: Open-Meteo forecast + archives, data.gov.my forecast / warnings / flood feed
  6. setup_views    Zetaris views over the tables above (db/views/*.sql)
  7. build_replay   the Nov 2024 replay (cited news readings)
  8. build_replay   the SYNTHETIC scenes (data/replay/synthetic_anchors.csv)
River levels then come from the JPS collector at runtime (python -m app.ingest.jps --loop), never from the repo.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = [["setup_pg.py"], ["seed_stations.py"], ["seed_peaks.py"], ["seed_places.py"], ["setup_wx.py"],
         ["setup_views.py"], ["build_replay.py"],
         ["build_replay.py", "--anchors", str(ROOT / "data" / "replay" / "synthetic_anchors.csv")]]


def main():
    for i, step in enumerate(STEPS, 1):
        print(f"[{i}/{len(STEPS)}] {' '.join(step)}", flush=True)
        if subprocess.run([sys.executable, str(ROOT / "scripts" / step[0]), *step[1:]], cwd=ROOT).returncode:
            print(f"FAILED at step {i} ({step[0]}) - fix it and re-run; finished steps are safe to repeat.")
            return 1
    print("Live setup complete. Start the JPS collector: python -m app.ingest.jps --loop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
