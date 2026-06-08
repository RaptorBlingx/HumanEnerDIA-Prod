-- ============================================================================
-- Migration 006: Energy Source Features (Dynamic Feature Discovery)
-- ============================================================================
-- Purpose: Enable dynamic feature discovery for multi-energy baselines
-- Mr. Umut Requirement: "ZERO hardcoding - system must work for ANY energy source"
-- 
-- This table documents what features are available for each energy source.
-- Baseline training service queries this table to:
--   1. Discover available features dynamically
--   2. Build aggregation queries based on source_table + source_column
--   3. Validate requested features exist
-- 
-- Example: Natural gas boiler baseline needs outdoor_temp + heating_degree_days
-- System queries this table → finds features → builds dynamic SQL → trains baseline
-- NO CODE CHANGES needed when adding new energy source or features!
-- ============================================================================

\echo '=========================================='
\echo 'Creating Energy Source Features Table...'
\echo '=========================================='

-- Create energy_source_features table
CREATE TABLE IF NOT EXISTS energy_source_features (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    energy_source_id UUID NOT NULL REFERENCES energy_sources(id) ON DELETE CASCADE,
    feature_name VARCHAR(100) NOT NULL,           -- User-friendly name: 'consumption_kwh', 'outdoor_temp_c'
    data_type VARCHAR(50) NOT NULL,               -- 'numeric', 'integer', 'boolean'
    source_table VARCHAR(100) NOT NULL,           -- 'energy_readings', 'natural_gas_readings', 'environmental_data'
    source_column VARCHAR(100) NOT NULL,          -- 'energy_kwh', 'flow_rate_m3h', 'outdoor_temp_c'
    aggregation_function VARCHAR(50) NOT NULL,    -- 'SUM', 'AVG', 'MAX', 'MIN', 'CUSTOM'
    description TEXT,
    is_regression_feature BOOLEAN DEFAULT true,   -- Can be used in baseline training?
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Each feature must be unique per energy source
    UNIQUE(energy_source_id, feature_name)
);

CREATE INDEX idx_esf_energy_source ON energy_source_features(energy_source_id);
CREATE INDEX idx_esf_source_table ON energy_source_features(source_table);
CREATE INDEX idx_esf_regression ON energy_source_features(is_regression_feature) WHERE is_regression_feature = true;

COMMENT ON TABLE energy_source_features IS 'Dynamic feature discovery for multi-energy baselines. Enables zero-hardcoding architecture per Mr. Umut requirements.';
COMMENT ON COLUMN energy_source_features.feature_name IS 'User-friendly name shown in API/UI';
COMMENT ON COLUMN energy_source_features.source_table IS 'Physical table containing the data';
COMMENT ON COLUMN energy_source_features.source_column IS 'Column name in source_table';
COMMENT ON COLUMN energy_source_features.aggregation_function IS 'How to aggregate hourly data to daily: SUM for consumption, AVG for temperature';
COMMENT ON COLUMN energy_source_features.is_regression_feature IS 'true = can be used as baseline feature, false = metadata only';

\echo '✓ Energy source features table created'

-- ============================================================================
-- Seed Electricity Features (Current System)
-- ============================================================================
\echo ''
\echo 'Seeding electricity features...'

DO $$
DECLARE
    v_electricity_id UUID;
