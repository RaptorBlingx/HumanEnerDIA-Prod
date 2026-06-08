-- ============================================================================
-- EnMS - Energy Management System
-- Database Initialization Script 05: Views
-- ============================================================================
-- This script creates views for common query patterns
-- Execution order: Fifth (05)
-- ============================================================================

\echo '=========================================='
\echo 'Creating Database Views...'
\echo '=========================================='

-- ============================================================================
-- MACHINE VIEWS
-- ============================================================================

\echo 'Creating machine views...'

-- Current machine status with latest metrics
CREATE OR REPLACE VIEW v_machines_current_status AS
SELECT 
    m.id AS machine_id,
    m.name AS machine_name,
    m.type AS machine_type,
    m.factory_id,
    f.name AS factory_name,
    m.rated_power_kw,
    
    ms.is_running,
    ms.current_mode,
    ms.current_power_kw,
    ms.operating_hours_total,
    ms.energy_total_kwh,
    ms.production_total_units,
    ms.alert_level,
    ms.alert_message,
    ms.health_score,
    ms.last_reading_time,
    ms.last_updated,
    
    m.is_active,
    m.is_critical
    
FROM machines m
LEFT JOIN factories f ON m.factory_id = f.id
LEFT JOIN machine_status ms ON m.id = ms.machine_id;

\echo '✓ v_machines_current_status created'

-- Machine details with specifications
CREATE OR REPLACE VIEW v_machines_detail AS
SELECT 
    m.id AS machine_id,
    m.name AS machine_name,
    m.description,
    m.type AS machine_type,
    m.manufacturer,
    m.model,
    m.serial_number,
    m.installation_date,
    
    m.rated_power_kw,
    m.rated_voltage_v,
    m.rated_current_a,
    m.rated_frequency_hz,
    
    m.location_in_factory,
    m.data_interval_seconds,
    
    m.factory_id,
    f.name AS factory_name,
    f.location AS factory_location,
    
    m.is_active,
    m.is_critical,
    m.created_at,
    m.metadata
    
FROM machines m
JOIN factories f ON m.factory_id = f.id;

\echo '✓ v_machines_detail created'

-- ============================================================================
-- REAL-TIME VIEWS (Last hour)
-- ============================================================================

\echo 'Creating real-time views...'

-- Latest energy readings per machine
CREATE OR REPLACE VIEW v_latest_energy_readings AS
SELECT DISTINCT ON (machine_id)
    machine_id,
    time,
    power_kw,
    energy_kwh,
    voltage_v,
    current_a,
    power_factor,
    frequency_hz
FROM energy_readings
WHERE time >= NOW() - INTERVAL '1 hour'
ORDER BY machine_id, time DESC;

\echo '✓ v_latest_energy_readings created'

-- Current hour metrics
CREATE OR REPLACE VIEW v_current_hour_metrics AS
SELECT 
    machine_id,
    time_bucket('1 hour', time) AS hour_bucket,
    
    AVG(power_kw) AS avg_power_kw,
    MAX(power_kw) AS max_power_kw,
    MIN(power_kw) AS min_power_kw,
    SUM(energy_kwh) AS total_energy_kwh,
    
    AVG(power_factor) AS avg_power_factor,
    AVG(voltage_v) AS avg_voltage_v,
    
    COUNT(*) AS reading_count
    
FROM energy_readings
WHERE time >= date_trunc('hour', NOW())
GROUP BY machine_id, time_bucket('1 hour', time);

\echo '✓ v_current_hour_metrics created'

-- ============================================================================
-- DASHBOARD SUMMARY VIEWS
-- ============================================================================

\echo 'Creating dashboard summary views...'

