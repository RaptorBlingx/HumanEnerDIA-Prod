-- Function to calculate predicted power based on baseline model
-- This allows Grafana to show actual vs predicted power in real-time

DROP FUNCTION IF EXISTS predict_power_from_baseline(UUID, NUMERIC, NUMERIC, NUMERIC, NUMERIC, NUMERIC);
DROP FUNCTION IF EXISTS predict_power_from_baseline(UUID, NUMERIC, NUMERIC, NUMERIC, NUMERIC, NUMERIC, NUMERIC);

CREATE OR REPLACE FUNCTION predict_power_from_baseline(
    p_machine_id UUID,
    p_production_count NUMERIC,
    p_outdoor_temp NUMERIC,
    p_throughput NUMERIC,
    p_machine_temp NUMERIC DEFAULT NULL,
    p_load_factor NUMERIC DEFAULT NULL,
    p_pressure_bar NUMERIC DEFAULT NULL
)
RETURNS NUMERIC
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_intercept NUMERIC;
    v_coefficients JSONB;
    v_feature_names TEXT[];
    v_predicted_power NUMERIC := 0;
    v_coef NUMERIC;
    v_feature_name TEXT;
BEGIN
    -- Get active baseline model for this machine
    SELECT 
        intercept,
        coefficients,
        feature_names
    INTO 
        v_intercept,
        v_coefficients,
        v_feature_names
    FROM energy_baselines
    WHERE machine_id = p_machine_id
      AND is_active = true
    LIMIT 1;
    
    -- If no model found, return NULL
    IF v_intercept IS NULL THEN
        RETURN NULL;
    END IF;
    
    -- Start with intercept
    v_predicted_power := v_intercept;
    
    -- Add contribution from each feature
    FOREACH v_feature_name IN ARRAY v_feature_names
    LOOP
        -- Get coefficient for this feature
        v_coef := (v_coefficients->>v_feature_name)::NUMERIC;
        
        -- Add feature contribution based on feature name
        CASE v_feature_name
            WHEN 'total_production_count' THEN
                v_predicted_power := v_predicted_power + (v_coef * COALESCE(p_production_count, 0));
            WHEN 'avg_outdoor_temp_c' THEN
                v_predicted_power := v_predicted_power + (v_coef * COALESCE(p_outdoor_temp, 0));
            WHEN 'avg_throughput_units_per_hour' THEN
                v_predicted_power := v_predicted_power + (v_coef * COALESCE(p_throughput, 0));
            WHEN 'avg_machine_temp_c' THEN
                v_predicted_power := v_predicted_power + (v_coef * COALESCE(p_machine_temp, 0));
            WHEN 'avg_load_factor' THEN
                v_predicted_power := v_predicted_power + (v_coef * COALESCE(p_load_factor, 0));
            WHEN 'avg_pressure_bar' THEN
                v_predicted_power := v_predicted_power + (v_coef * COALESCE(p_pressure_bar, 0));
            ELSE
                -- Unknown feature, skip it (don't throw error)
                NULL;
        END CASE;
    END LOOP;
    
    -- Return predicted power (baseline predicts hourly kWh, which equals kW for 1 hour)
    RETURN v_predicted_power;
END;
$$;

COMMENT ON FUNCTION predict_power_from_baseline IS 
'Calculate predicted power consumption using active baseline model coefficients. Returns NULL if no model exists.';