BEGIN
    -- Get electricity energy source ID
    SELECT id INTO v_electricity_id FROM energy_sources WHERE name = 'electricity';
    
    IF v_electricity_id IS NULL THEN
        RAISE EXCEPTION 'Electricity energy source not found! Run 004-production-seus.sql first.';
    END IF;
    
    -- Insert electricity features (existing system)
    INSERT INTO energy_source_features (energy_source_id, feature_name, data_type, source_table, source_column, aggregation_function, description) VALUES
    
    -- Energy readings features
    (v_electricity_id, 'consumption_kwh', 'numeric', 'energy_readings', 'energy_kwh', 'SUM', 'Total electrical energy consumed (kWh)'),
    (v_electricity_id, 'avg_power_kw', 'numeric', 'energy_readings', 'power_kw', 'AVG', 'Average electrical power demand (kW)'),
    (v_electricity_id, 'max_power_kw', 'numeric', 'energy_readings', 'power_kw', 'MAX', 'Peak electrical power demand (kW)'),
    (v_electricity_id, 'avg_voltage_v', 'numeric', 'energy_readings', 'voltage_v', 'AVG', 'Average supply voltage (V)'),
    (v_electricity_id, 'avg_current_a', 'numeric', 'energy_readings', 'current_a', 'AVG', 'Average current draw (A)'),
    (v_electricity_id, 'avg_power_factor', 'numeric', 'energy_readings', 'power_factor', 'AVG', 'Average power factor (0-1)'),
    
    -- Production data features
    (v_electricity_id, 'production_count', 'numeric', 'production_data', 'production_count', 'AVG', 'Average production units per hour'),
    (v_electricity_id, 'total_production', 'numeric', 'production_data', 'production_count', 'SUM', 'Total production units'),
    (v_electricity_id, 'avg_throughput', 'numeric', 'production_data', 'throughput_units_per_hour', 'AVG', 'Average throughput rate'),
    (v_electricity_id, 'avg_cycle_time_sec', 'numeric', 'production_data', 'cycle_time_seconds', 'AVG', 'Average cycle time (seconds)'),
    (v_electricity_id, 'good_units_count', 'integer', 'production_data', 'good_units_count', 'SUM', 'Total good units produced'),
    (v_electricity_id, 'defect_units_count', 'integer', 'production_data', 'defect_units_count', 'SUM', 'Total defective units'),
    
    -- Environmental data features (applicable to all energy types)
    (v_electricity_id, 'outdoor_temp_c', 'numeric', 'environmental_data', 'outdoor_temp_c', 'AVG', 'Average outdoor temperature (°C)'),
    (v_electricity_id, 'indoor_temp_c', 'numeric', 'environmental_data', 'indoor_temp_c', 'AVG', 'Average indoor temperature (°C)'),
    (v_electricity_id, 'machine_temp_c', 'numeric', 'environmental_data', 'machine_temp_c', 'AVG', 'Average machine temperature (°C)'),
    (v_electricity_id, 'outdoor_humidity_percent', 'numeric', 'environmental_data', 'outdoor_humidity_percent', 'AVG', 'Average outdoor humidity (%)'),
    (v_electricity_id, 'pressure_bar', 'numeric', 'environmental_data', 'pressure_bar', 'AVG', 'Average operating pressure (bar)'),
    
    -- Degree-days (CUSTOM aggregation - calculated separately)
    (v_electricity_id, 'heating_degree_days', 'numeric', 'environmental_data', 'outdoor_temp_c', 'CUSTOM', 'Heating degree days (ISO 50006) - SUM(MAX(0, 18°C - outdoor_temp))'),
    (v_electricity_id, 'cooling_degree_days', 'numeric', 'environmental_data', 'outdoor_temp_c', 'CUSTOM', 'Cooling degree days (ISO 50006) - SUM(MAX(0, outdoor_temp - 18°C))'),
    
    -- Operating hours (derived feature)
    (v_electricity_id, 'operating_hours', 'numeric', 'energy_readings', 'time', 'CUSTOM', 'COUNT(DISTINCT EXTRACT(HOUR FROM time)) - hours machine was active')
    
    ON CONFLICT (energy_source_id, feature_name) DO NOTHING;

        UPDATE energy_source_features
        SET is_regression_feature = false
        WHERE energy_source_id = v_electricity_id
            AND feature_name IN ('consumption_kwh', 'avg_power_kw', 'max_power_kw', 'avg_current_a', 'avg_voltage_v');
    
    RAISE NOTICE '✓ Electricity features seeded: % features', (SELECT COUNT(*) FROM energy_source_features WHERE energy_source_id = v_electricity_id);
END $$;

-- ============================================================================
-- Seed Natural Gas Features (Phase 2 Ready)
-- ============================================================================
\echo ''
\echo 'Seeding natural gas features (Phase 2 ready)...'

