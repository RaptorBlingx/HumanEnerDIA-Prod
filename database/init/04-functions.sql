-- ============================================================================
-- EnMS - Energy Management System
-- Database Initialization Script 04: Functions
-- ============================================================================
-- This script creates SQL functions for KPI calculations
-- Execution order: Fourth (04)
-- ============================================================================

\echo '=========================================='
\echo 'Creating SQL Functions...'
\echo '=========================================='

-- ============================================================================
-- KPI CALCULATION FUNCTIONS
-- ============================================================================

\echo 'Creating KPI calculation functions...'

-- ----------------------------------------------------------------------------
-- Function: Calculate Specific Energy Consumption (SEC)
-- ----------------------------------------------------------------------------
-- SEC = Total Energy (kWh) / Total Production (units)
-- Unit: kWh/unit

CREATE OR REPLACE FUNCTION calculate_sec(
    p_machine_id UUID,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
)
RETURNS TABLE (
    machine_id UUID,
    sec_kwh_per_unit DECIMAL(10, 4),
    total_energy_kwh DECIMAL(15, 3),
    total_production_units BIGINT,
    time_period_hours DECIMAL(10, 2)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p_machine_id,
        CASE 
            WHEN SUM(pd.total_production_count) > 0 THEN
                SUM(er.total_energy_kwh) / SUM(pd.total_production_count)
            ELSE NULL
        END AS sec_kwh_per_unit,
        SUM(er.total_energy_kwh) AS total_energy_kwh,
        COALESCE(SUM(pd.total_production_count), 0)::BIGINT AS total_production_units,
        EXTRACT(EPOCH FROM (p_end_time - p_start_time)) / 3600 AS time_period_hours
    FROM energy_readings_1hour er
    LEFT JOIN production_data_1hour pd 
        ON er.machine_id = pd.machine_id AND er.bucket = pd.bucket
    WHERE er.machine_id = p_machine_id
      AND er.bucket BETWEEN p_start_time AND p_end_time
    GROUP BY p_machine_id;
END;
$$ LANGUAGE plpgsql;

\echo '✓ calculate_sec() created'

-- ----------------------------------------------------------------------------
-- Function: Calculate Peak Demand
-- ----------------------------------------------------------------------------
-- Peak Demand = Maximum power over 15-minute interval
-- Unit: kW

CREATE OR REPLACE FUNCTION calculate_peak_demand(
    p_machine_id UUID,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
)
RETURNS TABLE (
    machine_id UUID,
    peak_demand_kw DECIMAL(10, 3),
    peak_time TIMESTAMPTZ,
    avg_power_kw DECIMAL(10, 3)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p_machine_id,
        MAX(peak_demand_kw) AS peak_demand_kw,
        (SELECT bucket FROM energy_readings_15min 
         WHERE machine_id = p_machine_id 
           AND bucket BETWEEN p_start_time AND p_end_time
         ORDER BY peak_demand_kw DESC LIMIT 1) AS peak_time,
        AVG(avg_power_kw) AS avg_power_kw
    FROM energy_readings_15min
    WHERE machine_id = p_machine_id
      AND bucket BETWEEN p_start_time AND p_end_time
    GROUP BY p_machine_id;
END;
$$ LANGUAGE plpgsql;

\echo '✓ calculate_peak_demand() created'

-- ----------------------------------------------------------------------------
-- Function: Calculate Load Factor
-- ----------------------------------------------------------------------------
-- Load Factor = Average Power / Peak Power
-- Unit: Decimal (0-1) or Percentage

CREATE OR REPLACE FUNCTION calculate_load_factor(
    p_machine_id UUID,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
)
RETURNS TABLE (
    machine_id UUID,
    load_factor DECIMAL(5, 4),
    load_factor_percent DECIMAL(5, 2),
    avg_power_kw DECIMAL(10, 3),
    max_power_kw DECIMAL(10, 3)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p_machine_id,
        CASE 
            WHEN MAX(max_power_kw) > 0 THEN
                AVG(avg_power_kw) / MAX(max_power_kw)
            ELSE 0
        END AS load_factor,
        CASE 
            WHEN MAX(max_power_kw) > 0 THEN
                (AVG(avg_power_kw) / MAX(max_power_kw)) * 100
            ELSE 0
        END AS load_factor_percent,
        AVG(avg_power_kw) AS avg_power_kw,
        MAX(max_power_kw) AS max_power_kw
    FROM energy_readings_15min
    WHERE machine_id = p_machine_id
      AND bucket BETWEEN p_start_time AND p_end_time
    GROUP BY p_machine_id;
END;
$$ LANGUAGE plpgsql;

\echo '✓ calculate_load_factor() created'

-- ----------------------------------------------------------------------------
-- Function: Calculate Energy Cost
-- ----------------------------------------------------------------------------
-- Cost = Energy (kWh) × Tariff Rate ($/kWh)
-- Considers time-of-use tariffs

CREATE OR REPLACE FUNCTION calculate_energy_cost(
    p_machine_id UUID,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ,
    p_factory_id UUID DEFAULT NULL
)
RETURNS TABLE (
    machine_id UUID,
    total_cost DECIMAL(15, 2),
    total_energy_kwh DECIMAL(15, 3),
    avg_rate_per_kwh DECIMAL(10, 6),
    currency VARCHAR(3)
) AS $$
DECLARE
    v_factory_id UUID;
    v_default_rate DECIMAL(10, 6) := 0.15; -- Default rate if no tariff found
    v_currency VARCHAR(3) := 'USD';
BEGIN
    -- Get factory_id if not provided
    IF p_factory_id IS NULL THEN
        SELECT m.factory_id INTO v_factory_id
        FROM machines m
        WHERE m.id = p_machine_id;
    ELSE
        v_factory_id := p_factory_id;
    END IF;
    
    RETURN QUERY
    WITH hourly_energy AS (
        SELECT 
            er.bucket,
            er.total_energy_kwh,
            EXTRACT(HOUR FROM er.bucket AT TIME ZONE 'UTC') AS hour_of_day,
            EXTRACT(DOW FROM er.bucket AT TIME ZONE 'UTC') AS day_of_week
        FROM energy_readings_1hour er
        WHERE er.machine_id = p_machine_id
          AND er.bucket BETWEEN p_start_time AND p_end_time
    ),
    energy_with_rates AS (
        SELECT 
            he.bucket,
            he.total_energy_kwh,
            COALESCE(
                (SELECT et.rate_per_kwh
                 FROM energy_tariffs et
                 WHERE et.factory_id = v_factory_id
                   AND et.is_active = TRUE
                   AND et.valid_from <= he.bucket::DATE
                   AND (et.valid_to IS NULL OR et.valid_to >= he.bucket::DATE)
                   AND (
                       NOT et.is_time_of_use OR
                       (he.hour_of_day >= et.start_hour AND he.hour_of_day < et.end_hour AND
                        he.day_of_week = ANY(et.applicable_days))
                   )
                 ORDER BY et.rate_per_kwh DESC
                 LIMIT 1
                ),
                v_default_rate
            ) AS rate
        FROM hourly_energy he
    )
    SELECT 
        p_machine_id,
        ROUND(SUM(ewr.total_energy_kwh * ewr.rate), 2) AS total_cost,
        SUM(ewr.total_energy_kwh) AS total_energy_kwh,
        CASE 
            WHEN SUM(ewr.total_energy_kwh) > 0 THEN
                SUM(ewr.total_energy_kwh * ewr.rate) / SUM(ewr.total_energy_kwh)
            ELSE v_default_rate
        END AS avg_rate_per_kwh,
        v_currency AS currency
    FROM energy_with_rates ewr;
END;
$$ LANGUAGE plpgsql;

\echo '✓ calculate_energy_cost() created'

-- ----------------------------------------------------------------------------
-- Function: Calculate Carbon Intensity
-- ----------------------------------------------------------------------------
-- Carbon Emissions = Energy (kWh) × Emission Factor (kg CO2/kWh)

CREATE OR REPLACE FUNCTION calculate_carbon_intensity(
    p_machine_id UUID,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ,
    p_region VARCHAR(255) DEFAULT 'default'
)
RETURNS TABLE (
    machine_id UUID,
    total_co2_kg DECIMAL(15, 3),
    total_energy_kwh DECIMAL(15, 3),
    emission_factor DECIMAL(10, 6),
    co2_per_unit_kg DECIMAL(10, 6)
) AS $$
DECLARE
    v_emission_factor DECIMAL(10, 6);
    v_default_factor DECIMAL(10, 6) := 0.45; -- Default: 0.45 kg CO2/kWh
BEGIN
    -- Get emission factor
    SELECT emission_factor_kg_co2_per_kwh INTO v_emission_factor
    FROM carbon_factors
    WHERE region = p_region
      AND is_active = TRUE
      AND valid_from <= CURRENT_DATE
      AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
    ORDER BY valid_from DESC
    LIMIT 1;
    
    IF v_emission_factor IS NULL THEN
        v_emission_factor := v_default_factor;
    END IF;
    
    RETURN QUERY
    SELECT 
        p_machine_id,
        SUM(er.total_energy_kwh) * v_emission_factor AS total_co2_kg,
        SUM(er.total_energy_kwh) AS total_energy_kwh,
        v_emission_factor AS emission_factor,
        CASE 
            WHEN SUM(pd.total_production_count) > 0 THEN
                (SUM(er.total_energy_kwh) * v_emission_factor) / SUM(pd.total_production_count)
            ELSE NULL
        END AS co2_per_unit_kg
    FROM energy_readings_1hour er
    LEFT JOIN production_data_1hour pd 
        ON er.machine_id = pd.machine_id AND er.bucket = pd.bucket
    WHERE er.machine_id = p_machine_id
      AND er.bucket BETWEEN p_start_time AND p_end_time
    GROUP BY p_machine_id;
END;
$$ LANGUAGE plpgsql;

\echo '✓ calculate_carbon_intensity() created'

-- ----------------------------------------------------------------------------
-- Function: Calculate All KPIs (Convenience Function)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION calculate_all_kpis(
    p_machine_id UUID,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
)
RETURNS TABLE (
    machine_id UUID,
    machine_name VARCHAR(255),
    time_period_hours DECIMAL(10, 2),
    
    -- Energy metrics
    total_energy_kwh DECIMAL(15, 3),
    avg_power_kw DECIMAL(10, 3),
    peak_demand_kw DECIMAL(10, 3),
    
    -- Production metrics
    total_production_units BIGINT,
    sec_kwh_per_unit DECIMAL(10, 4),
    
    -- Efficiency metrics
    load_factor DECIMAL(5, 4),
    load_factor_percent DECIMAL(5, 2),
    
    -- Cost metrics
    total_cost DECIMAL(15, 2),
    cost_per_unit DECIMAL(10, 4),
    
    -- Environmental metrics
    total_co2_kg DECIMAL(15, 3),
    co2_per_unit_kg DECIMAL(10, 6)
) AS $$
DECLARE
    v_rate DECIMAL(10, 6);
    v_co2_factor DECIMAL(10, 6);
    v_factory_id UUID;
BEGIN
    -- Get factory_id
    SELECT factory_id INTO v_factory_id FROM machines WHERE id = p_machine_id;

    -- Get average active rate (simplified for KPI summary)
    SELECT AVG(rate_per_kwh) INTO v_rate 
    FROM energy_tariffs 
    WHERE factory_id = v_factory_id AND is_active = true;
    
    IF v_rate IS NULL THEN v_rate := 0.15; END IF;

    -- Get CO2 factor
    SELECT emission_factor_kg_co2_per_kwh INTO v_co2_factor 
    FROM carbon_factors 
    WHERE is_active = true 
    ORDER BY valid_from DESC LIMIT 1;
    
    IF v_co2_factor IS NULL THEN v_co2_factor := 0.45; END IF;

    RETURN QUERY
    SELECT 
        m.id,
        m.name,
        EXTRACT(EPOCH FROM (p_end_time - p_start_time)) / 3600 AS time_period_hours,
        
        -- Energy
        COALESCE(SUM(er.total_energy_kwh), 0) AS total_energy_kwh,
        COALESCE(AVG(er.avg_power_kw), 0) AS avg_power_kw,
        COALESCE(MAX(er.peak_demand_kw), 0) AS peak_demand_kw,
        
        -- Production
        COALESCE(SUM(pd.total_production_count), 0)::BIGINT AS total_production_units,
        CASE 
            WHEN SUM(pd.total_production_count) > 0 THEN
                SUM(er.total_energy_kwh) / SUM(pd.total_production_count)
            ELSE NULL
        END AS sec_kwh_per_unit,
        
        -- Load factor
        CASE 
            WHEN MAX(er.max_power_kw) > 0 THEN
                AVG(er.avg_power_kw) / MAX(er.max_power_kw)
            ELSE 0
        END AS load_factor,
        CASE 
            WHEN MAX(er.max_power_kw) > 0 THEN
                (AVG(er.avg_power_kw) / MAX(er.max_power_kw)) * 100
            ELSE 0
        END AS load_factor_percent,
        
        -- Cost
        ROUND(COALESCE(SUM(er.total_energy_kwh), 0) * v_rate, 2) AS total_cost,
        CASE 
            WHEN SUM(pd.total_production_count) > 0 THEN
                (SUM(er.total_energy_kwh) * v_rate) / SUM(pd.total_production_count)
            ELSE NULL
        END AS cost_per_unit,
        
        -- Carbon
        COALESCE(SUM(er.total_energy_kwh), 0) * v_co2_factor AS total_co2_kg,
        CASE 
            WHEN SUM(pd.total_production_count) > 0 THEN
                (SUM(er.total_energy_kwh) * v_co2_factor) / SUM(pd.total_production_count)
            ELSE NULL
        END AS co2_per_unit_kg
        
    FROM machines m
    LEFT JOIN energy_readings_1hour er 
        ON m.id = er.machine_id 
        AND er.bucket BETWEEN p_start_time AND p_end_time
    LEFT JOIN production_data_1hour pd 
        ON m.id = pd.machine_id 
        AND pd.bucket = er.bucket
    WHERE m.id = p_machine_id
    GROUP BY m.id, m.name;
END;
$$ LANGUAGE plpgsql;

\echo '✓ calculate_all_kpis() created'

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

\echo 'Creating helper functions...'

-- ----------------------------------------------------------------------------
-- Function: Get Machine Operating Hours
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION get_machine_operating_hours(
    p_machine_id UUID,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
)
RETURNS TABLE (
    machine_id UUID,
    total_hours DECIMAL(10, 2),
    running_hours DECIMAL(10, 2),
    idle_hours DECIMAL(10, 2),
    downtime_hours DECIMAL(10, 2),
    utilization_percent DECIMAL(5, 2)
) AS $$
BEGIN
    RETURN QUERY
    WITH hourly_status AS (
        SELECT 
            pd.bucket,
            CASE 
                WHEN pd.total_production_count > 0 THEN 'running'
                WHEN pd.total_downtime_seconds >= 3600 THEN 'stopped'
                ELSE 'idle'
            END as dominant_mode,
            pd.total_downtime_seconds
        FROM production_data_1hour pd
        WHERE pd.machine_id = p_machine_id
          AND pd.bucket BETWEEN p_start_time AND p_end_time
    )
    SELECT 
        p_machine_id,
        EXTRACT(EPOCH FROM (p_end_time - p_start_time)) / 3600 AS total_hours,
        COUNT(*) FILTER (WHERE dominant_mode = 'running')::DECIMAL AS running_hours,
        COUNT(*) FILTER (WHERE dominant_mode = 'idle')::DECIMAL AS idle_hours,
        SUM(total_downtime_seconds) / 3600.0 AS downtime_hours,
        CASE 
            WHEN EXTRACT(EPOCH FROM (p_end_time - p_start_time)) > 0 THEN
                (COUNT(*) FILTER (WHERE dominant_mode = 'running')::DECIMAL / 
                 (EXTRACT(EPOCH FROM (p_end_time - p_start_time)) / 3600)) * 100
            ELSE 0
        END AS utilization_percent
    FROM hourly_status;
END;
$$ LANGUAGE plpgsql;

\echo '✓ get_machine_operating_hours() created'

-- ----------------------------------------------------------------------------
-- Function: Get Factory Summary
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION get_factory_summary(
    p_factory_id UUID,
    p_start_time TIMESTAMPTZ,
    p_end_time TIMESTAMPTZ
)
RETURNS TABLE (
    factory_id UUID,
    factory_name VARCHAR(255),
    machine_count BIGINT,
    active_machines BIGINT,
    total_energy_kwh DECIMAL(15, 3),
    total_cost DECIMAL(15, 2),
    total_co2_kg DECIMAL(15, 3),
    avg_load_factor DECIMAL(5, 4)
) AS $$
DECLARE
    v_rate DECIMAL(10, 6);
    v_co2_factor DECIMAL(10, 6);
BEGIN
    -- Get average active rate
    SELECT AVG(et.rate_per_kwh) INTO v_rate 
    FROM energy_tariffs et
    WHERE et.factory_id = p_factory_id AND et.is_active = true;
    
    IF v_rate IS NULL THEN v_rate := 0.15; END IF;

    -- Get CO2 factor
    SELECT cf.emission_factor_kg_co2_per_kwh INTO v_co2_factor 
    FROM carbon_factors cf
    WHERE cf.is_active = true 
    ORDER BY cf.valid_from DESC LIMIT 1;
    
    IF v_co2_factor IS NULL THEN v_co2_factor := 0.45; END IF;

    RETURN QUERY
    SELECT 
        f.id,
        f.name,
        COUNT(DISTINCT m.id) AS machine_count,
        COUNT(DISTINCT m.id) FILTER (WHERE m.is_active = TRUE) AS active_machines,
        COALESCE(SUM(er.energy_kwh), 0) AS total_energy_kwh,
        ROUND(COALESCE(SUM(er.energy_kwh), 0) * v_rate, 2) AS total_cost,
        COALESCE(SUM(er.energy_kwh), 0) * v_co2_factor AS total_co2_kg,
        0.0::DECIMAL(5,4) AS avg_load_factor
    FROM factories f
    LEFT JOIN machines m ON f.id = m.factory_id
    LEFT JOIN energy_readings er 
        ON m.id = er.machine_id 
        AND er.time BETWEEN p_start_time AND p_end_time
    WHERE f.id = p_factory_id
    GROUP BY f.id, f.name;
END;
$$ LANGUAGE plpgsql;

\echo '✓ get_factory_summary() created'

\echo ''
\echo '=========================================='
\echo 'SQL Functions created successfully!'
\echo '=========================================='
\echo ''
\echo 'KPI Functions:'
\echo '  - calculate_sec()'
\echo '  - calculate_peak_demand()'
\echo '  - calculate_load_factor()'
\echo '  - calculate_energy_cost()'
\echo '  - calculate_carbon_intensity()'
\echo '  - calculate_all_kpis()'
\echo ''
\echo 'Helper Functions:'
\echo '  - get_machine_operating_hours()'
\echo '  - get_factory_summary()'
\echo ''
