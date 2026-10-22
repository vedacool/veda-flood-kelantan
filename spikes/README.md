# spikes/ — throwaway exploration, NOT VEDA code

Day-1 spike tests (backlog B-64, 22 Oct 2026): one-off scripts that probed Zetaris, data.gov.my, Postgres, Nightshift, the JPS page and runtime DDL before the real modules were built. Results and decisions are in `docs/spikes.md`.

These scripts call services directly (HTTP, SQL) on purpose and are excluded from VEDA's agent guard rules. Nothing in `app/` imports them. VEDA's real data path is `app/adapters/zetaris.py` (`run_sql`), its model path is `app/adapters/nightshift.py`, and river levels are collected by `app/ingest/jps.py`.
