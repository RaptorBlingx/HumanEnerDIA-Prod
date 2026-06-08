-- ============================================================================
-- Migration 005: Production Enhancements (Real-World ISO 50001 Features)
-- ============================================================================
-- Purpose: Add columns for CUSUM, degree-days, uncertainty, data quality
-- Standard: ISO 50001:2018 + industry best practices
-- Author: EnMS Team
-- Date: October 22, 2025
-- ============================================================================

\echo ''
\echo '╔══════════════════════════════════════════════════════════════════════════╗'
\echo '║  Migration 005: Production Enhancements                                 ║'
\echo '║  Features: CUSUM, Degree-Days, Uncertainty, Data Quality                ║'
\echo '╚══════════════════════════════════════════════════════════════════════════╝'
\echo ''

BEGIN;

-- ============================================================================
-- 1. Enhance seu_energy_performance table
-- ============================================================================

\echo '→ Adding production columns to seu_energy_performance...'

-- Degree-days for HVAC normalization (ISO 50006 standard)
ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS heating_degree_days DECIMAL(10,2) DEFAULT NULL;

ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS cooling_degree_days DECIMAL(10,2) DEFAULT NULL;

COMMENT ON COLUMN seu_energy_performance.heating_degree_days IS 'HDD = Σ max(0, 18°C - T_daily_avg). Used for HVAC baseline normalization per ISO 50006 standard.';

COMMENT ON COLUMN seu_energy_performance.cooling_degree_days IS 'CDD = Σ max(0, T_daily_avg - 18°C). Used for HVAC baseline normalization per ISO 50006 standard.';

-- CUSUM tracking (cumulative sum for trend detection)
ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS cusum_deviation DECIMAL(10,2) DEFAULT 0.0;

COMMENT ON COLUMN seu_energy_performance.cusum_deviation IS 'Cumulative sum of monthly deviations. CUSUM[n] = CUSUM[n-1] + deviation[n]. Alert if |CUSUM| > 50% (persistent 5-month trend).';

-- Uncertainty quantification (95% confidence intervals)
ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS expected_lower_95ci DECIMAL(15,4) DEFAULT NULL;

ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS expected_upper_95ci DECIMAL(15,4) DEFAULT NULL;

COMMENT ON COLUMN seu_energy_performance.expected_lower_95ci IS 'Lower bound of 95% prediction interval. Formula: Expected - 1.96×RMSE. Deviation below this is statistically significant.';

COMMENT ON COLUMN seu_energy_performance.expected_upper_95ci IS 'Upper bound of 95% prediction interval. Formula: Expected + 1.96×RMSE. Deviation above this is statistically significant.';

-- Data quality scoring
ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS data_quality_score DECIMAL(3,2) DEFAULT NULL;

ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS data_completeness_percent DECIMAL(5,2) DEFAULT NULL;

COMMENT ON COLUMN seu_energy_performance.data_quality_score IS 'Overall data quality score (0-1). Factors: completeness, outliers, correlation. Score < 0.90 triggers warning in reports.';

COMMENT ON COLUMN seu_energy_performance.data_completeness_percent IS 'Percentage of expected data points received. 100% = no missing data. < 95% triggers data quality warning.';

-- EnPI value (normalized energy performance indicator)
ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS enpi_value DECIMAL(15,6) DEFAULT NULL;

ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS enpi_unit VARCHAR(50) DEFAULT NULL;

COMMENT ON COLUMN seu_energy_performance.enpi_value IS 'Energy Performance Indicator (ISO 50001 requirement). Examples: kWh/ton (compressors), kWh/degree-day (HVAC), kWh/operating-hour (motors).';

COMMENT ON COLUMN seu_energy_performance.enpi_unit IS 'Unit of EnPI metric. Examples: "kWh/ton", "kWh/degree-day", "kWh/operating-hour".';

-- Product mix factor (multi-product facilities)
ALTER TABLE seu_energy_performance 
ADD COLUMN IF NOT EXISTS product_mix_factor DECIMAL(8,4) DEFAULT 1.0000;

COMMENT ON COLUMN seu_energy_performance.product_mix_factor IS 'Adjustment factor for product mix changes. 1.0 = baseline mix. Used when facility produces multiple products with different energy intensities.';

\echo '✓ seu_energy_performance enhanced (11 new columns)'
\echo ''

-- ============================================================================
-- 2. Create baseline_adjustments table (ISO 50001 Clause 6.6)
-- ============================================================================