-- Today's summary per machine
CREATE OR REPLACE VIEW v_today_summary AS
SELECT 
    m.id AS machine_id,
    m.name AS machine_name,
    m.type AS machine_type,
    f.name AS factory_name,
    
    COALESCE(SUM(er.total_energy_kwh), 0) AS energy_today_kwh,
    COALESCE(AVG(er.avg_power_kw), 0) AS avg_power_today_kw,
    COALESCE(MAX(er.peak_demand_kw), 0) AS peak_demand_today_kw,
    
    COALESCE(SUM(pd.total_production_count), 0) AS production_today_units,
    
    CASE 
        WHEN SUM(pd.total_production_count) > 0 THEN
            SUM(er.total_energy_kwh) / SUM(pd.total_production_count)
        ELSE NULL
    END AS sec_today,
    
    ROUND(COALESCE(SUM(er.total_energy_kwh), 0) * 0.15, 2) AS cost_today,
    COALESCE(SUM(er.total_energy_kwh), 0) * 0.45 AS co2_today_kg
    
FROM machines m
LEFT JOIN factories f ON m.factory_id = f.id
LEFT JOIN energy_readings_1hour er 
    ON m.id = er.machine_id 
    AND er.bucket >= date_trunc('day', NOW())
LEFT JOIN production_data_1hour pd 
    ON m.id = pd.machine_id 
    AND pd.bucket = er.bucket
WHERE m.is_active = TRUE
GROUP BY m.id, m.name, m.type, f.name;

\echo '✓ v_today_summary created'

-- This week's summary per machine
CREATE OR REPLACE VIEW v_week_summary AS
SELECT 
    m.id AS machine_id,
    m.name AS machine_name,
    m.type AS machine_type,
    f.name AS factory_name,
    
    COALESCE(SUM(er.total_energy_kwh), 0) AS energy_week_kwh,
    COALESCE(AVG(er.avg_power_kw), 0) AS avg_power_week_kw,
    COALESCE(MAX(er.peak_demand_kw), 0) AS peak_demand_week_kw,
    
    COALESCE(SUM(pd.total_production_count), 0) AS production_week_units,
    
    CASE 
        WHEN SUM(pd.total_production_count) > 0 THEN
            SUM(er.total_energy_kwh) / SUM(pd.total_production_count)
        ELSE NULL
    END AS sec_week,
    
    ROUND(COALESCE(SUM(er.total_energy_kwh), 0) * 0.15, 2) AS cost_week,
    COALESCE(SUM(er.total_energy_kwh), 0) * 0.45 AS co2_week_kg
    
FROM machines m
LEFT JOIN factories f ON m.factory_id = f.id
LEFT JOIN energy_readings_1day er 
    ON m.id = er.machine_id 
    AND er.bucket >= date_trunc('week', NOW())
LEFT JOIN production_data_1day pd 
    ON m.id = pd.machine_id 
    AND pd.bucket = er.bucket
WHERE m.is_active = TRUE
GROUP BY m.id, m.name, m.type, f.name;

\echo '✓ v_week_summary created'

-- Factory-wide dashboard
CREATE OR REPLACE VIEW v_factory_dashboard AS
SELECT 
    f.id AS factory_id,
    f.name AS factory_name,
    f.location,
    
    COUNT(DISTINCT m.id) AS total_machines,
    COUNT(DISTINCT m.id) FILTER (WHERE m.is_active = TRUE) AS active_machines,
    COUNT(DISTINCT m.id) FILTER (WHERE ms.is_running = TRUE) AS running_machines,
    
    COALESCE(SUM(ms.current_power_kw), 0) AS current_total_power_kw,
    COALESCE(SUM(er.total_energy_kwh), 0) AS energy_today_kwh,
    COALESCE(SUM(pd.total_production_count), 0) AS production_today_units,
    
    COUNT(DISTINCT a.id) FILTER (WHERE a.is_resolved = FALSE) AS active_alerts,
    
    ROUND(COALESCE(SUM(er.total_energy_kwh), 0) * 0.15, 2) AS cost_today,
    COALESCE(SUM(er.total_energy_kwh), 0) * 0.45 AS co2_today_kg
    
FROM factories f
LEFT JOIN machines m ON f.id = m.factory_id
LEFT JOIN machine_status ms ON m.id = ms.machine_id
LEFT JOIN energy_readings_1hour er 
    ON m.id = er.machine_id 
    AND er.bucket >= date_trunc('day', NOW())
