-- ============================================================================
-- EnMS - Model Performance Tracking Schema
-- ============================================================================
-- Migration 09: Model Performance Tracking
-- This script creates tables for tracking ML model performance over time
-- Date: October 15, 2025
-- Phase 4, Session 4
-- ============================================================================

\echo '=========================================='
\echo 'Creating Model Performance Tracking Schema...'
\echo '=========================================='

-- ============================================================================
-- MODEL PERFORMANCE METRICS
-- ============================================================================

\echo 'Creating model_performance_metrics table...'

-- Track model performance over time
CREATE TABLE IF NOT EXISTS model_performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Model identification
    model_id UUID NOT NULL,  -- References energy_baselines(id), energy_forecasts model, etc.
    model_type VARCHAR(50) NOT NULL,  -- 'baseline', 'anomaly', 'forecast_prophet'
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    model_version INTEGER NOT NULL,
    
    -- Evaluation period
    evaluation_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evaluation_start TIMESTAMPTZ NOT NULL,
    evaluation_end TIMESTAMPTZ NOT NULL,
    sample_count INTEGER NOT NULL,
    
    -- Performance metrics (specific to model type)
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,  -- Flexible storage for different metrics
    
    -- Standard regression metrics (for baseline/forecast)
    r_squared DECIMAL(5, 4),
    rmse DECIMAL(12, 6),
    mae DECIMAL(12, 6),
    mape DECIMAL(6, 2),  -- Mean Absolute Percentage Error
    
    -- Classification metrics (for anomaly detection)
    precision_score DECIMAL(5, 4),
    recall_score DECIMAL(5, 4),
    f1_score DECIMAL(5, 4),
    true_positives INTEGER,
    false_positives INTEGER,
    true_negatives INTEGER,
    false_negatives INTEGER,
    
    -- Drift indicators
    drift_detected BOOLEAN DEFAULT FALSE,
    drift_score DECIMAL(8, 6),  -- KS statistic or PSI score
    drift_threshold DECIMAL(8, 6),
    
    -- Data quality metrics
    data_completeness DECIMAL(5, 4),  -- % of expected data points available
    outlier_percentage DECIMAL(5, 4),
    
    -- Metadata
    evaluation_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_model_perf_model_id ON model_performance_metrics(model_id);
CREATE INDEX IF NOT EXISTS idx_model_perf_machine_type ON model_performance_metrics(machine_id, model_type);
CREATE INDEX IF NOT EXISTS idx_model_perf_eval_date ON model_performance_metrics(evaluation_date DESC);
CREATE INDEX IF NOT EXISTS idx_model_perf_drift ON model_performance_metrics(drift_detected) WHERE drift_detected = TRUE;

\echo '✓ model_performance_metrics table created'

-- ============================================================================
-- MODEL TRAINING HISTORY
-- ============================================================================

\echo 'Creating model_training_history table...'

-- Track all training attempts and results
CREATE TABLE IF NOT EXISTS model_training_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Model identification
    model_id UUID,  -- NULL if training failed
    model_type VARCHAR(50) NOT NULL,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    model_version INTEGER,
    
    -- Training details
    training_start TIMESTAMPTZ NOT NULL,
    training_end TIMESTAMPTZ,
    training_duration_seconds INTEGER,
    training_status VARCHAR(50) NOT NULL,  -- 'pending', 'running', 'completed', 'failed'
    
    -- Training data
    training_data_start TIMESTAMPTZ NOT NULL,
    training_data_end TIMESTAMPTZ NOT NULL,
    training_samples INTEGER,
    
    -- Training configuration
    hyperparameters JSONB DEFAULT '{}'::jsonb,
    feature_names TEXT[],
    
    -- Training metrics
    training_metrics JSONB DEFAULT '{}'::jsonb,
    validation_metrics JSONB DEFAULT '{}'::jsonb,
    
    -- Results
    initial_r_squared DECIMAL(5, 4),
    initial_rmse DECIMAL(12, 6),
    initial_mae DECIMAL(12, 6),
    
    -- Error handling
    error_message TEXT,
    error_traceback TEXT,
    
    -- Trigger information
    trigger_type VARCHAR(50) NOT NULL,  -- 'manual', 'scheduled', 'drift_detected', 'performance_degradation'
    triggered_by VARCHAR(100),
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_training_history_machine_type ON model_training_history(machine_id, model_type);
CREATE INDEX IF NOT EXISTS idx_training_history_status ON model_training_history(training_status);
CREATE INDEX IF NOT EXISTS idx_training_history_date ON model_training_history(training_start DESC);
CREATE INDEX IF NOT EXISTS idx_training_history_trigger ON model_training_history(trigger_type);

\echo '✓ model_training_history table created'

-- ============================================================================
-- MODEL AB TESTS
-- ============================================================================

\echo 'Creating model_ab_tests table...'

