-- place_risk_inputs: ONE fused row per covered place - controlling gauge status + nearest rain + today's
-- town forecast. Sentinels and secondary gauges are in place_gauge_status (one row per place x gauge).
SELECT p.place_id, p.name AS place, p.kind, p.district, p.mapping_status,
       g.station_key AS controlling_gauge, rs.name AS gauge_name,
       rs.level_m, rs.observed_at_utc, rs.age_minutes, rs.band, rs.change_1h_m, rs.change_3h_m,
       rs.normal_m, rs.alert_m, rs.warning_m, rs.danger_m,
       rp.point_key AS rain_point, rp.rain_past_24h_mm, rp.rain_past_7d_mm, rp.rain_next_24h_mm,
       rp.rain_next_72h_mm, rp.max_prob_next_24h_pct,
       fk.summary_forecast AS forecast_today, fk.summary_when AS forecast_today_when
FROM veda_pg.places p
JOIN veda_pg.place_gauges g ON g.place_id = p.place_id AND g.role = 'controlling'
LEFT JOIN veda.river_status_latest rs ON rs.station_key = g.station_key
LEFT JOIN veda.rain_24h_by_point rp ON rp.location_id = p.rain_location_id
LEFT JOIN veda.forecast_kelantan fk
       ON fk.location_id = p.forecast_location_id
      AND fk.forecast_date = to_date(from_utc_timestamp(current_timestamp(), 'Asia/Kuala_Lumpur'))
