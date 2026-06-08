-- ============================================================================
-- Production Functions for ISO 50001 EnMS
-- ============================================================================
-- Purpose: Degree-day calculation, data quality checks, CUSUM functions
-- Standard: ISO 50006 (Energy Performance Indicators)
-- Date: October 22, 2025
-- ============================================================================

-- ============================================================================
-- Function: Calculate Degree-Days for HVAC Normalization
-- ============================================================================
-- Purpose: Weather normalization per ISO 50006 standard
-- Usage: SELECT * FROM calculate_degree_days('2024-01-01', '2024-12-31', 18.0);
-- ============================================================================

CREATE OR REPLACE FUNCTION calculate_degree_days(
    p_start_date DATE,
    p_end_date DATE,
    p_base_temp_c DECIMAL DEFAULT 18.0
) RETURNS TABLE(
    day DATE,
    heating_degree_days DECIMAL,
    cooling_degree_days DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        time_bucket('1 day', ed.time)::DATE as day,
        -- HDD = sum of (base_temp - actual_temp) for all hours where actual < base
        SUM(GREATEST(0, p_base_temp_c - ed.outdoor_temp_c)) as heating_degree_days,
        -- CDD = sum of (actual_temp - base_temp) for all hours where actual > base
        SUM(GREATEST(0, ed.outdoor_temp_c - p_base_temp_c)) as cooling_degree_days
    FROM environmental_data ed
    WHERE ed.time BETWEEN p_start_date AND (p_end_date + INTERVAL '1 day')
    GROUP BY time_bucket('1 day', ed.time)
    ORDER BY day;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_degree_days IS 'ISO 50006 degree-day calculation. Base temp 18°C (ASHRAE standard). HDD measures coldness requiring heating, CDD measures hotness requiring cooling.';

-- ============================================================================
-- Function: Get SEU Daily Aggregates with Degree-Days
-- ============================================================================
-- Purpose: Enhanced daily aggregates including degree-days for HVAC baselines
-- Usage: SELECT * FROM get_seu_daily_aggregates_dd('seu_id', '2024-01-01', '2024-12-31');
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
        AVG(ed.outdoor_temp_c) as avg_temp_c,
        -- Calculate degree-days at daily level using outdoor temperature
        SUM(GREATEST(0, p_base_temp_c - ed.outdoor_temp_c)) as heating_degree_days,
        SUM(GREATEST(0, ed.outdoor_temp_c - p_base_temp_c)) as cooling_degree_days,
        COUNT(DISTINCT EXTRACT(HOUR FROM er.time))::DECIMAL as avg_operating_hours
    FROM energy_readings er
    LEFT JOIN production_data pd ON er.time = pd.time AND er.machine_id = pd.machine_id
    LEFT JOIN environmental_data ed ON er.time = ed.time AND er.machine_id = ed.machine_id
    WHERE er.machine_id = ANY(v_machine_ids)
      AND er.time BETWEEN p_start_date AND (p_end_date + INTERVAL '1 day')
    GROUP BY time_bucket('1 day', er.time)
    HAVING SUM(er.energy_kwh) > 0
    ORDER BY day;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_seu_daily_aggregates_dd IS 'Enhanced daily aggregates with degree-days for HVAC baseline training. Replaces get_seu_daily_aggregates() when degree-day features needed.';

-- ============================================================================
-- Function: Enhanced Daily Aggregates with Data Quality
-- ============================================================================
-- Purpose: Original function with data quality scoring
-- Usage: SELECT * FROM get_seu_daily_aggregates_with_quality('seu_id', '2024-01-01', '2024-12-31');
-- ============================================================================

CREATE OR REPLACE FUNCTION get_seu_daily_aggregates_with_quality(
    p_seu_id UUID,
    p_start_date DATE,
    p_end_date DATE
) RETURNS TABLE(
    day DATE,
    total_energy_kwh DECIMAL,
    avg_production_count DECIMAL,
    avg_temp_c DECIMAL,
    avg_operating_hours DECIMAL,
    data_quality_score DECIMAL,
    data_completeness DECIMAL,
    outlier_count INTEGER
) AS $$
DECLARE
    v_machine_ids UUID[];
BEGIN
    -- Get machine IDs for this SEU
    SELECT machine_ids INTO v_machine_ids FROM seus WHERE id = p_seu_id;
    
    RETURN QUERY
    WITH daily_data AS (
        SELECT 
            time_bucket('1 day', er.time)::DATE as day,
            SUM(er.energy_kwh) as total_energy,
            AVG(pd.production_count) as avg_production,
            AVG(ed.machine_temp_c) as avg_temp,
            COUNT(DISTINCT EXTRACT(HOUR FROM er.time)) as operating_hours,
            COUNT(*) as total_readings,
            COUNT(*) FILTER (WHERE er.power_kw > AVG(er.power_kw) OVER () + 3*STDDEV(er.power_kw) OVER ()) as outliers
        FROM energy_readings er
        LEFT JOIN production_data pd ON er.time = pd.time AND er.machine_id = pd.machine_id
        LEFT JOIN environmental_data ed ON er.time = ed.time AND er.machine_id = ed.machine_id
        WHERE er.machine_id = ANY(v_machine_ids)
          AND er.time BETWEEN p_start_date AND (p_end_date + INTERVAL '1 day')
        GROUP BY time_bucket('1 day', er.time)
    )
    SELECT 
        dd.day,
        dd.total_energy,
        dd.avg_production,
        dd.avg_temp,
        dd.operating_hours,
        -- Data quality score (0-1): penalize missing data and outliers
        LEAST(1.0, (dd.total_readings / 24.0) * (1.0 - COALESCE(dd.outliers::DECIMAL / NULLIF(dd.total_readings, 0), 0))) as quality_score,
        (dd.total_readings / 24.0 * 100.0) as completeness,
        dd.outliers::INTEGER
    FROM daily_data dd
    WHERE dd.total_energy > 0
    ORDER BY dd.day;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_seu_daily_aggregates_with_quality IS 'Daily aggregates with data quality scoring. Used for baseline training validation and data quality monitoring.';

-- ============================================================================
-- Grant permissions
-- ============================================================================

GRANT EXECUTE ON FUNCTION calculate_degree_days(DATE, DATE, DECIMAL) TO CURRENT_USER;
GRANT EXECUTE ON FUNCTION get_seu_daily_aggregates_dd(UUID, DATE, DATE, DECIMAL) TO CURRENT_USER;
GRANT EXECUTE ON FUNCTION get_seu_daily_aggregates_with_quality(UUID, DATE, DATE) TO CURRENT_USER;

-- ============================================================================
-- Validation
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE 'Production Functions Created:';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE '✓ calculate_degree_days() - ISO 50006 degree-day calculation';
    RAISE NOTICE '✓ get_seu_daily_aggregates_dd() - Daily aggregates with degree-days';
    RAISE NOTICE '✓ get_seu_daily_aggregates_with_quality() - Data quality scoring';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE '';
END $$;
