-- Real-time view for energy baseline predictions
-- Uses 1-minute aggregation to match training data patterns
-- Proper feature engineering to match model training exactly

DROP VIEW IF EXISTS energy_predictions_realtime CASCADE;

CREATE VIEW energy_predictions_realtime AS
WITH aggregated_features AS (
  -- Aggregate to 1-minute intervals to match training data granularity
  -- This smooths out per-second noise and provides stable features
  SELECT 
    time_bucket('1 minute', er.time) AS time,
    er.machine_id,
    AVG(er.power_kw) as avg_power_kw,
    
    -- Match EXACT feature names from training query (database.py line 316)
    -- Scale production_count to hourly total: sum per minute × 60
    SUM(COALESCE(pd.production_count, 0)) * 60 as total_production_count,
    
    -- Throughput is already units/hour, just average it
    AVG(COALESCE(pd.throughput_units_per_hour, 0)) as avg_throughput_units_per_hour,
    
    -- Environmental features - average over the minute
    AVG(COALESCE(ed.outdoor_temp_c, 20)) as avg_outdoor_temp_c,
    AVG(COALESCE(ed.machine_temp_c, 60)) as avg_machine_temp_c,
    AVG(COALESCE(ed.pressure_bar, 6.0)) as avg_pressure_bar,
    
    -- Load factor calculation (same as training)
    AVG(COALESCE(
      er.power_kw / NULLIF((SELECT rated_power_kw FROM machines WHERE id = er.machine_id), 0),
      0.8
    )) as avg_load_factor
    
  FROM energy_readings er
  LEFT JOIN production_data pd ON er.machine_id = pd.machine_id AND er.time = pd.time
  LEFT JOIN environmental_data ed ON er.machine_id = ed.machine_id AND er.time = ed.time
  GROUP BY time_bucket('1 minute', er.time), er.machine_id
)
SELECT 
  time,
  machine_id,
  avg_power_kw as actual_avg_power_kw,
  
  -- Predict using the EXACT same features as training
  predict_power_from_baseline(
    machine_id,
    total_production_count,
    avg_outdoor_temp_c,
    avg_throughput_units_per_hour,
    avg_machine_temp_c,
    avg_load_factor,
    avg_pressure_bar
  ) as predicted_power_kw,
  
  -- Calculate deviation (actual - predicted)
  avg_power_kw - predict_power_from_baseline(
    machine_id,
    total_production_count,
    avg_outdoor_temp_c,
    avg_throughput_units_per_hour,
    avg_machine_temp_c,
    avg_load_factor,
    avg_pressure_bar
  ) as deviation_kw,
  
  -- Calculate deviation percentage
  CASE 
    WHEN predict_power_from_baseline(
      machine_id,
      total_production_count,
      avg_outdoor_temp_c,
      avg_throughput_units_per_hour,
      avg_machine_temp_c,
      avg_load_factor,
      avg_pressure_bar
    ) > 0 THEN
      (avg_power_kw - predict_power_from_baseline(
        machine_id,
        total_production_count,
        avg_outdoor_temp_c,
        avg_throughput_units_per_hour,
        avg_machine_temp_c,
        avg_load_factor,
        avg_pressure_bar
      )) / predict_power_from_baseline(
        machine_id,
        total_production_count,
        avg_outdoor_temp_c,
        avg_throughput_units_per_hour,
        avg_machine_temp_c,
        avg_load_factor,
        avg_pressure_bar
      ) * 100
    ELSE 0
  END as deviation_percent
FROM aggregated_features;

COMMENT ON VIEW energy_predictions_realtime IS 
'Real-time baseline predictions with 1-minute aggregation. Features engineered to exactly match model training data for accurate predictions.';
