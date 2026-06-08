-- ============================================================================
-- Migration 013: Fix regression feature flags for baseline training
-- ============================================================================
-- Purpose: Prevent target leakage by ensuring energy consumption fields and
-- direct electrical measurement proxies are not exposed as baseline drivers.

UPDATE energy_source_features
SET is_regression_feature = false,
    updated_at = NOW()
WHERE is_regression_feature = true
  AND feature_name IN (
      'consumption_kwh',
      'consumption_m3',
      'consumption_kg',
      'avg_power_kw',
      'max_power_kw',
      'avg_current_a',
      'avg_voltage_v'
  );