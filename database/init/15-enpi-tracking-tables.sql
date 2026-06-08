-- Migration 011: Create EnPI (Energy Performance Indicator) Tracking Tables
-- Phase 3 Milestone 3.1: ISO 50001 Compliance Engine
-- Created: November 7, 2025

-- ============================================================================
-- EnPI Baseline Periods
-- ============================================================================
-- Stores baseline year data for SEUs (ISO 50001 requirement)
-- Used to calculate expected energy consumption based on production

CREATE TABLE IF NOT EXISTS enpi_baselines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seu_id UUID NOT NULL REFERENCES seus(id) ON DELETE CASCADE,
    baseline_year INTEGER NOT NULL CHECK (baseline_year >= 2020 AND baseline_year <= 2100),
    baseline_start_date DATE NOT NULL,
    baseline_end_date DATE NOT NULL,
    
    -- Energy metrics for baseline period
    baseline_energy_kwh NUMERIC(15, 4) NOT NULL CHECK (baseline_energy_kwh >= 0),
    baseline_production_units INTEGER CHECK (baseline_production_units >= 0),
    baseline_operating_hours NUMERIC(10, 2) CHECK (baseline_operating_hours >= 0),
    
    -- Specific Energy Consumption (SEC) = Energy / Production
    baseline_sec NUMERIC(10, 6) CHECK (baseline_sec >= 0),  -- kWh per unit
    
    -- Environmental factors (for normalization)
    baseline_avg_temp_c NUMERIC(5, 2),
    baseline_degree_days NUMERIC(10, 2),
    
    -- Metadata
    is_active BOOLEAN DEFAULT true,
    notes TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT enpi_baselines_dates_valid CHECK (baseline_end_date > baseline_start_date),
    CONSTRAINT enpi_baselines_unique_seu_year UNIQUE (seu_id, baseline_year)
);

-- Indexes for EnPI baselines
CREATE INDEX IF NOT EXISTS idx_enpi_baselines_seu ON enpi_baselines(seu_id);
CREATE INDEX IF NOT EXISTS idx_enpi_baselines_year ON enpi_baselines(baseline_year);
CREATE INDEX IF NOT EXISTS idx_enpi_baselines_active ON enpi_baselines(is_active);

-- ============================================================================
-- EnPI Performance Tracking
-- ============================================================================
-- Tracks actual vs expected energy performance for each reporting period
-- Used for ISO 50001 compliance reporting and continuous improvement

CREATE TABLE IF NOT EXISTS enpi_performance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seu_id UUID NOT NULL REFERENCES seus(id) ON DELETE CASCADE,
    baseline_id UUID REFERENCES enpi_baselines(id) ON DELETE SET NULL,
    
    -- Reporting period
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    period_type VARCHAR(20) CHECK (period_type IN ('monthly', 'quarterly', 'annual')),
    
    -- Actual performance
    actual_energy_kwh NUMERIC(15, 4) NOT NULL CHECK (actual_energy_kwh >= 0),
    actual_production_units INTEGER CHECK (actual_production_units >= 0),
    actual_operating_hours NUMERIC(10, 2) CHECK (actual_operating_hours >= 0),
    actual_sec NUMERIC(10, 6) CHECK (actual_sec >= 0),
    
    -- Expected performance (based on baseline + normalization)
    expected_energy_kwh NUMERIC(15, 4) CHECK (expected_energy_kwh >= 0),
    expected_sec NUMERIC(10, 6) CHECK (expected_sec >= 0),
    
    -- Performance metrics
    deviation_kwh NUMERIC(15, 4),  -- Can be negative (savings)
    deviation_percent NUMERIC(6, 2),  -- Can be negative (savings)
    cumulative_savings_kwh NUMERIC(15, 4),  -- Year-to-date savings
    cumulative_savings_usd NUMERIC(12, 2),  -- Year-to-date cost savings
    
    -- ISO 50001 status
    iso_status VARCHAR(50) CHECK (iso_status IN ('excellent', 'on_track', 'requires_attention', 'critical')),
    compliance_notes TEXT,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT enpi_performance_dates_valid CHECK (period_end > period_start)
);

