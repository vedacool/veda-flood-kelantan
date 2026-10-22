-- station_risk_inputs: one row per CORE station - everything about it in one place
-- (river status + rain at its point + today's district forecast). place_risk_inputs (B-09) builds on this.
SELECT rs.station_key, rs.brief_name, rs.name, rs.district, rs.controls_town, rs.chain, rs.mapping_status,
       rs.level_m, rs.observed_at_utc, rs.age_minutes, rs.band, rs.change_1h_m, rs.change_3h_m,
       rs.normal_m, rs.alert_m, rs.warning_m, rs.danger_m,
       rp.point_key AS rain_point, rp.rain_past_24h_mm, rp.rain_past_7d_mm, rp.rain_next_24h_mm, rp.rain_next_72h_mm,
       rp.max_prob_next_24h_pct,
       fk.summary_forecast AS forecast_today, fk.summary_when AS forecast_today_when
FROM veda.river_status_latest rs
LEFT JOIN veda.rain_24h_by_point rp ON rp.station_key = rs.station_key
LEFT JOIN veda.forecast_kelantan fk
       ON fk.place = rs.district AND fk.level = 'district'
      AND fk.forecast_date = to_date(from_utc_timestamp(current_timestamp(), 'Asia/Kuala_Lumpur'))
WHERE rs.is_core = true