LEFT JOIN production_data_1hour pd 
    ON m.id = pd.machine_id 
    AND pd.bucket = er.bucket
LEFT JOIN anomalies a 
    ON m.id = a.machine_id 
    AND a.detected_at >= date_trunc('day', NOW())
GROUP BY f.id, f.name, f.location;

\echo '✓ v_factory_dashboard created'

-- ============================================================================
-- ANALYTICS VIEWS
-- ============================================================================

\echo 'Creating analytics views...'

-- Hourly energy consumption comparison (current vs previous day)
CREATE OR REPLACE VIEW v_energy_comparison_daily AS
SELECT 
    m.id AS machine_id,
    m.name AS machine_name,
    EXTRACT(HOUR FROM er_today.bucket) AS hour_of_day,
    
    er_today.total_energy_kwh AS energy_today_kwh,
    er_yesterday.total_energy_kwh AS energy_yesterday_kwh,
    
    CASE 
        WHEN er_yesterday.total_energy_kwh > 0 THEN
            ((er_today.total_energy_kwh - er_yesterday.total_energy_kwh) / 
             er_yesterday.total_energy_kwh) * 100
        ELSE NULL
    END AS change_percent
    
FROM machines m
LEFT JOIN energy_readings_1hour er_today 
    ON m.id = er_today.machine_id 
    AND er_today.bucket >= date_trunc('day', NOW())
LEFT JOIN energy_readings_1hour er_yesterday 
    ON m.id = er_yesterday.machine_id 
    AND er_yesterday.bucket = er_today.bucket - INTERVAL '1 day'
WHERE m.is_active = TRUE
ORDER BY m.id, hour_of_day;

\echo '✓ v_energy_comparison_daily created'

-- Active anomalies with machine context
CREATE OR REPLACE VIEW v_active_anomalies AS
SELECT 
    a.id AS anomaly_id,
    a.machine_id,
    m.name AS machine_name,
    m.type AS machine_type,
    f.name AS factory_name,
    
    a.detected_at,
    a.anomaly_type,
    a.severity,
    a.metric_name,
    a.metric_value,
    a.expected_value,
    a.deviation_percent,
    a.detection_method,
    a.confidence_score,
    
    ms.current_power_kw,
    ms.current_mode
    
FROM anomalies a
JOIN machines m ON a.machine_id = m.id
JOIN factories f ON m.factory_id = f.id
LEFT JOIN machine_status ms ON m.id = ms.machine_id
WHERE a.is_resolved = FALSE
ORDER BY a.severity DESC, a.detected_at DESC;

\echo '✓ v_active_anomalies created'

-- Energy baseline compliance
CREATE OR REPLACE VIEW v_baseline_compliance AS
SELECT 
    m.id AS machine_id,
    m.name AS machine_name,
    m.type AS machine_type,
    
    eb.model_name,
    eb.model_version,
    eb.r_squared,
    eb.is_active,
    eb.training_end_date AS last_trained,
    
    CASE 
        WHEN eb.is_active AND eb.training_end_date >= NOW() - INTERVAL '30 days' THEN 'current'
        WHEN eb.is_active AND eb.training_end_date >= NOW() - INTERVAL '90 days' THEN 'aging'
        WHEN eb.is_active THEN 'outdated'
        ELSE 'none'
    END AS baseline_status
    
FROM machines m
LEFT JOIN energy_baselines eb 
    ON m.id = eb.machine_id 
    AND eb.is_active = TRUE
WHERE m.is_active = TRUE;

\echo '✓ v_baseline_compliance created'

-- ============================================================================
-- TIME-SERIES VIEWS (For Grafana)
-- ============================================================================

\echo 'Creating time-series views...'

-- Minute-by-minute power trend (last 24 hours)
CREATE OR REPLACE VIEW v_power_trend_24h AS
SELECT 
    bucket AS time,
    machine_id,
    avg_power_kw AS power_kw
