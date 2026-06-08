-- ============================================================================
-- EnMS Migration 015: Fix 15-minute load factor aggregate column name
-- ============================================================================
-- The analytics service expects `avg_load_factor` for all aggregate intervals.
-- Older databases created `energy_readings_15min.load_factor`, while 1-hour
-- and 1-day aggregates already used `avg_load_factor`. The anomaly detector
-- queries the 15-minute aggregate, so the mismatch breaks scheduled detection.
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'energy_readings_15min'
          AND column_name = 'load_factor'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'energy_readings_15min'
          AND column_name = 'avg_load_factor'
    ) THEN
        ALTER MATERIALIZED VIEW energy_readings_15min
            RENAME COLUMN load_factor TO avg_load_factor;
    END IF;
END $$;
