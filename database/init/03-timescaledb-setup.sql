-- ============================================================================
-- EnMS - Energy Management System
-- Database Initialization Script 03: TimescaleDB Setup
-- ============================================================================
-- This script configures TimescaleDB hypertables and continuous aggregates
-- Execution order: Third (03)
-- ============================================================================

\echo '=========================================='
\echo 'Configuring TimescaleDB...'
\echo '=========================================='

-- ============================================================================
-- CONVERT TABLES TO HYPERTABLES
-- ============================================================================

\echo 'Converting tables to hypertables...'

-- Energy readings hypertable (main time-series data)
-- Partitioned by time with 1-day chunks
SELECT create_hypertable(
    'energy_readings',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

\echo '✓ energy_readings converted to hypertable'

-- Production data hypertable
SELECT create_hypertable(
    'production_data',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

\echo '✓ production_data converted to hypertable'

-- Environmental data hypertable
SELECT create_hypertable(
    'environmental_data',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

\echo '✓ environmental_data converted to hypertable'

-- ============================================================================
-- CONTINUOUS AGGREGATES - 1 MINUTE
-- ============================================================================

\echo 'Creating 1-minute continuous aggregates...'

-- Energy readings aggregated to 1 minute
CREATE MATERIALIZED VIEW energy_readings_1min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 minute', time) AS bucket,
    machine_id,
    
    -- Power statistics
    AVG(power_kw) AS avg_power_kw,
    MIN(power_kw) AS min_power_kw,
    MAX(power_kw) AS max_power_kw,
    STDDEV(power_kw) AS stddev_power_kw,
    
    -- Energy (sum of incremental readings)
    SUM(energy_kwh) AS total_energy_kwh,
    
    -- Electrical parameters
    AVG(voltage_v) AS avg_voltage_v,
    AVG(current_a) AS avg_current_a,
    AVG(power_factor) AS avg_power_factor,
    AVG(frequency_hz) AS avg_frequency_hz,
    
    -- Data quality
    COUNT(*) AS reading_count,
    COUNT(*) FILTER (WHERE is_estimated = TRUE) AS estimated_count
    
FROM energy_readings
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ energy_readings_1min created'

-- Production data aggregated to 1 minute
CREATE MATERIALIZED VIEW production_data_1min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 minute', time) AS bucket,
    machine_id,
    
    -- Production counts
    SUM(production_count) AS total_production_count,
    SUM(production_count_good) AS total_production_good,
    SUM(production_count_bad) AS total_production_bad,
    
    -- Average throughput
    AVG(throughput_units_per_hour) AS avg_throughput,
    
    -- Operating mode (most frequent)
    MODE() WITHIN GROUP (ORDER BY operating_mode) AS dominant_mode,
    
    -- Speed
    AVG(speed_percent) AS avg_speed_percent,
    
    -- Downtime
    SUM(downtime_seconds) AS total_downtime_seconds,
    
    COUNT(*) AS reading_count
    
FROM production_data
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ production_data_1min created'

-- Environmental data aggregated to 1 minute
CREATE MATERIALIZED VIEW environmental_data_1min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 minute', time) AS bucket,
    machine_id,
    
    -- Temperature averages
    AVG(outdoor_temp_c) AS avg_outdoor_temp_c,
    AVG(indoor_temp_c) AS avg_indoor_temp_c,
    AVG(machine_temp_c) AS avg_machine_temp_c,
    
    -- Humidity
    AVG(outdoor_humidity_percent) AS avg_outdoor_humidity,
    AVG(indoor_humidity_percent) AS avg_indoor_humidity,
    
    -- Pressure
    AVG(pressure_bar) AS avg_pressure_bar,
    MIN(pressure_bar) AS min_pressure_bar,
    MAX(pressure_bar) AS max_pressure_bar,
    
    -- Flow
    AVG(flow_rate_m3h) AS avg_flow_rate_m3h,
    
    -- HVAC metrics
    AVG(supply_air_temp_c) AS avg_supply_air_temp_c,
    AVG(return_air_temp_c) AS avg_return_air_temp_c,
    AVG(cop) AS avg_cop,
    
    -- Vibration
    AVG(vibration_mm_s) AS avg_vibration_mm_s,
    MAX(vibration_mm_s) AS max_vibration_mm_s,
    
    COUNT(*) AS reading_count
    
FROM environmental_data
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ environmental_data_1min created'

-- ============================================================================
-- CONTINUOUS AGGREGATES - 15 MINUTES
-- ============================================================================

\echo 'Creating 15-minute continuous aggregates...'

CREATE MATERIALIZED VIEW energy_readings_15min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('15 minutes', time) AS bucket,
    machine_id,
    
    -- Power statistics
    AVG(power_kw) AS avg_power_kw,
    MIN(power_kw) AS min_power_kw,
    MAX(power_kw) AS max_power_kw,
    
    -- Peak demand (important for utility billing)
    MAX(power_kw) AS peak_demand_kw,
    
    -- Energy
    SUM(energy_kwh) AS total_energy_kwh,
    
    -- Electrical parameters
    AVG(voltage_v) AS avg_voltage_v,
    AVG(current_a) AS avg_current_a,
    AVG(power_factor) AS avg_power_factor,
    AVG(frequency_hz) AS avg_frequency_hz,
    
    -- Load factor: avg_power / peak_power
    CASE 
        WHEN MAX(power_kw) > 0 THEN AVG(power_kw) / MAX(power_kw)
        ELSE 0
    END AS avg_load_factor,
    
    COUNT(*) AS total_readings
    
FROM energy_readings
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ energy_readings_15min created'

CREATE MATERIALIZED VIEW production_data_15min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('15 minutes', time) AS bucket,
    machine_id,
    
    SUM(production_count) AS total_production_count,
    SUM(production_count_good) AS total_production_good,
    SUM(production_count_bad) AS total_production_bad,
    
    AVG(throughput_units_per_hour) AS avg_throughput,
    AVG(speed_percent) AS avg_speed_percent,
    
    SUM(downtime_seconds) AS total_downtime_seconds,
    
    COUNT(*) AS total_readings
    
FROM production_data
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ production_data_15min created'

-- Environmental data aggregated to 15 minutes
CREATE MATERIALIZED VIEW environmental_data_15min
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('15 minutes', time) AS bucket,
    machine_id,
    
    AVG(outdoor_temp_c) AS avg_outdoor_temp_c,
    AVG(indoor_temp_c) AS avg_indoor_temp_c,
    AVG(machine_temp_c) AS avg_machine_temp_c,
    AVG(outdoor_humidity_percent) AS avg_outdoor_humidity,
    AVG(indoor_humidity_percent) AS avg_indoor_humidity,
    AVG(pressure_bar) AS avg_pressure_bar,
    MIN(pressure_bar) AS min_pressure_bar,
    MAX(pressure_bar) AS max_pressure_bar,
    AVG(flow_rate_m3h) AS avg_flow_rate_m3h,
    AVG(vibration_mm_s) AS avg_vibration_mm_s,
    
    COUNT(*) AS total_readings
    
FROM environmental_data
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ environmental_data_15min created'

-- ============================================================================
-- CONTINUOUS AGGREGATES - 1 HOUR
-- ============================================================================

\echo 'Creating 1-hour continuous aggregates...'

CREATE MATERIALIZED VIEW energy_readings_1hour
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS bucket,
    machine_id,
    
    AVG(power_kw) AS avg_power_kw,
    MIN(power_kw) AS min_power_kw,
    MAX(power_kw) AS max_power_kw,
    MAX(power_kw) AS peak_demand_kw,
    
    SUM(energy_kwh) AS total_energy_kwh,
    
    AVG(voltage_v) AS avg_voltage_v,
    AVG(current_a) AS avg_current_a,
    AVG(power_factor) AS avg_power_factor,
    
    CASE 
        WHEN MAX(power_kw) > 0 THEN AVG(power_kw) / MAX(power_kw)
        ELSE 0
    END AS avg_load_factor,
    
    COUNT(*) AS total_readings
    
FROM energy_readings
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ energy_readings_1hour created'

CREATE MATERIALIZED VIEW production_data_1hour
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS bucket,
    machine_id,
    
    SUM(production_count) AS total_production_count,
    SUM(production_count_good) AS total_production_good,
    SUM(production_count_bad) AS total_production_bad,
    
    -- Quality percentage
    CASE 
        WHEN SUM(production_count) > 0 THEN 
            (SUM(production_count_good)::DECIMAL / SUM(production_count)) * 100
        ELSE 0
    END AS quality_percent,
    
    AVG(throughput_units_per_hour) AS avg_throughput,
    AVG(speed_percent) AS avg_speed_percent,
    
    SUM(downtime_seconds) AS total_downtime_seconds,
    
    -- Availability calculation
    CASE 
        WHEN (3600 - SUM(downtime_seconds)) > 0 THEN
            ((3600 - SUM(downtime_seconds))::DECIMAL / 3600) * 100
        ELSE 0
    END AS availability_percent,
    
    COUNT(*) AS total_readings
    
FROM production_data
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ production_data_1hour created'

-- Environmental data aggregated to 1 hour
CREATE MATERIALIZED VIEW environmental_data_1hour
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS bucket,
    machine_id,
    
    AVG(outdoor_temp_c) AS avg_outdoor_temp_c,
    AVG(indoor_temp_c) AS avg_indoor_temp_c,
    AVG(machine_temp_c) AS avg_machine_temp_c,
    AVG(outdoor_humidity_percent) AS avg_outdoor_humidity,
    AVG(indoor_humidity_percent) AS avg_indoor_humidity,
    AVG(pressure_bar) AS avg_pressure_bar,
    AVG(flow_rate_m3h) AS avg_flow_rate_m3h,
    AVG(vibration_mm_s) AS avg_vibration_mm_s,
    
    COUNT(*) AS total_readings
    
FROM environmental_data
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ environmental_data_1hour created'

-- ============================================================================
-- CONTINUOUS AGGREGATES - 1 DAY
-- ============================================================================

\echo 'Creating 1-day continuous aggregates...'

CREATE MATERIALIZED VIEW energy_readings_1day
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS bucket,
    machine_id,
    
    AVG(power_kw) AS avg_power_kw,
    MIN(power_kw) AS min_power_kw,
    MAX(power_kw) AS max_power_kw,
    MAX(power_kw) AS peak_demand_kw,
    
    SUM(energy_kwh) AS total_energy_kwh,
    
    AVG(voltage_v) AS avg_voltage_v,
    AVG(power_factor) AS avg_power_factor,
    
    CASE 
        WHEN MAX(power_kw) > 0 THEN AVG(power_kw) / MAX(power_kw)
        ELSE 0
    END AS avg_load_factor,
    
    COUNT(*) AS total_readings
    
FROM energy_readings
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ energy_readings_1day created'

CREATE MATERIALIZED VIEW production_data_1day
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS bucket,
    machine_id,
    
    SUM(production_count) AS total_production_count,
    SUM(production_count_good) AS total_production_good,
    SUM(production_count_bad) AS total_production_bad,
    
    CASE 
        WHEN SUM(production_count) > 0 THEN 
            (SUM(production_count_good)::DECIMAL / SUM(production_count)) * 100
        ELSE 0
    END AS quality_percent,
    AVG(throughput_units_per_hour) AS avg_throughput,
    
    SUM(downtime_seconds) AS total_downtime_seconds,
    CASE 
        WHEN (86400 - SUM(downtime_seconds)) > 0 THEN
            ((86400 - SUM(downtime_seconds))::DECIMAL / 86400) * 100
        ELSE 0
    END AS availability_percent,
    
    COUNT(*) AS total_readings
    
FROM production_data
GROUP BY bucket, machine_id
WITH NO DATA;

\echo '✓ production_data_1day created'

-- Environmental degree days aggregated daily (for HVAC energy analysis)
CREATE MATERIALIZED VIEW environmental_degree_days_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS day,
    machine_id,
    
    AVG(outdoor_temp_c) AS avg_outdoor_temp_c,
    
    -- Heating degree days (base 18°C - common European standard)
    SUM(GREATEST(0, 18.0 - outdoor_temp_c)) AS heating_degree_days_18c,
    -- Cooling degree days (base 18°C)
    SUM(GREATEST(0, outdoor_temp_c - 18.0)) AS cooling_degree_days_18c,
    
    -- Heating degree days (base 15.5°C - UK standard)
    SUM(GREATEST(0, 15.5 - outdoor_temp_c)) AS heating_degree_days_15c,
    -- Cooling degree days (base 15.5°C)
    SUM(GREATEST(0, outdoor_temp_c - 15.5)) AS cooling_degree_days_15c,
    
    COUNT(*) AS readings_count,
    MIN(outdoor_temp_c) AS min_outdoor_temp_c,
    MAX(outdoor_temp_c) AS max_outdoor_temp_c
    
FROM environmental_data
GROUP BY day, machine_id
WITH NO DATA;

\echo '✓ environmental_degree_days_daily created'

-- ============================================================================
-- REFRESH POLICIES FOR CONTINUOUS AGGREGATES
-- ============================================================================

\echo 'Setting up refresh policies...'

-- 1-minute aggregates: refresh every 1 minute
SELECT add_continuous_aggregate_policy('energy_readings_1min',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');

SELECT add_continuous_aggregate_policy('production_data_1min',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');

SELECT add_continuous_aggregate_policy('environmental_data_1min',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');

\echo '✓ 1-minute refresh policies set'

-- 15-minute aggregates: refresh every 5 minutes
SELECT add_continuous_aggregate_policy('energy_readings_15min',
    start_offset => INTERVAL '6 hours',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '5 minutes');

SELECT add_continuous_aggregate_policy('production_data_15min',
    start_offset => INTERVAL '6 hours',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '5 minutes');

SELECT add_continuous_aggregate_policy('environmental_data_15min',
    start_offset => INTERVAL '6 hours',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '5 minutes');

\echo '✓ 15-minute refresh policies set'

-- 1-hour aggregates: refresh every 15 minutes
SELECT add_continuous_aggregate_policy('energy_readings_1hour',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes');

SELECT add_continuous_aggregate_policy('production_data_1hour',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes');

SELECT add_continuous_aggregate_policy('environmental_data_1hour',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes');

\echo '✓ 1-hour refresh policies set'

-- 1-day aggregates: refresh every hour
SELECT add_continuous_aggregate_policy('energy_readings_1day',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 hour');

SELECT add_continuous_aggregate_policy('production_data_1day',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 hour');

SELECT add_continuous_aggregate_policy('environmental_degree_days_daily',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 hour');

\echo '✓ 1-day refresh policies set'

-- ============================================================================
-- DATA RETENTION POLICIES
-- ============================================================================

\echo 'Setting up retention policies...'

-- Keep raw energy data for 90 days
SELECT add_retention_policy('energy_readings', INTERVAL '90 days');

-- Keep raw production data for 90 days
SELECT add_retention_policy('production_data', INTERVAL '90 days');

-- Keep raw environmental data for 90 days
SELECT add_retention_policy('environmental_data', INTERVAL '90 days');

\echo '✓ Retention policies set (90 days for raw data)'

-- Note: Continuous aggregates are kept indefinitely by default
-- Adjust as needed for your use case

-- ============================================================================
-- COMPRESSION POLICIES
-- ============================================================================

\echo 'Setting up compression policies...'

-- Enable compression on hypertables
ALTER TABLE energy_readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'machine_id',
    timescaledb.compress_orderby = 'time DESC'
);

ALTER TABLE production_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'machine_id',
    timescaledb.compress_orderby = 'time DESC'
);

ALTER TABLE environmental_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'machine_id',
    timescaledb.compress_orderby = 'time DESC'
);

\echo '✓ Compression enabled'

-- Compress chunks older than 7 days
SELECT add_compression_policy('energy_readings', INTERVAL '7 days');
SELECT add_compression_policy('production_data', INTERVAL '7 days');
SELECT add_compression_policy('environmental_data', INTERVAL '7 days');

\echo '✓ Compression policies set (7 days)'

\echo ''
\echo '=========================================='
\echo 'TimescaleDB configuration complete!'
\echo '=========================================='
\echo ''
\echo 'Hypertables:'
\echo '  - energy_readings (1-day chunks)'
\echo '  - production_data (1-day chunks)'
\echo '  - environmental_data (1-day chunks)'
\echo ''
\echo 'Continuous Aggregates:'
\echo '  - 1 minute (refreshed every 1 min)'
\echo '  - 15 minutes (refreshed every 5 min)'
\echo '  - 1 hour (refreshed every 15 min)'
\echo '  - 1 day (refreshed every 1 hour)'
\echo ''
\echo 'Data Retention: 90 days (raw data)'
\echo 'Compression: After 7 days'
\echo ''
