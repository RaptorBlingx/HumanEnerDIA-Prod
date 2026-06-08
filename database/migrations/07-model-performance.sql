-- /enms/database/migrations/07-model-performance.sql
-- Phase 4 Session 2: Model Performance Tracking
-- Stores historical performance metrics for all ML models
CREATE TABLE IF NOT EXISTS model_performance_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_type VARCHAR(50) NOT NULL,
    model_id UUID,
    machine_id UUID REFERENCES machines(id),
    metric_name VARCHAR(50) NOT NULL,
    metric_value FLOAT NOT NULL,
    evaluated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_perf_model_type ON model_performance_history(model_type);
CREATE INDEX IF NOT EXISTS idx_perf_evaluated_at ON model_performance_history(evaluated_at DESC);