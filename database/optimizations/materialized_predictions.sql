-- Replace slow VIEW with fast MATERIALIZED VIEW
DROP MATERIALIZED VIEW IF EXISTS energy_predictions_realtime CASCADE;

CREATE MATERIALIZED VIEW energy_predictions_realtime AS
WITH aggregated_features AS (
  SELECT 
    time_bucket('1 minute', er.time) AS time,
    er.machine_id,
    AVG(er.power_kw) as avg_power_kw,
    SUM(COALESCE(pd.production_count, 0)) * 60 as total_production_count,
    AVG(COALESCE(pd.throughput_units_per_hour, 0)) as avg_throughput_units_per_hour,
    AVG(COALESCE(ed.outdoor_temp_c, 20)) as avg_outdoor_temp_c,
    AVG(COALESCE(ed.machine_temp_c, 60)) as avg_machine_temp_c,
    AVG(COALESCE(ed.pressure_bar, 6.0)) as avg_pressure_bar,
    AVG(COALESCE(
      er.power_kw / NULLIF((SELECT rated_power_kw FROM machines WHERE id = er.machine_id), 0),
      0.8
    )) as avg_load_factor
  FROM energy_readings er
  LEFT JOIN production_data pd ON er.machine_id = pd.machine_id AND er.time = pd.time
  LEFT JOIN environmental_data ed ON er.machine_id = ed.machine_id AND er.time = ed.time
  WHERE er.time >= NOW() - INTERVAL '7 days'
    AND er.time < date_trunc('minute', NOW()) - INTERVAL '1 minute'  -- Exclude incomplete current + last minute
  GROUP BY time_bucket('1 minute', er.time), er.machine_id
)
SELECT 
  time, machine_id,
  avg_power_kw as actual_avg_power_kw,
  predict_power_from_baseline(machine_id, total_production_count, avg_outdoor_temp_c, avg_throughput_units_per_hour, avg_machine_temp_c, avg_load_factor, avg_pressure_bar) as predicted_power_kw,
  avg_power_kw - predict_power_from_baseline(machine_id, total_production_count, avg_outdoor_temp_c, avg_throughput_units_per_hour, avg_machine_temp_c, avg_load_factor, avg_pressure_bar) as deviation_kw,
  CASE WHEN predict_power_from_baseline(machine_id, total_production_count, avg_outdoor_temp_c, avg_throughput_units_per_hour, avg_machine_temp_c, avg_load_factor, avg_pressure_bar) > 0 THEN (avg_power_kw - predict_power_from_baseline(machine_id, total_production_count, avg_outdoor_temp_c, avg_throughput_units_per_hour, avg_machine_temp_c, avg_load_factor, avg_pressure_bar)) / predict_power_from_baseline(machine_id, total_production_count, avg_outdoor_temp_c, avg_throughput_units_per_hour, avg_machine_temp_c, avg_load_factor, avg_pressure_bar) * 100 ELSE 0 END as deviation_percent
FROM aggregated_features;

CREATE INDEX idx_predictions_machine_time ON energy_predictions_realtime (machine_id, time DESC);
CREATE INDEX idx_predictions_time ON energy_predictions_realtime (time DESC);
CREATE UNIQUE INDEX idx_predictions_unique ON energy_predictions_realtime (machine_id, time);
