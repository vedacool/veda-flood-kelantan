-- rain_24h_by_point: one row per rain point - how much rain fell, how much is coming?
-- Open-Meteo hourly values are the rain of the hour ENDING at that time, in Malaysia time (MYT);
-- Zetaris runs in GMT, so "now" is converted to MYT before comparing.
WITH clock AS (
    SELECT from_utc_timestamp(current_timestamp(), 'Asia/Kuala_Lumpur') AS now_myt
),
hours AS (
    SELECT COALESCE(r.location_id, 0) AS location_id,          -- Open-Meteo leaves the first point's id empty
           to_timestamp(t, "yyyy-MM-dd'T'HH:mm") AS ts_myt,
           CAST(r.hourly.precipitation[i] AS DOUBLE) AS rain_mm,
           CAST(r.hourly.precipitation_probability[i] AS DOUBLE) AS prob_pct
    FROM veda_wx.om_rain r
    LATERAL VIEW posexplode(r.hourly.time) h AS i, t
)
SELECT p.location_id, p.point_key, p.station_key, p.name, p.role,
       ROUND(SUM(CASE WHEN h.ts_myt > c.now_myt - INTERVAL 24 HOURS AND h.ts_myt <= c.now_myt THEN h.rain_mm END), 1) AS rain_past_24h_mm,
       ROUND(SUM(CASE WHEN h.ts_myt > c.now_myt - INTERVAL 7 DAYS AND h.ts_myt <= c.now_myt THEN h.rain_mm END), 1) AS rain_past_7d_mm,
       ROUND(SUM(CASE WHEN h.ts_myt > c.now_myt AND h.ts_myt <= c.now_myt + INTERVAL 24 HOURS THEN h.rain_mm END), 1) AS rain_next_24h_mm,
       ROUND(SUM(CASE WHEN h.ts_myt > c.now_myt AND h.ts_myt <= c.now_myt + INTERVAL 72 HOURS THEN h.rain_mm END), 1) AS rain_next_72h_mm,
       MAX(CASE WHEN h.ts_myt > c.now_myt AND h.ts_myt <= c.now_myt + INTERVAL 24 HOURS THEN h.prob_pct END) AS max_prob_next_24h_pct,
       MAX(h.ts_myt) AS forecast_until_myt
FROM hours h
CROSS JOIN clock c
JOIN veda_pg.rain_points p ON p.location_id = h.location_id
GROUP BY p.location_id, p.point_key, p.station_key, p.name, p.role
