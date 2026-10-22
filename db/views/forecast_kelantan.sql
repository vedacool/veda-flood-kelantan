-- forecast_kelantan: one row per Kelantan place per day - what does MetMalaysia forecast?
-- data.gov.my levels: St = state, Ds = district, Tn = town (e.g. Tn030 Rantau Panjang).
SELECT f.location.location_id AS location_id,
       f.location.location_name AS place,
       CASE substr(f.location.location_id, 1, 2) WHEN 'St' THEN 'state' WHEN 'Ds' THEN 'district'
                                                  WHEN 'Tn' THEN 'town' ELSE 'other' END AS level,
       to_date(f.date) AS forecast_date,
       f.morning_forecast, f.afternoon_forecast, f.night_forecast,
       f.summary_forecast, f.summary_when,
       f.min_temp, f.max_temp
FROM veda_wx.mygov_forecast
LATERAL VIEW explode(data) AS f
WHERE f.location.location_id = 'St005'
   OR (substr(f.location.location_id, 1, 2) IN ('Ds', 'Tn')
       AND f.location.location_name IN ('Kota Bharu', 'Pasir Mas', 'Tumpat', 'Bachok', 'Pasir Puteh', 'Machang',
                                       'Tanah Merah', 'Kuala Krai', 'Jeli', 'Gua Musang', 'Rantau Panjang'))