\echo '→ Creating baseline_adjustments table...'

CREATE TABLE IF NOT EXISTS baseline_adjustments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seu_id UUID NOT NULL REFERENCES seus(id) ON DELETE CASCADE,
    adjustment_date DATE NOT NULL,
    adjustment_type VARCHAR(50) NOT NULL,
    adjustment_reason TEXT NOT NULL,
    old_baseline_year INTEGER,
    new_baseline_year INTEGER,
    adjustment_factor DECIMAL(8,4) DEFAULT 1.0000,
    approved_by VARCHAR(100),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_adjustment_type CHECK (
        adjustment_type IN (
            'equipment_upgrade',
            'process_change',
            'operating_schedule_change',
            'production_capacity_change',
            'energy_source_change',
            'control_system_upgrade',
            'maintenance_impact',
            'other'
        )
    ),
    CONSTRAINT chk_adjustment_factor CHECK (adjustment_factor > 0 AND adjustment_factor < 10)
);

CREATE INDEX idx_baseline_adj_seu ON baseline_adjustments(seu_id, adjustment_date DESC);
CREATE INDEX idx_baseline_adj_date ON baseline_adjustments(adjustment_date DESC);
CREATE INDEX idx_baseline_adj_type ON baseline_adjustments(adjustment_type);

COMMENT ON TABLE baseline_adjustments IS 'ISO 50001 Clause 6.6 requires documented baseline adjustments for significant changes. Examples: equipment upgrades, process changes, operating schedule changes. Auditors WILL ask for this documentation.';

COMMENT ON COLUMN baseline_adjustments.adjustment_type IS 'Type of significant change requiring baseline adjustment. Must be justified and approved.';

COMMENT ON COLUMN baseline_adjustments.adjustment_factor IS 'Multiplicative adjustment factor. Example: 0.85 = 15% improvement after equipment upgrade.';

\echo '✓ baseline_adjustments table created'
\echo ''

-- ============================================================================
-- 3. Create data_quality_log table
-- ============================================================================

\echo '→ Creating data_quality_log table...'

CREATE TABLE IF NOT EXISTS data_quality_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    check_date DATE NOT NULL,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    missing_data_percent DECIMAL(5,2) DEFAULT 0.00,
    outlier_count INTEGER DEFAULT 0,
    correlation_score DECIMAL(3,2) DEFAULT NULL,
    overall_score DECIMAL(3,2) DEFAULT NULL,
    issues TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_missing_data CHECK (missing_data_percent >= 0 AND missing_data_percent <= 100),
    CONSTRAINT chk_outlier_count CHECK (outlier_count >= 0),
    CONSTRAINT chk_correlation_score CHECK (correlation_score IS NULL OR (correlation_score >= -1 AND correlation_score <= 1)),
    CONSTRAINT chk_overall_score CHECK (overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 1))
);

CREATE INDEX idx_data_quality_date ON data_quality_log(check_date DESC);
CREATE INDEX idx_data_quality_machine ON data_quality_log(machine_id, check_date);
CREATE INDEX idx_data_quality_score ON data_quality_log(overall_score) WHERE overall_score < 0.90;

COMMENT ON TABLE data_quality_log IS 'Daily data quality checks for each machine. Real factories have bad data: sensor failures, communication gaps, outliers. ISO 50001 auditors check data quality procedures.';

COMMENT ON COLUMN data_quality_log.missing_data_percent IS 'Percentage of expected data points missing. Target: < 5%. Above 10% triggers alert.';

COMMENT ON COLUMN data_quality_log.correlation_score IS 'Correlation between energy and production. Target: > 0.7 for production-dependent equipment. Low correlation indicates data quality issues.';

COMMENT ON COLUMN data_quality_log.overall_score IS 'Combined data quality score (0-1). Factors: completeness, outliers, correlation. Score < 0.90 excludes data from baseline training.';

\echo '✓ data_quality_log table created'
\echo ''

-- ============================================================================
-- 4. Create Phase 2 placeholder tables (Multi-Energy Future)
-- ============================================================================

\echo '→ Creating Phase 2 placeholder comments...'

-- Future tables for multi-energy tracking (Phase 2)
COMMENT ON TABLE energy_sources IS 'Phase 1: electricity tracked via energy_readings. Phase 2: Add natural_gas_readings, compressed_air_readings, steam_readings tables with similar structure.';

