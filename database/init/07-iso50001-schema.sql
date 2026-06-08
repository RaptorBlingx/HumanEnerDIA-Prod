-- ============================================================================
-- EnMS - ISO 50001 EnPI Database Schema
-- Migration: 003-iso50001-schema.sql
-- ============================================================================
-- Purpose: Add tables for ISO 50001 compliance reporting (parallel to real-time monitoring)
-- Author: EnMS Team
-- Date: 2025-10-22
-- Status: Ready for deployment
-- ============================================================================

\echo ''
\echo '========================================='
\echo 'Starting ISO 50001 EnPI Schema Migration'
\echo '========================================='
\echo ''

-- ============================================================================
-- 1. ENERGY SOURCES TABLE
-- ============================================================================
-- Tracks different energy types (electricity, gas, compressed air, steam)
-- Required by ISO 50001 for multi-source SEU management
-- ============================================================================

\echo '→ Creating energy_sources table...'

CREATE TABLE IF NOT EXISTS energy_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) UNIQUE NOT NULL,
    unit VARCHAR(20) NOT NULL,
    cost_per_unit DECIMAL(10,4),
    carbon_factor DECIMAL(10,6),
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_energy_sources_active ON energy_sources(is_active);

\echo '✓ energy_sources table created'

-- ============================================================================
-- 2. SEUS TABLE (Significant Energy Users)
-- ============================================================================
-- ISO 50001 requirement: Group machines by energy significance
-- Stores annual baseline regression models for compliance reporting
-- Different from energy_baselines (which is for real-time predictions)
-- ============================================================================

\echo '→ Creating seus table...'

CREATE TABLE IF NOT EXISTS seus (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    energy_source_id UUID REFERENCES energy_sources(id) ON DELETE RESTRICT NOT NULL,
    machine_ids UUID[] NOT NULL,
    
    -- Baseline configuration
    baseline_year INTEGER,
    baseline_start_date DATE,
    baseline_end_date DATE,
    
    -- Regression model (stored as JSONB for flexibility)
    regression_coefficients JSONB,
    intercept DECIMAL(15,6),
    feature_columns TEXT[],
    
    -- Model performance metrics
    r_squared DECIMAL(6,4),
    rmse DECIMAL(15,4),
    mae DECIMAL(15,4),
    
    -- Metadata
    trained_at TIMESTAMPTZ,
    trained_by VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT seus_baseline_year_check CHECK (baseline_year >= 2020 AND baseline_year <= 2100),
    CONSTRAINT seus_machine_ids_not_empty CHECK (array_length(machine_ids, 1) > 0)
);

CREATE INDEX IF NOT EXISTS idx_seus_energy_source ON seus(energy_source_id);
CREATE INDEX IF NOT EXISTS idx_seus_active ON seus(is_active);
CREATE INDEX IF NOT EXISTS idx_seus_baseline_year ON seus(baseline_year);

\echo '✓ seus table created'

-- ============================================================================
-- 3. SEU ENERGY PERFORMANCE TABLE
-- ============================================================================
-- Tracks quarterly/annual energy performance vs baseline
-- Core of ISO 50001 EnPI (Energy Performance Indicator) reporting
-- ============================================================================

\echo '→ Creating seu_energy_performance table...'

CREATE TABLE IF NOT EXISTS seu_energy_performance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seu_id UUID REFERENCES seus(id) ON DELETE CASCADE NOT NULL,
    
    -- Reporting period
    report_period VARCHAR(20) NOT NULL,  -- e.g., '2025-Q1', '2025-annual'
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    baseline_year INTEGER NOT NULL,
    
    -- Energy consumption data
    actual_consumption DECIMAL(15,4) NOT NULL,
    expected_consumption DECIMAL(15,4) NOT NULL,
    
    -- Performance metrics
    deviation_kwh DECIMAL(15,4),
    deviation_percent DECIMAL(6,2),
    compliance_status VARCHAR(20),  -- 'compliant', 'warning', 'critical'
    
    -- Additional context
    notes TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    generated_by VARCHAR(100),
    
    -- Ensure unique reports per SEU per period
    UNIQUE(seu_id, report_period),
    
    -- Constraints
    CONSTRAINT seu_perf_compliance_status_check 
        CHECK (compliance_status IN ('compliant', 'warning', 'critical', NULL))
);

