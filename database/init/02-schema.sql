-- ============================================================================
-- EnMS - Energy Management System
-- Database Initialization Script 02: Schema
-- ============================================================================
-- This script creates all tables and basic constraints
-- Execution order: Second (02)
-- ============================================================================

\echo '=========================================='
\echo 'Creating Database Schema...'
\echo '=========================================='

-- Set timezone to UTC for consistency
SET timezone = 'UTC';

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

\echo 'Creating ENUM types...'

-- Machine types
CREATE TYPE machine_type AS ENUM (
    'compressor',
    'hvac',
    'motor',
    'pump',
    'injection_molding',
    'conveyor',
    'boiler',
    'other'
);

-- Alert levels
CREATE TYPE alert_level AS ENUM (
    'normal',
    'warning',
    'critical'
);

-- Machine operating modes
CREATE TYPE operating_mode AS ENUM (
    'idle',
    'running',
    'maintenance',
    'fault',
    'offline'
);

\echo '✓ ENUM types created'

-- ============================================================================
-- DIMENSION TABLES
-- ============================================================================

\echo 'Creating dimension tables...'

-- Factories table
CREATE TABLE factories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    address TEXT,
    timezone VARCHAR(50) DEFAULT 'UTC',
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    
    CONSTRAINT factories_name_unique UNIQUE (name)
);

CREATE INDEX idx_factories_active ON factories(is_active);
CREATE INDEX idx_factories_name ON factories(name);

\echo '✓ factories table created'

-- Machines (SEUs) table
CREATE TABLE machines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    factory_id UUID NOT NULL REFERENCES factories(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    type machine_type NOT NULL,
    manufacturer VARCHAR(255),
    model VARCHAR(255),
    serial_number VARCHAR(255),
    installation_date DATE,
    
    -- Power specifications
    rated_power_kw DECIMAL(10, 2) NOT NULL,
    rated_voltage_v DECIMAL(10, 2),
    rated_current_a DECIMAL(10, 2),
    rated_frequency_hz DECIMAL(5, 2) DEFAULT 50.0,
    
    -- Physical specifications
    location_in_factory VARCHAR(255),
    
    -- Data collection settings
    data_interval_seconds INTEGER NOT NULL DEFAULT 10,
    mqtt_topic VARCHAR(255),
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_critical BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    
    CONSTRAINT machines_factory_name_unique UNIQUE (factory_id, name)
);

CREATE INDEX idx_machines_factory ON machines(factory_id);
CREATE INDEX idx_machines_type ON machines(type);
CREATE INDEX idx_machines_active ON machines(is_active);
CREATE INDEX idx_machines_critical ON machines(is_critical);
CREATE INDEX idx_machines_mqtt_topic ON machines(mqtt_topic);

\echo '✓ machines table created'

-- ============================================================================
-- FACT TABLES (Will be converted to hypertables)
-- ============================================================================

\echo 'Creating fact tables...'

