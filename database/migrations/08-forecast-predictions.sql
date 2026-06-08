-- ============================================================================
-- EnMS - Energy Management System
-- Migration 08: Energy Forecast Predictions Table
-- ============================================================================
-- Purpose: Store forecast predictions for visualization in Grafana
-- Date: October 14, 2025
-- ============================================================================

\echo '=========================================='
\echo 'Creating forecast predictions table...'
\echo '=========================================='

-- Create forecast model type enum
CREATE TYPE forecast_model_type AS ENUM (
    'ARIMA',
    'Prophet',
    'LSTM',
    'Other'
);

-- Create forecast horizon enum
CREATE TYPE forecast_horizon AS ENUM (
    'short',    -- 1-4 hours
    'medium',   -- 24 hours
    'long'      -- 7 days
);

-- Forecast predictions table (hypertable for time-series)
CREATE TABLE energy_forecasts (
    id BIGSERIAL,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    
    -- Forecast metadata
    model_type forecast_model_type NOT NULL,
    model_version INTEGER DEFAULT 1,
    horizon forecast_horizon NOT NULL,
    
    -- Time information
    forecasted_at TIMESTAMPTZ NOT NULL,  -- When the forecast was generated
    forecast_time TIMESTAMPTZ NOT NULL,  -- The time being forecasted
    
    -- Predictions
    predicted_power_kw DECIMAL(10, 3) NOT NULL,
    lower_bound_kw DECIMAL(10, 3),       -- 95% confidence interval lower
    upper_bound_kw DECIMAL(10, 3),       -- 95% confidence interval upper
    
    -- Metadata
    confidence_level DECIMAL(5, 2) DEFAULT 0.95,  -- 95% by default
    training_samples INTEGER,
    rmse DECIMAL(10, 3),
    mape DECIMAL(5, 2),
    r2 DECIMAL(5, 4),
    
    -- Additional info
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (forecast_time, machine_id, model_type)
);

-- Convert to hypertable (partitioned by forecast_time)
SELECT create_hypertable(
    'energy_forecasts',
    'forecast_time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Indexes for efficient querying
CREATE INDEX idx_energy_forecasts_machine_time 
    ON energy_forecasts(machine_id, forecast_time DESC);

CREATE INDEX idx_energy_forecasts_forecasted_at 
    ON energy_forecasts(forecasted_at DESC);

CREATE INDEX idx_energy_forecasts_model 
    ON energy_forecasts(model_type, horizon);

CREATE INDEX idx_energy_forecasts_metadata 
    ON energy_forecasts USING gin(metadata);

-- Add retention policy (keep forecasts for 90 days)
SELECT add_retention_policy(
    'energy_forecasts',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- Create view for latest forecasts per machine
CREATE OR REPLACE VIEW latest_forecasts AS
SELECT DISTINCT ON (machine_id, model_type)
    ef.id,
    ef.machine_id,
    m.name AS machine_name,
    ef.model_type,
    ef.horizon,
    ef.forecasted_at,
    ef.forecast_time,
    ef.predicted_power_kw,
    ef.lower_bound_kw,
    ef.upper_bound_kw,
    ef.confidence_level,
    ef.rmse,
    ef.mape,
    ef.r2
FROM energy_forecasts ef
JOIN machines m ON ef.machine_id = m.id
ORDER BY machine_id, model_type, forecasted_at DESC;

-- Create view for comparing actual vs forecast
CREATE OR REPLACE VIEW forecast_accuracy AS
SELECT 
    ef.machine_id,
    ef.model_type,
    ef.horizon,
    ef.forecast_time,
    ef.predicted_power_kw,
    er.avg_power_kw AS actual_power_kw,
    ABS(ef.predicted_power_kw - er.avg_power_kw) AS absolute_error,
    CASE 
        WHEN er.avg_power_kw > 0 THEN 
            ABS((ef.predicted_power_kw - er.avg_power_kw) / er.avg_power_kw) * 100
        ELSE NULL 
    END AS percentage_error,
    CASE 
        WHEN er.avg_power_kw BETWEEN ef.lower_bound_kw AND ef.upper_bound_kw 
        THEN TRUE 
        ELSE FALSE 
    END AS within_confidence_interval
FROM energy_forecasts ef
LEFT JOIN energy_readings_1min er ON 
    ef.machine_id = er.machine_id 
    AND ef.forecast_time = er.bucket
WHERE er.bucket IS NOT NULL;

COMMENT ON TABLE energy_forecasts IS 'Stores time-series forecast predictions for energy consumption';
COMMENT ON VIEW latest_forecasts IS 'Shows the most recent forecast for each machine and model type';
COMMENT ON VIEW forecast_accuracy IS 'Compares forecast predictions with actual measurements for accuracy tracking';

\echo '✓ Forecast predictions table created'
\echo '✓ Hypertable configured with 7-day chunks'
\echo '✓ 90-day retention policy added'
\echo '✓ Views created for latest forecasts and accuracy tracking'
\echo '=========================================='
