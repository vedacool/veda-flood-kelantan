-- place_gauge_status: one row per place x gauge (controlling, secondary, sentinels) with each gauge's status
-- and, for sentinels, the reported travel time to the controlling gauge when one is known (station_links).
SELECT p.place_id, p.name AS place, g.role, g.sort_order, g.station_key, rs.name AS gauge_name,
       rs.level_m, rs.age_minutes, rs.band, rs.change_1h_m, rs.change_3h_m, rs.alert_m, rs.warning_m, rs.danger_m,
       tt.lag_min_h, tt.lag_max_h, tt.lag_source
FROM veda_pg.places p
JOIN veda_pg.place_gauges g ON g.place_id = p.place_id
LEFT JOIN veda.river_status_latest rs ON rs.station_key = g.station_key
LEFT JOIN veda_pg.place_gauges c ON c.place_id = p.place_id AND c.role = 'controlling'
LEFT JOIN veda_pg.station_links tt
       ON tt.link_type = 'travel_time' AND tt.from_key = g.station_key AND tt.to_key = c.station_key
