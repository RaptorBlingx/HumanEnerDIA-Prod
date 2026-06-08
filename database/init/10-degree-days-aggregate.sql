-- ============================================================================
-- Migration 006: Degree-Days Continuous Aggregate for HVAC Baselines
-- ============================================================================
-- Purpose: Pre-calculate daily degree-days to avoid timeout on large queries
-- Date: October 23, 2025
-- ============================================================================

-- Drop existing aggregate if exists (for idempotency)
DROP MATERIALIZED VIEW IF EXISTS environmental_degree_days_daily CASCADE;

-- Create continuous aggregate for daily degree-days
CREATE MATERIALIZED VIEW environmental_degree_days_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) as day,
    machine_id,
    -- Average outdoor temperature for the day
    AVG(outdoor_temp_c) as avg_outdoor_temp_c,
    -- Heating Degree Days (base 18°C)
    -- HDD = sum of max(0, 18°C - temp) for all hours
    SUM(GREATEST(0, 18.0 - outdoor_temp_c)) as heating_degree_days_18c,
    -- Cooling Degree Days (base 18°C)
    -- CDD = sum of max(0, temp - 18°C) for all hours
    SUM(GREATEST(0, outdoor_temp_c - 18.0)) as cooling_degree_days_18c,
    -- Additional bases for flexibility
    SUM(GREATEST(0, 15.5 - outdoor_temp_c)) as heating_degree_days_15c,
    SUM(GREATEST(0, outdoor_temp_c - 15.5)) as cooling_degree_days_15c,
    -- Data quality
    COUNT(*) as readings_count,
    MIN(outdoor_temp_c) as min_outdoor_temp_c,
    MAX(outdoor_temp_c) as max_outdoor_temp_c
FROM environmental_data
GROUP BY day, machine_id;

-- Add refresh policy (refresh last 7 days every hour)
SELECT add_continuous_aggregate_policy('environmental_degree_days_daily',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_env_dd_daily_machine_day 
    ON environmental_degree_days_daily (machine_id, day DESC);

-- Add comment
COMMENT ON VIEW environmental_degree_days_daily IS 
'Continuous aggregate for daily degree-days (ISO 50006 standard). 
Base temperatures: 18°C (ASHRAE commercial), 15.5°C (European residential). 
Refreshes hourly for last 7 days.';

-- ============================================================================
-- Improved Function: Get SEU Daily Aggregates with Degree-Days
-- ============================================================================
-- Purpose: Use the continuous aggregate instead of calculating on-the-fly
-- ============================================================================

CREATE OR REPLACE FUNCTION get_seu_daily_aggregates_dd(
    p_seu_id UUID,
    p_start_date DATE,
    p_end_date DATE,
    p_base_temp_c DECIMAL DEFAULT 18.0
) RETURNS TABLE(
    day DATE,
    total_energy_kwh DECIMAL,
    avg_production_count DECIMAL,
    avg_temp_c DECIMAL,
    heating_degree_days DECIMAL,
    cooling_degree_days DECIMAL,
    avg_operating_hours DECIMAL
) AS $$
DECLARE
    v_machine_ids UUID[];
BEGIN
    -- Get machine IDs for this SEU
    SELECT machine_ids INTO v_machine_ids FROM seus WHERE id = p_seu_id;
    
    RETURN QUERY
    SELECT 
        time_bucket('1 day', er.time)::DATE as day,
        SUM(er.energy_kwh) as total_energy_kwh,
        AVG(pd.production_count) as avg_production_count,
        AVG(dd.avg_outdoor_temp_c) as avg_temp_c,
        -- Use pre-calculated degree-days from continuous aggregate
        SUM(dd.heating_degree_days_18c) as heating_degree_days,
        SUM(dd.cooling_degree_days_18c) as cooling_degree_days,
        COUNT(DISTINCT EXTRACT(HOUR FROM er.time))::DECIMAL as avg_operating_hours
    FROM energy_readings er
    LEFT JOIN production_data pd ON er.time = pd.time AND er.machine_id = pd.machine_id
    LEFT JOIN environmental_degree_days_daily dd ON dd.day = er.time::DATE AND dd.machine_id = er.machine_id
    WHERE er.machine_id = ANY(v_machine_ids)
      AND er.time BETWEEN p_start_date AND (p_end_date + INTERVAL '1 day')
    GROUP BY time_bucket('1 day', er.time)
    HAVING SUM(er.energy_kwh) IS NOT NULL AND SUM(er.energy_kwh) > 0
    ORDER BY day;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_seu_daily_aggregates_dd IS 
'Enhanced daily aggregates using pre-calculated degree-days from continuous aggregate. 
Much faster than on-the-fly calculation for large date ranges.';

-- Grant permissions
GRANT SELECT ON environmental_degree_days_daily TO CURRENT_USER;
GRANT EXECUTE ON FUNCTION get_seu_daily_aggregates_dd TO CURRENT_USER;

-- ============================================================================
-- Backfill Historical Data
-- ============================================================================
-- Purpose: Calculate degree-days for all historical data (2024 + 2025 YTD)
-- ============================================================================

-- Refresh the continuous aggregate for 2024
CALL refresh_continuous_aggregate('environmental_degree_days_daily', 
    '2024-01-01', '2025-01-01');

-- Refresh for 2025 YTD
CALL refresh_continuous_aggregate('environmental_degree_days_daily', 
    '2025-01-01', NOW());

-- Verify backfill
DO $$
DECLARE
    v_count BIGINT;
    v_date_range TEXT;
BEGIN
    SELECT COUNT(*), 
           MIN(day)::TEXT || ' to ' || MAX(day)::TEXT
    INTO v_count, v_date_range
    FROM environmental_degree_days_daily;
    
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE 'Degree-Days Continuous Aggregate Created:';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE '✓ Daily degree-days calculated: % rows', v_count;
    RAISE NOTICE '✓ Date range: %', v_date_range;
    RAISE NOTICE '✓ Refresh policy: Every 1 hour for last 7 days';
    RAISE NOTICE '✓ Base temperatures: 18°C (ASHRAE), 15.5°C (European)';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE '';
END $$;