-- Indexes for EnPI performance
CREATE INDEX IF NOT EXISTS idx_enpi_performance_seu ON enpi_performance(seu_id);
CREATE INDEX IF NOT EXISTS idx_enpi_performance_baseline ON enpi_performance(baseline_id);
CREATE INDEX IF NOT EXISTS idx_enpi_performance_period ON enpi_performance(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_enpi_performance_status ON enpi_performance(iso_status);

-- ============================================================================
-- Energy Reduction Targets (ISO 50001 requirement)
-- ============================================================================
-- Stores energy reduction targets and tracks progress

CREATE TABLE IF NOT EXISTS energy_targets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seu_id UUID REFERENCES seus(id) ON DELETE CASCADE,
    factory_id UUID REFERENCES factories(id) ON DELETE CASCADE,
    target_type VARCHAR(20) CHECK (target_type IN ('seu', 'factory')),
    
    -- Target definition
    target_year INTEGER NOT NULL CHECK (target_year >= 2020 AND target_year <= 2100),
    target_description TEXT NOT NULL,
    
    -- Baseline reference
    baseline_year INTEGER CHECK (baseline_year >= 2020 AND baseline_year <= 2100),
    baseline_energy_kwh NUMERIC(15, 4) CHECK (baseline_energy_kwh >= 0),
    
    -- Target values
    target_reduction_percent NUMERIC(5, 2) NOT NULL CHECK (target_reduction_percent >= 0 AND target_reduction_percent <= 100),
    target_energy_kwh NUMERIC(15, 4) CHECK (target_energy_kwh >= 0),
    target_savings_kwh NUMERIC(15, 4) CHECK (target_savings_kwh >= 0),
    
    -- Progress tracking
    current_energy_kwh NUMERIC(15, 4),
    current_savings_kwh NUMERIC(15, 4),
    progress_percent NUMERIC(5, 2),
    
    -- Status
    status VARCHAR(20) CHECK (status IN ('active', 'achieved', 'missed', 'cancelled')),
    deadline DATE,
    
    -- Metadata
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT energy_targets_seu_or_factory CHECK (
        (seu_id IS NOT NULL AND factory_id IS NULL) OR 
        (seu_id IS NULL AND factory_id IS NOT NULL)
    )
);

-- Indexes for energy targets
CREATE INDEX IF NOT EXISTS idx_energy_targets_seu ON energy_targets(seu_id);
CREATE INDEX IF NOT EXISTS idx_energy_targets_factory ON energy_targets(factory_id);
CREATE INDEX IF NOT EXISTS idx_energy_targets_year ON energy_targets(target_year);
CREATE INDEX IF NOT EXISTS idx_energy_targets_status ON energy_targets(status);

-- ============================================================================
-- Triggers for updated_at timestamps
-- ============================================================================

CREATE OR REPLACE FUNCTION update_enpi_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_enpi_baselines_updated_at
    BEFORE UPDATE ON enpi_baselines
    FOR EACH ROW
    EXECUTE FUNCTION update_enpi_updated_at();

CREATE TRIGGER update_enpi_performance_updated_at
    BEFORE UPDATE ON enpi_performance
    FOR EACH ROW
    EXECUTE FUNCTION update_enpi_updated_at();

CREATE TRIGGER update_energy_targets_updated_at
    BEFORE UPDATE ON energy_targets
    FOR EACH ROW
    EXECUTE FUNCTION update_enpi_updated_at();

-- ============================================================================
-- Comments for documentation
-- ============================================================================

COMMENT ON TABLE enpi_baselines IS 'ISO 50001 EnPI baseline periods for SEUs';
COMMENT ON TABLE enpi_performance IS 'EnPI performance tracking vs baseline';
COMMENT ON TABLE energy_targets IS 'Energy reduction targets and progress tracking';

COMMENT ON COLUMN enpi_baselines.baseline_sec IS 'Specific Energy Consumption (kWh per production unit)';
COMMENT ON COLUMN enpi_performance.cumulative_savings_kwh IS 'Year-to-date cumulative energy savings';
COMMENT ON COLUMN energy_targets.target_reduction_percent IS 'Target energy reduction as % of baseline';