CREATE INDEX IF NOT EXISTS idx_seu_performance_period ON seu_energy_performance(seu_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_seu_performance_baseline ON seu_energy_performance(baseline_year);
CREATE INDEX IF NOT EXISTS idx_seu_performance_compliance ON seu_energy_performance(compliance_status);

\echo '✓ seu_energy_performance table created'

-- ============================================================================
-- 4. SEED INITIAL DATA
-- ============================================================================
-- Populate energy sources with standard industrial energy types
-- ============================================================================

\echo ''
\echo '→ Seeding energy sources...'

INSERT INTO energy_sources (name, unit, cost_per_unit, carbon_factor, description) VALUES
    ('electricity', 'kWh', 0.15, 0.450000, 'Electrical power from grid'),
    ('natural_gas', 'm³', 0.50, 2.030000, 'Natural gas for heating/boilers'),
    ('compressed_air', 'Nm³', 0.03, 0.120000, 'Compressed air for pneumatic systems'),
    ('steam', 'kg', 0.08, 0.350000, 'Process steam')
ON CONFLICT (name) DO NOTHING;

\echo '✓ Energy sources seeded'

-- ============================================================================
-- 5. HELPER FUNCTIONS
-- ============================================================================
-- SQL functions for common ISO 50001 calculations
-- ============================================================================

\echo ''
\echo '→ Creating helper functions...'

-- Function: Calculate SEU total energy for a period
CREATE OR REPLACE FUNCTION get_seu_energy(
    p_seu_id UUID,
    p_start_date TIMESTAMPTZ,
    p_end_date TIMESTAMPTZ
) RETURNS DECIMAL AS $$
DECLARE
    v_machine_ids UUID[];
    v_total_energy DECIMAL;
BEGIN
    -- Get machine IDs from SEU
    SELECT machine_ids INTO v_machine_ids
    FROM seus
    WHERE id = p_seu_id;
    
    IF v_machine_ids IS NULL THEN
        RAISE EXCEPTION 'SEU not found: %', p_seu_id;
    END IF;
    
    -- Sum energy from all machines in SEU
    SELECT COALESCE(SUM(total_energy_kwh), 0)
    INTO v_total_energy
    FROM energy_readings_1hour
    WHERE machine_id = ANY(v_machine_ids)
      AND bucket >= p_start_date
      AND bucket <= p_end_date;
    
    RETURN v_total_energy;
END;
$$ LANGUAGE plpgsql;

\echo '  ✓ get_seu_energy() function created'

-- Function: Determine compliance status from deviation percentage
CREATE OR REPLACE FUNCTION get_deviation_status(
    p_deviation_percent DECIMAL
) RETURNS TEXT AS $$
BEGIN
    IF abs(p_deviation_percent) <= 3.0 THEN
        RETURN 'compliant';
    ELSIF abs(p_deviation_percent) <= 5.0 THEN
        RETURN 'warning';
    ELSE
        RETURN 'critical';
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

\echo '  ✓ get_deviation_status() function created'

-- Function: Get SEU daily aggregated data for baseline training
CREATE OR REPLACE FUNCTION get_seu_daily_aggregates(
    p_seu_id UUID,
    p_start_date DATE,
    p_end_date DATE
) RETURNS TABLE (
    day DATE,
    total_energy_kwh DECIMAL,
    avg_production_count DECIMAL,
    avg_temp_c DECIMAL,
    avg_operating_hours DECIMAL
) AS $$
DECLARE
    v_machine_ids UUID[];
BEGIN
    -- Get machine IDs from SEU
    SELECT machine_ids INTO v_machine_ids
    FROM seus
    WHERE id = p_seu_id;
    
    IF v_machine_ids IS NULL THEN
        RAISE EXCEPTION 'SEU not found: %', p_seu_id;
    END IF;
    
    -- Aggregate data by day across all SEU machines
    RETURN QUERY
    SELECT 
        er.bucket::DATE as day,
        SUM(er.total_energy_kwh) as total_energy_kwh,
        AVG(pd.total_production_count) as avg_production_count,
        AVG(ed.avg_machine_temp_c) as avg_temp_c,
        COUNT(DISTINCT time_bucket('1 hour', er.bucket)) as avg_operating_hours
    FROM energy_readings_1hour er
    LEFT JOIN production_data_1hour pd 
        ON er.machine_id = pd.machine_id 
        AND er.bucket = pd.bucket
    LEFT JOIN environmental_data_1hour ed 
        ON er.machine_id = ed.machine_id 
        AND er.bucket = ed.bucket
    WHERE er.machine_id = ANY(v_machine_ids)
      AND er.bucket::DATE >= p_start_date
      AND er.bucket::DATE <= p_end_date
    GROUP BY er.bucket::DATE
    ORDER BY day;
END;
$$ LANGUAGE plpgsql;

\echo '  ✓ get_seu_daily_aggregates() function created'

-- ============================================================================
-- 6. UPDATE TRIGGERS
-- ============================================================================
-- Auto-update updated_at timestamps
-- ============================================================================

\echo ''
\echo '→ Creating update triggers...'

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_energy_sources_updated_at
    BEFORE UPDATE ON energy_sources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_seus_updated_at
    BEFORE UPDATE ON seus
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

\echo '✓ Update triggers created'

-- ============================================================================
-- 7. VERIFICATION
-- ============================================================================

\echo ''
\echo '→ Verifying schema...'

DO $$
DECLARE
    v_table_count INTEGER;
    v_source_count INTEGER;
BEGIN
    -- Check tables exist
    SELECT COUNT(*) INTO v_table_count
    FROM information_schema.tables
    WHERE table_name IN ('energy_sources', 'seus', 'seu_energy_performance');
    
    IF v_table_count != 3 THEN
        RAISE EXCEPTION 'Table creation failed. Expected 3 tables, found %', v_table_count;
    END IF;
    
    -- Check seed data
    SELECT COUNT(*) INTO v_source_count FROM energy_sources;
    
    IF v_source_count < 4 THEN
        RAISE EXCEPTION 'Seed data incomplete. Expected 4+ energy sources, found %', v_source_count;
    END IF;
    
    RAISE NOTICE 'Verification passed: % tables, % energy sources', v_table_count, v_source_count;
END;
$$;

\echo '✓ Schema verification passed'

-- ============================================================================
-- 8. GRANT PERMISSIONS
-- ============================================================================
-- Grant access to analytics service user
-- ============================================================================

\echo ''
\echo '→ Granting permissions...'

GRANT SELECT, INSERT, UPDATE, DELETE ON energy_sources TO CURRENT_USER;
GRANT SELECT, INSERT, UPDATE, DELETE ON seus TO CURRENT_USER;
GRANT SELECT, INSERT, UPDATE, DELETE ON seu_energy_performance TO CURRENT_USER;

\echo '✓ Permissions granted'

-- ============================================================================
-- MIGRATION SUMMARY
-- ============================================================================

\echo ''
\echo '========================================='
\echo 'ISO 50001 EnPI Schema Migration Complete'
\echo '========================================='
\echo ''
\echo 'Tables created:'
\echo '  • energy_sources (4 types seeded)'
\echo '  • seus (SEU management)'
\echo '  • seu_energy_performance (EnPI tracking)'
\echo ''
\echo 'Functions created:'
\echo '  • get_seu_energy(seu_id, start, end)'
\echo '  • get_deviation_status(deviation_percent)'
\echo '  • get_seu_daily_aggregates(seu_id, start, end)'
\echo ''
\echo 'Next steps:'
\echo '  1. Restart analytics service: docker-compose restart analytics'
\echo '  2. Create test SEU via API'
\echo '  3. Train baseline on available data'
\echo '  4. Generate performance report'
\echo ''
\echo '========================================='