-- Track A/B tests between model versions
CREATE TABLE IF NOT EXISTS model_ab_tests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Test identification
    test_name VARCHAR(255) NOT NULL,
    model_type VARCHAR(50) NOT NULL,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    
    -- Models being compared
    model_a_id UUID NOT NULL,
    model_a_version INTEGER NOT NULL,
    model_b_id UUID NOT NULL,
    model_b_version INTEGER NOT NULL,
    
    -- Test period
    test_start TIMESTAMPTZ NOT NULL,
    test_end TIMESTAMPTZ,
    test_status VARCHAR(50) NOT NULL DEFAULT 'running',  -- 'planned', 'running', 'completed', 'cancelled'
    
    -- Traffic split
    traffic_split_a DECIMAL(3, 2) DEFAULT 0.50,  -- 50% traffic to model A
    traffic_split_b DECIMAL(3, 2) DEFAULT 0.50,  -- 50% traffic to model B
    
    -- Results
    model_a_metrics JSONB DEFAULT '{}'::jsonb,
    model_b_metrics JSONB DEFAULT '{}'::jsonb,
    
    -- Winner determination
    winner_model_id UUID,
    winner_declared_at TIMESTAMPTZ,
    statistical_significance DECIMAL(5, 4),  -- p-value
    confidence_level DECIMAL(5, 4) DEFAULT 0.95,
    
    -- Decision
    decision VARCHAR(50),  -- 'promote_a', 'promote_b', 'no_winner', 'manual_review'
    decision_notes TEXT,
    decided_by VARCHAR(100),
    decided_at TIMESTAMPTZ,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ab_tests_machine_type ON model_ab_tests(machine_id, model_type);
CREATE INDEX IF NOT EXISTS idx_ab_tests_status ON model_ab_tests(test_status);
CREATE INDEX IF NOT EXISTS idx_ab_tests_active ON model_ab_tests(test_start, test_end) WHERE test_status = 'running';

\echo '✓ model_ab_tests table created'

-- ============================================================================
-- MODEL ALERTS
-- ============================================================================

\echo 'Creating model_alerts table...'

-- Track alerts for model performance issues
CREATE TABLE IF NOT EXISTS model_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Alert identification
    alert_type VARCHAR(100) NOT NULL,  -- 'drift_detected', 'performance_degradation', 'training_failed', etc.
    severity alert_level NOT NULL,  -- Using existing alert_level enum (normal, warning, critical)
    
    -- Model identification
    model_id UUID,
    model_type VARCHAR(50) NOT NULL,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    model_version INTEGER,
    
    -- Alert details
    alert_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alert_message TEXT NOT NULL,
    alert_details JSONB DEFAULT '{}'::jsonb,
    
    -- Metrics that triggered alert
    current_metric_value DECIMAL(12, 6),
    threshold_value DECIMAL(12, 6),
    baseline_metric_value DECIMAL(12, 6),
    
    -- Resolution
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolution_action VARCHAR(255),  -- 'retrained_model', 'acknowledged', 'false_positive', etc.
    resolved_by VARCHAR(100),
    resolution_notes TEXT,
    
    -- Actions taken
    auto_action_taken BOOLEAN DEFAULT FALSE,
    auto_action_type VARCHAR(100),  -- 'auto_retrain', 'rollback', 'notify', etc.
    auto_action_result JSONB,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_model_alerts_machine_type ON model_alerts(machine_id, model_type);
CREATE INDEX IF NOT EXISTS idx_model_alerts_severity ON model_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_model_alerts_unresolved ON model_alerts(machine_id) WHERE is_resolved = FALSE;
CREATE INDEX IF NOT EXISTS idx_model_alerts_timestamp ON model_alerts(alert_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_model_alerts_type ON model_alerts(alert_type);

\echo '✓ model_alerts table created'

-- ============================================================================
-- VIEWS FOR EASY QUERYING
-- ============================================================================

\echo 'Creating helper views...'

-- View: Latest performance for each model
CREATE OR REPLACE VIEW v_latest_model_performance AS
SELECT DISTINCT ON (machine_id, model_type)
    mpm.*,
    m.name as machine_name,
    m.type as machine_type
FROM model_performance_metrics mpm
JOIN machines m ON m.id = mpm.machine_id
ORDER BY machine_id, model_type, evaluation_date DESC;

\echo '✓ v_latest_model_performance view created'

-- View: Active AB tests
CREATE OR REPLACE VIEW v_active_ab_tests AS
SELECT 
    abt.*,
    m.name as machine_name,
    EXTRACT(EPOCH FROM (NOW() - abt.test_start))/3600 as test_duration_hours
FROM model_ab_tests abt
JOIN machines m ON m.id = abt.machine_id
WHERE abt.test_status = 'running';

\echo '✓ v_active_ab_tests view created'

-- View: Unresolved model alerts
CREATE OR REPLACE VIEW v_unresolved_model_alerts AS
SELECT 
    ma.*,
    m.name as machine_name,
    m.type as machine_type,
    EXTRACT(EPOCH FROM (NOW() - ma.alert_timestamp))/3600 as age_hours
FROM model_alerts ma
JOIN machines m ON m.id = ma.machine_id
WHERE ma.is_resolved = FALSE
ORDER BY ma.severity DESC, ma.alert_timestamp DESC;

\echo '✓ v_unresolved_model_alerts view created'

\echo ''
\echo '=========================================='
\echo 'Model Performance Tracking Schema Complete!'
\echo '=========================================='
\echo ''
\echo 'Tables created:'
\echo '  - model_performance_metrics'
\echo '  - model_training_history'
\echo '  - model_ab_tests'
\echo '  - model_alerts'
\echo ''
\echo 'Views created:'
\echo '  - v_latest_model_performance'
\echo '  - v_active_ab_tests'
\echo '  - v_unresolved_model_alerts'
\echo ''