DO $$
DECLARE
    v_natural_gas_id UUID;
BEGIN
    -- Get natural gas energy source ID (created in 004-production-seus.sql)
    SELECT id INTO v_natural_gas_id FROM energy_sources WHERE name = 'natural_gas';
    
    IF v_natural_gas_id IS NULL THEN
        RAISE NOTICE 'Natural gas energy source not found, skipping...';
        RETURN;
    END IF;
    
    -- Insert natural gas features (for when meters are installed)
    INSERT INTO energy_source_features (energy_source_id, feature_name, data_type, source_table, source_column, aggregation_function, description) VALUES
    
    -- Natural gas readings (when natural_gas_readings hypertable exists)
    (v_natural_gas_id, 'consumption_m3', 'numeric', 'natural_gas_readings', 'consumption_m3', 'SUM', 'Total natural gas consumed (m³)'),
    (v_natural_gas_id, 'avg_flow_rate_m3h', 'numeric', 'natural_gas_readings', 'flow_rate_m3h', 'AVG', 'Average gas flow rate (m³/h)'),
    (v_natural_gas_id, 'max_flow_rate_m3h', 'numeric', 'natural_gas_readings', 'flow_rate_m3h', 'MAX', 'Peak gas flow rate (m³/h)'),
    (v_natural_gas_id, 'avg_pressure_bar', 'numeric', 'natural_gas_readings', 'pressure_bar', 'AVG', 'Average gas supply pressure (bar)'),
    (v_natural_gas_id, 'avg_gas_temp_c', 'numeric', 'natural_gas_readings', 'temperature_c', 'AVG', 'Average gas temperature (°C)'),
    (v_natural_gas_id, 'avg_calorific_value', 'numeric', 'natural_gas_readings', 'calorific_value_kwh_m3', 'AVG', 'Average gas energy content (kWh/m³)'),
    
    -- Environmental features (boilers/furnaces are weather-sensitive)
    (v_natural_gas_id, 'outdoor_temp_c', 'numeric', 'environmental_data', 'outdoor_temp_c', 'AVG', 'Average outdoor temperature (°C)'),
    (v_natural_gas_id, 'heating_degree_days', 'numeric', 'environmental_data', 'outdoor_temp_c', 'CUSTOM', 'Heating degree days - primary driver for boiler gas consumption'),
    
    -- Production features (if gas used in production processes)
    (v_natural_gas_id, 'production_count', 'numeric', 'production_data', 'production_count', 'AVG', 'Average production units (for process heating load)')
    
    ON CONFLICT (energy_source_id, feature_name) DO NOTHING;

        UPDATE energy_source_features
        SET is_regression_feature = false
        WHERE energy_source_id = v_natural_gas_id
            AND feature_name = 'consumption_m3';
    
    RAISE NOTICE '✓ Natural gas features seeded: % features', (SELECT COUNT(*) FROM energy_source_features WHERE energy_source_id = v_natural_gas_id);
END $$;

-- ============================================================================
-- Seed Steam Features (Phase 2 Ready)
-- ============================================================================
\echo ''
\echo 'Seeding steam features (Phase 2 ready)...'

DO $$
DECLARE
    v_steam_id UUID;