FROM energy_readings_1min
WHERE bucket >= NOW() - INTERVAL '24 hours'
ORDER BY bucket DESC;

\echo '✓ v_power_trend_24h created'

-- Daily energy consumption trend (last 30 days)
CREATE OR REPLACE VIEW v_energy_trend_30d AS
SELECT 
    bucket::DATE AS date,
    machine_id,
    total_energy_kwh AS energy_kwh,
    peak_demand_kw,
    avg_load_factor AS load_factor
FROM energy_readings_1day
WHERE bucket >= NOW() - INTERVAL '30 days'
ORDER BY bucket DESC;

\echo '✓ v_energy_trend_30d created'

-- ============================================================================
-- COST AND EMISSIONS VIEWS
-- ============================================================================

\echo 'Creating cost and emissions views...'

-- Monthly cost breakdown
CREATE OR REPLACE VIEW v_monthly_cost_breakdown AS
SELECT 
    date_trunc('month', er.bucket) AS month,
    m.id AS machine_id,
    m.name AS machine_name,
    m.type AS machine_type,
    f.name AS factory_name,
    
    SUM(er.total_energy_kwh) AS total_energy_kwh,
    MAX(er.peak_demand_kw) AS peak_demand_kw,
    
    ROUND(SUM(er.total_energy_kwh) * 0.15, 2) AS energy_cost,
    ROUND(MAX(er.peak_demand_kw) * 10, 2) AS demand_charge,
    ROUND((SUM(er.total_energy_kwh) * 0.15) + (MAX(er.peak_demand_kw) * 10), 2) AS total_cost
    
FROM energy_readings_1day er
JOIN machines m ON er.machine_id = m.id
JOIN factories f ON m.factory_id = f.id
WHERE er.bucket >= date_trunc('month', NOW()) - INTERVAL '12 months'
GROUP BY date_trunc('month', er.bucket), m.id, m.name, m.type, f.name
ORDER BY month DESC, m.name;

\echo '✓ v_monthly_cost_breakdown created'

-- Carbon emissions tracking
CREATE OR REPLACE VIEW v_carbon_emissions_tracking AS
SELECT 
    date_trunc('day', er.bucket)::DATE AS date,
    m.id AS machine_id,
    m.name AS machine_name,
    f.name AS factory_name,
    
    SUM(er.total_energy_kwh) AS total_energy_kwh,
    ROUND((SUM(er.total_energy_kwh) * 0.45)::NUMERIC, 3) AS total_co2_kg,
    ROUND((SUM(er.total_energy_kwh) * 0.45 / 1000)::NUMERIC, 3) AS total_co2_tonnes
    
FROM energy_readings_1day er
JOIN machines m ON er.machine_id = m.id
JOIN factories f ON m.factory_id = f.id
WHERE er.bucket >= NOW() - INTERVAL '90 days'
GROUP BY date_trunc('day', er.bucket), m.id, m.name, f.name
ORDER BY date DESC, m.name;

\echo '✓ v_carbon_emissions_tracking created'

\echo ''
\echo '=========================================='
\echo 'Database views created successfully!'
\echo '=========================================='
\echo ''
\echo 'Machine Views:'
\echo '  - v_machines_current_status'
\echo '  - v_machines_detail'
\echo ''
\echo 'Real-time Views:'
\echo '  - v_latest_energy_readings'
\echo '  - v_current_hour_metrics'
\echo ''
\echo 'Dashboard Views:'
\echo '  - v_today_summary'
\echo '  - v_week_summary'
\echo '  - v_factory_dashboard'
\echo ''
\echo 'Analytics Views:'
\echo '  - v_energy_comparison_daily'
\echo '  - v_active_anomalies'
\echo '  - v_baseline_compliance'
\echo ''
\echo 'Time-series Views:'
\echo '  - v_power_trend_24h'
\echo '  - v_energy_trend_30d'
\echo ''
\echo 'Cost & Emissions Views:'
\echo '  - v_monthly_cost_breakdown'
\echo '  - v_carbon_emissions_tracking'
\echo ''