-- Energy readings (time-series data)
CREATE TABLE energy_readings (
    time TIMESTAMPTZ NOT NULL,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    energy_type VARCHAR(50) NOT NULL DEFAULT 'electrical',
    
    -- Power metrics
    power_kw DECIMAL(10, 3) NOT NULL,
    energy_kwh DECIMAL(12, 6) NOT NULL DEFAULT 0,
    
    -- Electrical parameters
    voltage_v DECIMAL(10, 2),
    current_a DECIMAL(10, 2),
    power_factor DECIMAL(5, 4),
    frequency_hz DECIMAL(6, 3),
    
    -- Harmonics (optional)
    thd_voltage_percent DECIMAL(6, 3),
    thd_current_percent DECIMAL(6, 3),
    
    -- Three-phase systems (optional)
    voltage_l1_v DECIMAL(10, 2),
    voltage_l2_v DECIMAL(10, 2),
    voltage_l3_v DECIMAL(10, 2),
    current_l1_a DECIMAL(10, 2),
    current_l2_a DECIMAL(10, 2),
    current_l3_a DECIMAL(10, 2),
    
    -- Data quality
    is_estimated BOOLEAN DEFAULT FALSE,
    quality_score DECIMAL(3, 2) DEFAULT 1.0,
    
    -- Metadata
    source VARCHAR(50) DEFAULT 'sensor',
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Note: Will be converted to hypertable in 03-timescaledb-setup.sql
CREATE INDEX idx_energy_readings_machine_time ON energy_readings(machine_id, time DESC);
CREATE UNIQUE INDEX energy_readings_machine_time_type_unique ON energy_readings(machine_id, time, energy_type);

\echo '✓ energy_readings table created'

-- Production data (time-series data)
CREATE TABLE production_data (
    time TIMESTAMPTZ NOT NULL,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    
    -- Production metrics
    production_count INTEGER DEFAULT 0,
    production_count_good INTEGER DEFAULT 0,
    production_count_bad INTEGER DEFAULT 0,
    throughput_units_per_hour DECIMAL(10, 2),
    
    -- Operating parameters
    operating_mode operating_mode DEFAULT 'idle',
    recipe_id VARCHAR(100),
    batch_id VARCHAR(100),
    product_id VARCHAR(100),
    
    -- Speed/Performance
    speed_percent DECIMAL(5, 2),
    target_speed_percent DECIMAL(5, 2),
    
    -- Quality metrics
    quality_score DECIMAL(5, 2),
    
    -- Downtime
    downtime_seconds INTEGER DEFAULT 0,
    downtime_reason VARCHAR(255),
    
    -- Metadata
    operator_id VARCHAR(100),
    shift VARCHAR(50),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_production_data_machine_time ON production_data(machine_id, time DESC);
CREATE UNIQUE INDEX production_data_machine_time_unique ON production_data(machine_id, time);

\echo '✓ production_data table created'

-- Environmental data (time-series data)
CREATE TABLE environmental_data (
    time TIMESTAMPTZ NOT NULL,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    
    -- Temperature
    outdoor_temp_c DECIMAL(5, 2),
    indoor_temp_c DECIMAL(5, 2),
    machine_temp_c DECIMAL(5, 2),
    
    -- Humidity
    outdoor_humidity_percent DECIMAL(5, 2),
    indoor_humidity_percent DECIMAL(5, 2),
    
    -- Pressure (for compressors, pumps)
    pressure_bar DECIMAL(10, 3),
    pressure_setpoint_bar DECIMAL(10, 3),
    
    -- Flow (for fluids)
    flow_rate_m3h DECIMAL(10, 3),
    
    -- HVAC specific
    supply_air_temp_c DECIMAL(5, 2),
    return_air_temp_c DECIMAL(5, 2),
    chilled_water_supply_temp_c DECIMAL(5, 2),
    chilled_water_return_temp_c DECIMAL(5, 2),
    cop DECIMAL(5, 2), -- Coefficient of Performance
    
    -- Vibration (for condition monitoring)
    vibration_mm_s DECIMAL(8, 4),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_environmental_data_machine_time ON environmental_data(machine_id, time DESC);
CREATE UNIQUE INDEX environmental_data_machine_time_unique ON environmental_data(machine_id, time);

\echo '✓ environmental_data table created'

-- ============================================================================
-- CURRENT STATE TABLES
-- ============================================================================

\echo 'Creating state tables...'

-- Machine status (current state, not time-series)
CREATE TABLE machine_status (
    machine_id UUID PRIMARY KEY REFERENCES machines(id) ON DELETE CASCADE,
    
    -- Current state
    is_running BOOLEAN DEFAULT FALSE,
    current_mode operating_mode DEFAULT 'offline',
    current_power_kw DECIMAL(10, 3) DEFAULT 0,
    
    -- Cumulative metrics
    operating_hours_total DECIMAL(12, 2) DEFAULT 0,
    energy_total_kwh DECIMAL(15, 3) DEFAULT 0,
    production_total_units BIGINT DEFAULT 0,
    
    -- Last readings
    last_reading_time TIMESTAMPTZ,
    last_production_time TIMESTAMPTZ,
    
    -- Alert status
    alert_level alert_level DEFAULT 'normal',
    alert_message TEXT,
    alert_timestamp TIMESTAMPTZ,
    
    -- Health metrics
    health_score DECIMAL(5, 2) DEFAULT 100.0,
    uptime_percent_24h DECIMAL(5, 2),
    availability_percent_24h DECIMAL(5, 2),
    
    -- Timestamps
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_machine_status_running ON machine_status(is_running);
CREATE INDEX idx_machine_status_alert ON machine_status(alert_level);

\echo '✓ machine_status table created'

-- ============================================================================
-- ANALYTICS TABLES
-- ============================================================================

\echo 'Creating analytics tables...'

-- Energy baselines (EnB) - Stores trained regression models
CREATE TABLE energy_baselines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    
    -- Model metadata
    model_name VARCHAR(100) NOT NULL,
    model_type VARCHAR(50) DEFAULT 'linear_regression',
    model_version INTEGER DEFAULT 1,
    
    -- Training data
    training_start_date TIMESTAMPTZ NOT NULL,
    training_end_date TIMESTAMPTZ NOT NULL,
    training_samples INTEGER NOT NULL,
    
    -- Model parameters (stored as JSON)
    coefficients JSONB NOT NULL,
    intercept DECIMAL(15, 6),
    feature_names TEXT[] NOT NULL,
    
    -- Model performance
    r_squared DECIMAL(5, 4),
    rmse DECIMAL(12, 6),
    mae DECIMAL(12, 6),
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    trained_by VARCHAR(100),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    
    CONSTRAINT energy_baselines_machine_version_unique UNIQUE (machine_id, model_version)
);

CREATE INDEX idx_energy_baselines_machine ON energy_baselines(machine_id);
CREATE INDEX idx_energy_baselines_active ON energy_baselines(machine_id, is_active) WHERE is_active = TRUE;

\echo '✓ energy_baselines table created'

-- Anomalies detected
CREATE TABLE anomalies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    
    -- Anomaly details
    detected_at TIMESTAMPTZ NOT NULL,
    anomaly_type VARCHAR(100) NOT NULL,
    severity alert_level NOT NULL,
    
    -- Context
    metric_name VARCHAR(100),
    metric_value DECIMAL(15, 6),
    expected_value DECIMAL(15, 6),
    deviation_percent DECIMAL(8, 2),
    deviation_std_dev DECIMAL(8, 2),
    
    -- Detection method
    detection_method VARCHAR(100),
    confidence_score DECIMAL(5, 4),
    
    -- Resolution
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_anomalies_machine_time ON anomalies(machine_id, detected_at DESC);
CREATE INDEX idx_anomalies_severity ON anomalies(severity);
CREATE INDEX idx_anomalies_unresolved ON anomalies(machine_id, is_resolved) WHERE is_resolved = FALSE;

\echo '✓ anomalies table created'

-- ============================================================================
-- CONFIGURATION TABLES
-- ============================================================================

\echo 'Creating configuration tables...'

-- Energy tariffs (for cost calculation)
CREATE TABLE energy_tariffs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    factory_id UUID NOT NULL REFERENCES factories(id) ON DELETE CASCADE,
    
    -- Tariff details
    name VARCHAR(255) NOT NULL,
    description TEXT,
    
    -- Pricing
    rate_per_kwh DECIMAL(10, 6) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    
    -- Time-of-use
    is_time_of_use BOOLEAN DEFAULT FALSE,
    start_hour INTEGER,
    end_hour INTEGER,
    applicable_days INTEGER[], -- Array of day numbers (0=Sunday, 6=Saturday)
    
    -- Demand charges
    demand_charge_per_kw DECIMAL(10, 6),
    
    -- Validity
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_energy_tariffs_factory ON energy_tariffs(factory_id);
CREATE INDEX idx_energy_tariffs_active ON energy_tariffs(factory_id, is_active) WHERE is_active = TRUE;

\echo '✓ energy_tariffs table created'

-- Carbon emission factors
CREATE TABLE carbon_factors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Location/Grid
    region VARCHAR(255) NOT NULL,
    grid_name VARCHAR(255),
    
    -- Emission factor
    emission_factor_kg_co2_per_kwh DECIMAL(10, 6) NOT NULL,
    
    -- Source
    source VARCHAR(255),
    
    -- Validity
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_carbon_factors_region ON carbon_factors(region);
CREATE INDEX idx_carbon_factors_active ON carbon_factors(is_active) WHERE is_active = TRUE;

\echo '✓ carbon_factors table created'

-- ============================================================================
-- AUDIT LOG
-- ============================================================================

\echo 'Creating audit tables...'

-- System audit log
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Event details
    event_type VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id UUID,
    
    -- User/System
    user_id VARCHAR(100),
    system_component VARCHAR(100),
    
    -- Changes
    action VARCHAR(50) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    
    -- Context
    ip_address INET,
    user_agent TEXT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_log_event_type ON audit_log(event_type);

\echo '✓ audit_log table created'

-- ============================================================================
-- UPDATE TRIGGERS
-- ============================================================================

\echo 'Creating update triggers...'

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to tables with updated_at column
CREATE TRIGGER update_factories_updated_at BEFORE UPDATE ON factories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_machines_updated_at BEFORE UPDATE ON machines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

\echo '✓ Update triggers created'

-- ============================================================================
-- PERMISSIONS (Basic setup)
-- ============================================================================

\echo 'Setting up permissions...'

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO PUBLIC;

-- Grant select on all tables (adjust as needed for production)
GRANT SELECT ON ALL TABLES IN SCHEMA public TO PUBLIC;

\echo '✓ Permissions configured'

\echo ''
\echo '=========================================='
\echo 'Database schema created successfully!'
\echo '=========================================='
\echo ''
\echo 'Tables created:'
\echo '  - factories'
\echo '  - machines'
\echo '  - energy_readings'
\echo '  - production_data'
\echo '  - environmental_data'
\echo '  - machine_status'
\echo '  - energy_baselines'
\echo '  - anomalies'
\echo '  - energy_tariffs'
\echo '  - carbon_factors'
\echo '  - audit_log'
\echo ''