BEGIN
    SELECT id INTO v_steam_id FROM energy_sources WHERE name = 'steam';
    
    IF v_steam_id IS NULL THEN
        RAISE NOTICE 'Steam energy source not found, skipping...';
        RETURN;
    END IF;
    
    INSERT INTO energy_source_features (energy_source_id, feature_name, data_type, source_table, source_column, aggregation_function, description) VALUES
    
    -- Steam readings
    (v_steam_id, 'consumption_kg', 'numeric', 'steam_readings', 'consumption_kg', 'SUM', 'Total steam consumed (kg)'),
    (v_steam_id, 'avg_flow_rate_kg_h', 'numeric', 'steam_readings', 'flow_rate_kg_h', 'AVG', 'Average steam mass flow rate (kg/h)'),
    (v_steam_id, 'avg_pressure_bar', 'numeric', 'steam_readings', 'pressure_bar', 'AVG', 'Average steam pressure (bar)'),
    (v_steam_id, 'avg_temperature_c', 'numeric', 'steam_readings', 'temperature_c', 'AVG', 'Average steam temperature (°C)'),
    (v_steam_id, 'avg_enthalpy_kj_kg', 'numeric', 'steam_readings', 'enthalpy_kj_kg', 'AVG', 'Average steam energy content (kJ/kg)'),
    
    -- Production features
    (v_steam_id, 'production_count', 'numeric', 'production_data', 'production_count', 'AVG', 'Average production units (steam process load)')
    
    ON CONFLICT (energy_source_id, feature_name) DO NOTHING;

        UPDATE energy_source_features
        SET is_regression_feature = false
        WHERE energy_source_id = v_steam_id
            AND feature_name = 'consumption_kg';
    
    RAISE NOTICE '✓ Steam features seeded: % features', (SELECT COUNT(*) FROM energy_source_features WHERE energy_source_id = v_steam_id);
END $$;

-- ============================================================================
-- Seed Compressed Air Features (Phase 2 Ready)
-- ============================================================================
\echo ''
\echo 'Seeding compressed air features (Phase 2 ready)...'

DO $$
DECLARE
    v_compressed_air_id UUID;
BEGIN
    SELECT id INTO v_compressed_air_id FROM energy_sources WHERE name = 'compressed_air';
    
    IF v_compressed_air_id IS NULL THEN
        RAISE NOTICE 'Compressed air energy source not found, skipping...';
        RETURN;
    END IF;
    
    -- NOTE: This tracks compressed air END-USE consumption
    -- Compressor ELECTRICITY consumption is tracked separately in energy_readings
    -- Cross-energy efficiency: Compressor kWh / Air produced Nm³ = Specific Power
    
    INSERT INTO energy_source_features (energy_source_id, feature_name, data_type, source_table, source_column, aggregation_function, description) VALUES
    
    -- Compressed air end-use readings
    (v_compressed_air_id, 'consumption_m3', 'numeric', 'compressed_air_end_use_readings', 'consumption_m3', 'SUM', 'Total compressed air consumed by end-use equipment (m³)'),
    (v_compressed_air_id, 'avg_flow_rate_m3h', 'numeric', 'compressed_air_end_use_readings', 'flow_rate_m3h', 'AVG', 'Average air consumption rate (m³/h)'),
    (v_compressed_air_id, 'avg_pressure_bar', 'numeric', 'compressed_air_end_use_readings', 'pressure_bar', 'AVG', 'Average air pressure at point of use (bar)'),
    (v_compressed_air_id, 'avg_dewpoint_c', 'numeric', 'compressed_air_end_use_readings', 'dewpoint_c', 'AVG', 'Average air dewpoint - indicates air quality (°C)'),
    
    -- Production features
    (v_compressed_air_id, 'production_count', 'numeric', 'production_data', 'production_count', 'AVG', 'Average production units (pneumatic equipment load)')
    
    ON CONFLICT (energy_source_id, feature_name) DO NOTHING;

        UPDATE energy_source_features
        SET is_regression_feature = false
        WHERE energy_source_id = v_compressed_air_id
            AND feature_name = 'consumption_m3';
    
    RAISE NOTICE '✓ Compressed air features seeded: % features', (SELECT COUNT(*) FROM energy_source_features WHERE energy_source_id = v_compressed_air_id);
END $$;

\echo ''
\echo '=========================================='
\echo 'Migration 006 Complete!'
\echo ''
\echo 'Summary:'
SELECT 
    es.name as energy_source,
    COUNT(esf.id) as features_count
FROM energy_sources es
LEFT JOIN energy_source_features esf ON es.id = esf.energy_source_id
GROUP BY es.name
ORDER BY es.name;
\echo ''
\echo 'System now supports DYNAMIC feature discovery!'
\echo 'Next: Create feature_discovery.py service to query this table'
\echo '=========================================='
\echo ''
