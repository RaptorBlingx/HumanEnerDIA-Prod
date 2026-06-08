-- ============================================================================
-- Migration 010: Fix Multi-Energy Baseline Storage
-- ============================================================================
-- Date: November 5, 2025
-- Phase: v2-bugfix (Phase 0 validation)
-- Bug: Critical - Multi-energy machines share same baseline model
-- Root Cause: energy_baselines table lacks energy_source_id column
-- Impact: Boiler-1 electricity/gas/steam predictions are identical (wrong!)
-- ============================================================================

\echo ''
\echo '========================================='
\echo 'Migration 010: Fix Multi-Energy Baselines'
\echo '========================================='
\echo ''

BEGIN;

-- ============================================================================
-- Step 1: Add energy_source_id column
-- ============================================================================

\echo '→ Adding energy_source_id column to energy_baselines...'

ALTER TABLE energy_baselines
    ADD COLUMN energy_source_id UUID REFERENCES energy_sources(id) ON DELETE RESTRICT;

\echo '✓ Column added'

-- ============================================================================
-- Step 2: Populate energy_source_id from machine's SEU
-- ============================================================================

\echo '→ Populating energy_source_id for existing models...'

-- For each existing baseline, find the most common energy source from machine's SEUs
-- (Handles case where machine has multiple SEUs with different energy sources)
UPDATE energy_baselines eb
SET energy_source_id = (
    SELECT s.energy_source_id
    FROM seus s
    WHERE eb.machine_id = ANY(s.machine_ids)
    GROUP BY s.energy_source_id
    ORDER BY COUNT(*) DESC
    LIMIT 1
);

-- If any baselines still have NULL energy_source_id, set to electricity (default)
UPDATE energy_baselines
SET energy_source_id = (SELECT id FROM energy_sources WHERE name = 'electricity' LIMIT 1)
WHERE energy_source_id IS NULL;

\echo '✓ Existing models populated with energy_source_id'

-- ============================================================================
-- Step 3: Make energy_source_id NOT NULL
-- ============================================================================

\echo '→ Making energy_source_id NOT NULL...'

ALTER TABLE energy_baselines
    ALTER COLUMN energy_source_id SET NOT NULL;

\echo '✓ Column constraint added'

-- ============================================================================
-- Step 4: Update unique constraint
-- ============================================================================

\echo '→ Updating unique constraint to include energy_source_id...'

-- Drop old constraint
ALTER TABLE energy_baselines
    DROP CONSTRAINT energy_baselines_machine_version_unique;

-- Add new constraint: unique per (machine_id, energy_source_id, model_version)
ALTER TABLE energy_baselines
    ADD CONSTRAINT energy_baselines_machine_energy_version_unique
    UNIQUE (machine_id, energy_source_id, model_version);

\echo '✓ Unique constraint updated'

-- ============================================================================
-- Step 5: Add index for faster lookups
-- ============================================================================

\echo '→ Creating index on (machine_id, energy_source_id, is_active)...'

DROP INDEX IF EXISTS idx_energy_baselines_active;

CREATE INDEX IF NOT EXISTS idx_energy_baselines_active 
    ON energy_baselines(machine_id, energy_source_id, is_active) 
    WHERE is_active = TRUE;

\echo '✓ Index created'

-- ============================================================================
-- Step 6: Verification
-- ============================================================================

\echo ''
\echo '→ Verifying migration...'

-- Check for any NULL energy_source_id
DO $$
DECLARE
    null_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count
    FROM energy_baselines
    WHERE energy_source_id IS NULL;
    
    IF null_count > 0 THEN
        RAISE EXCEPTION 'Migration failed: % baselines still have NULL energy_source_id', null_count;
    END IF;
    
    RAISE NOTICE '✓ No NULL energy_source_id values';
END $$;

-- Show current baseline distribution
\echo ''
\echo 'Current baseline distribution:'
SELECT 
    es.name as energy_source,
    COUNT(*) as total_models,
    COUNT(*) FILTER (WHERE eb.is_active) as active_models
FROM energy_baselines eb
JOIN energy_sources es ON es.id = eb.energy_source_id
GROUP BY es.name
ORDER BY es.name;

COMMIT;

\echo ''
\echo '✅ Migration 010 completed successfully!'
\echo '   Next: Re-train multi-energy machine baselines (Boiler-1)'
\echo ''