-- Phase 2 table structure examples (for future implementation):
--
-- CREATE TABLE natural_gas_readings (
--     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     time TIMESTAMPTZ NOT NULL,
--     machine_id UUID REFERENCES machines(id),
--     flow_rate_m3_h DECIMAL(10,3),
--     consumption_m3 DECIMAL(15,4),
--     pressure_bar DECIMAL(6,2),
--     temperature_c DECIMAL(5,2),
--     created_at TIMESTAMPTZ DEFAULT NOW()
-- );
-- SELECT create_hypertable('natural_gas_readings', 'time');
--
-- CREATE TABLE compressed_air_readings (
--     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     time TIMESTAMPTZ NOT NULL,
--     machine_id UUID REFERENCES machines(id),
--     flow_rate_nm3_min DECIMAL(10,3),
--     consumption_nm3 DECIMAL(15,4),
--     pressure_bar DECIMAL(6,2),
--     temperature_c DECIMAL(5,2),
--     created_at TIMESTAMPTZ DEFAULT NOW()
-- );
-- SELECT create_hypertable('compressed_air_readings', 'time');
--
-- CREATE TABLE steam_readings (
--     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     time TIMESTAMPTZ NOT NULL,
--     machine_id UUID REFERENCES machines(id),
--     flow_rate_kg_h DECIMAL(10,3),
--     consumption_kg DECIMAL(15,4),
--     pressure_bar DECIMAL(6,2),
--     temperature_c DECIMAL(5,2),
--     enthalpy_kj_kg DECIMAL(8,2),
--     created_at TIMESTAMPTZ DEFAULT NOW()
-- );
-- SELECT create_hypertable('steam_readings', 'time');

\echo '✓ Phase 2 placeholder comments added'
\echo ''

-- ============================================================================
-- 5. Update triggers
-- ============================================================================

\echo '→ Adding triggers for updated_at columns...'

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add trigger to baseline_adjustments
DROP TRIGGER IF EXISTS update_baseline_adjustments_updated_at ON baseline_adjustments;
CREATE TRIGGER update_baseline_adjustments_updated_at
    BEFORE UPDATE ON baseline_adjustments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

\echo '✓ Triggers created'
\echo ''

-- ============================================================================
-- Validation & Summary
-- ============================================================================

DO $$
DECLARE
    v_perf_columns INTEGER;
    v_adjustment_count INTEGER;
    v_quality_count INTEGER;
BEGIN
    -- Count new columns in seu_energy_performance
    SELECT COUNT(*) INTO v_perf_columns
    FROM information_schema.columns
    WHERE table_name = 'seu_energy_performance'
    AND column_name IN (
        'heating_degree_days', 'cooling_degree_days', 'cusum_deviation',
        'expected_lower_95ci', 'expected_upper_95ci',
        'data_quality_score', 'data_completeness_percent',
        'enpi_value', 'enpi_unit', 'product_mix_factor'
    );
    
    -- Count tables
    SELECT COUNT(*) INTO v_adjustment_count FROM baseline_adjustments;
    SELECT COUNT(*) INTO v_quality_count FROM data_quality_log;
    
    RAISE NOTICE ' ';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE 'Migration 005 Summary:';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE 'seu_energy_performance: % new columns added', v_perf_columns;
    RAISE NOTICE 'baseline_adjustments: % records', v_adjustment_count;
    RAISE NOTICE 'data_quality_log: % records', v_quality_count;
    RAISE NOTICE ' ';
    RAISE NOTICE 'Features added:';
    RAISE NOTICE '  ✓ CUSUM tracking (trend detection)';
    RAISE NOTICE '  ✓ Degree-day normalization (HVAC)';
    RAISE NOTICE '  ✓ Uncertainty quantification (95 percent CI)';
    RAISE NOTICE '  ✓ Data quality scoring';
    RAISE NOTICE '  ✓ EnPI calculations (ISO 50001)';
    RAISE NOTICE '  ✓ Baseline adjustment tracking';
    RAISE NOTICE '  ✓ Product mix factors';
    RAISE NOTICE '  ✓ Phase 2 preparation (multi-energy)';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE ' ';
    
    IF v_perf_columns < 10 THEN
        RAISE WARNING 'Expected at least 10 new columns, found %', v_perf_columns;
    END IF;
END $$;

COMMIT;

\echo ''
\echo '✅ Migration 005 completed successfully!'
\echo '   Next step: Update PostgreSQL functions for degree-day calculation'
\echo '   Phase 2: Multi-energy tracking ready when meters installed'
\echo ''
