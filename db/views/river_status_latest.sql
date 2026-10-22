-- river_status_latest: one row per JPS gauge - what is each river doing right now?
-- Facts only (level, reading time, age, band, change); freshness and verdicts are decided in Python.
-- Zetaris runs in GMT: observed_at is UTC; age_minutes = now - reading time.
WITH ranked AS (
    SELECT station_key, level_m, observed_at,
           ROW_NUMBER() OVER (PARTITION BY station_key ORDER BY observed_at DESC) AS rn
    FROM veda_pg.river_levels
),
latest AS (
    SELECT station_key, level_m, observed_at FROM ranked WHERE rn = 1
),
earlier AS (   -- the newest reading at least 1 h / 3 h older than the latest one (within a 1 h window)
    SELECT l.station_key,
           r.level_m,
           CASE WHEN r.observed_at <= l.observed_at - INTERVAL 3 HOURS THEN 3 ELSE 1 END AS hours_back,
           ROW_NUMBER() OVER (
               PARTITION BY l.station_key, CASE WHEN r.observed_at <= l.observed_at - INTERVAL 3 HOURS THEN 3 ELSE 1 END
               ORDER BY r.observed_at DESC) AS rn
    FROM latest l
    JOIN veda_pg.river_levels r ON r.station_key = l.station_key
    WHERE (r.observed_at <= l.observed_at - INTERVAL 1 HOURS AND r.observed_at > l.observed_at - INTERVAL 2 HOURS)
       OR (r.observed_at <= l.observed_at - INTERVAL 3 HOURS AND r.observed_at > l.observed_at - INTERVAL 4 HOURS)
)
SELECT s.station_key, s.name, s.brief_name, s.is_core, s.chain, s.chain_order, s.controls_town, s.district, s.river,
       s.mapping_status,
       l.level_m,
       l.observed_at AS observed_at_utc,
       CAST(ROUND((unix_timestamp(current_timestamp()) - unix_timestamp(l.observed_at)) / 60) AS INT) AS age_minutes,
       s.normal_m, s.alert_m, s.warning_m, s.danger_m,
       CASE WHEN l.level_m IS NULL THEN 'no_reading'
            WHEN s.danger_m IS NOT NULL AND l.level_m >= s.danger_m THEN 'danger'
            WHEN s.warning_m IS NOT NULL AND l.level_m >= s.warning_m THEN 'warning'
            WHEN s.alert_m IS NOT NULL AND l.level_m >= s.alert_m THEN 'alert'
            WHEN s.normal_m IS NOT NULL AND l.level_m >= s.normal_m THEN 'normal'
            WHEN s.normal_m IS NOT NULL THEN 'below_normal'
            ELSE 'unknown' END AS band,
       ROUND(l.level_m - e1.level_m, 2) AS change_1h_m,
       ROUND(l.level_m - e3.level_m, 2) AS change_3h_m
FROM veda_pg.stations s
LEFT JOIN latest l ON l.station_key = s.station_key
LEFT JOIN earlier e1 ON e1.station_key = s.station_key AND e1.hours_back = 1 AND e1.rn = 1
LEFT JOIN earlier e3 ON e3.station_key = s.station_key AND e3.hours_back = 3 AND e3.rn = 1
