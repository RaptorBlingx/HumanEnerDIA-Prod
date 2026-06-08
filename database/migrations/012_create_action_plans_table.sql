-- ============================================================================
-- Migration 012: Create ISO 50001 Action Plans Table
-- Created: November 7, 2025
-- Purpose: Track energy improvement action plans for ISO 50001 compliance
-- ============================================================================

-- ============================================================================
-- Action Plans Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS action_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Reference
    seu_id UUID REFERENCES seus(id),
    factory_id UUID REFERENCES factories(id),
    
    -- Plan Details
    title VARCHAR(255) NOT NULL,
    objective TEXT NOT NULL,
    description TEXT,
    
    -- Energy Impact
    target_savings_kwh NUMERIC(15, 4) NOT NULL CHECK (target_savings_kwh >= 0),
    target_savings_usd NUMERIC(15, 2),
    actual_savings_kwh NUMERIC(15, 4),
    actual_savings_usd NUMERIC(15, 2),
    
    -- Status Management
    status VARCHAR(20) NOT NULL DEFAULT 'planned' 
        CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled', 'on_hold')),
    priority VARCHAR(10) DEFAULT 'medium'
        CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    
    -- Responsibility & Dates
    responsible_person VARCHAR(255),
    responsible_department VARCHAR(255),
    start_date DATE,
    target_date DATE,
    completion_date DATE,
    
    -- Progress Tracking
    progress_percent NUMERIC(5, 2) DEFAULT 0 CHECK (progress_percent >= 0 AND progress_percent <= 100),
    completion_notes TEXT,
    
    -- Investment & ROI
    estimated_investment_usd NUMERIC(15, 2),
    actual_investment_usd NUMERIC(15, 2),
    payback_period_months NUMERIC(6, 2),
    
    -- Audit Trail
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT action_plans_target_date_after_start CHECK (target_date IS NULL OR start_date IS NULL OR target_date >= start_date),
    CONSTRAINT action_plans_completion_date_logic CHECK (
        (status = 'completed' AND completion_date IS NOT NULL) OR 
        (status != 'completed' AND completion_date IS NULL)
    )
);

-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX idx_action_plans_seu ON action_plans(seu_id);
CREATE INDEX idx_action_plans_factory ON action_plans(factory_id);
CREATE INDEX idx_action_plans_status ON action_plans(status);
CREATE INDEX idx_action_plans_priority ON action_plans(priority);
CREATE INDEX idx_action_plans_target_date ON action_plans(target_date);
CREATE INDEX idx_action_plans_responsible ON action_plans(responsible_person);

-- ============================================================================
-- Triggers
-- ============================================================================

CREATE TRIGGER update_action_plans_updated_at
    BEFORE UPDATE ON action_plans
    FOR EACH ROW
    EXECUTE FUNCTION update_enpi_updated_at();

-- Auto-update ROI calculations
CREATE OR REPLACE FUNCTION update_action_plan_roi()
RETURNS TRIGGER AS $$
BEGIN
    -- Calculate payback period if investment and savings are known
    IF NEW.actual_investment_usd IS NOT NULL AND NEW.actual_investment_usd > 0 
       AND NEW.actual_savings_usd IS NOT NULL AND NEW.actual_savings_usd > 0 THEN
        NEW.payback_period_months := (NEW.actual_investment_usd / NEW.actual_savings_usd) * 12;
    ELSIF NEW.estimated_investment_usd IS NOT NULL AND NEW.estimated_investment_usd > 0 
          AND NEW.target_savings_usd IS NOT NULL AND NEW.target_savings_usd > 0 THEN
        NEW.payback_period_months := (NEW.estimated_investment_usd / NEW.target_savings_usd) * 12;
    END IF;
    
    -- Auto-set completion date if status changes to completed
    IF NEW.status = 'completed' AND OLD.status != 'completed' AND NEW.completion_date IS NULL THEN
        NEW.completion_date := CURRENT_DATE;
    END IF;
    
    -- Auto-set progress to 100% if completed
    IF NEW.status = 'completed' AND NEW.progress_percent < 100 THEN
        NEW.progress_percent := 100;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_action_plan_roi_trigger
    BEFORE INSERT OR UPDATE ON action_plans
    FOR EACH ROW
    EXECUTE FUNCTION update_action_plan_roi();

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE action_plans IS 'ISO 50001 energy improvement action plans and tracking';
COMMENT ON COLUMN action_plans.target_savings_kwh IS 'Expected energy savings from this action (kWh/year)';
COMMENT ON COLUMN action_plans.actual_savings_kwh IS 'Measured energy savings achieved (kWh/year)';
COMMENT ON COLUMN action_plans.payback_period_months IS 'Investment payback period in months';
COMMENT ON COLUMN action_plans.priority IS 'Action priority level (low, medium, high, critical)';
