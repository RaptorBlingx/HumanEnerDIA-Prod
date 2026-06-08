-- ============================================================================
-- Migration 004: Production SEU Structure (Real-World ISO 50001)
-- ============================================================================
-- Purpose: Create per-equipment electricity SEUs for Phase 1
-- Future: Multi-energy expansion (gas, steam, compressed air) in Phase 2
-- Author: EnMS Team
-- Date: October 22, 2025
-- ============================================================================

\echo ''
\echo '╔══════════════════════════════════════════════════════════════════════════╗'
\echo '║  Migration 004: Production SEU Structure (Per-Equipment)                ║'
\echo '║  Phase 1: Electricity SEUs (7 equipment)                                ║'
\echo '║  Phase 2 Ready: Multi-energy support built-in                           ║'
\echo '╚══════════════════════════════════════════════════════════════════════════╝'
\echo ''

BEGIN;

-- ============================================================================
-- PHASE 1: ELECTRICITY SEUs (Current Data Available)
-- ============================================================================
-- Real-world ISO 50001 practice: ONE SEU per equipment per energy type
-- 
-- These 7 SEUs track ELECTRICITY CONSUMPTION of production equipment.
-- Data source: energy_readings table (kWh consumed by each machine)
--
-- Real-world example:
--   - "Compressor-1 Electricity" SEU → tracks kWh to run compressor motor
--   - Future: "Compressor-1 Air Production" SEU → tracks Nm³ produced per kWh
-- ============================================================================

\echo '→ Creating 7 electricity SEUs (per-equipment structure)...'

-- Get electricity energy_source_id (needed for all SEUs)
DO $$
DECLARE
    v_electricity_id UUID;
    v_natural_gas_id UUID;
    v_compressed_air_id UUID;
    v_steam_id UUID;
BEGIN
    -- Fetch energy source IDs
    SELECT id INTO v_electricity_id FROM energy_sources WHERE name = 'electricity';
    SELECT id INTO v_natural_gas_id FROM energy_sources WHERE name = 'natural_gas';
    SELECT id INTO v_compressed_air_id FROM energy_sources WHERE name = 'compressed_air';
    SELECT id INTO v_steam_id FROM energy_sources WHERE name = 'steam';
    
    IF v_electricity_id IS NULL THEN
        RAISE EXCEPTION 'Energy source "electricity" not found. Run migration 003 first.';
    END IF;
    
    RAISE NOTICE 'Energy sources found:';
    RAISE NOTICE '  Electricity: %', v_electricity_id;
    RAISE NOTICE '  Natural Gas: % (for Phase 2)', v_natural_gas_id;
    RAISE NOTICE '  Compressed Air: % (for Phase 2)', v_compressed_air_id;
    RAISE NOTICE '  Steam: % (for Phase 2)', v_steam_id;
    
    -- ========================================================================
    -- SEU 1: Compressor-1 (ELECTRICITY)
    -- ========================================================================
    INSERT INTO seus (
        id,
        name,
        description,
        energy_source_id,
        machine_ids,
        is_active,
        created_at
    ) VALUES (
        'aaaaaaaa-1111-1111-1111-111111111111'::uuid,
        'Compressor-1',
        'Rotary screw air compressor - 55kW rated. Baseline variables: avg_production_count (flow rate proxy), ambient temperature (°C), operating hours. Produces compressed air for pneumatic tools and actuators. Energy source: ELECTRICITY consumption of compressor motor.',
        v_electricity_id,
        ARRAY['c0000000-0000-0000-0000-000000000001'::uuid],
        true,
        NOW()
    );
    RAISE NOTICE '✓ Created SEU: Compressor-1 (Electricity)';
    
    -- ========================================================================
    -- SEU 2: Compressor-EU-1 (ELECTRICITY)
    -- ========================================================================
    INSERT INTO seus (
        id,
        name,
        description,
        energy_source_id,
        machine_ids,
        is_active,
        created_at
    ) VALUES (
        'aaaaaaaa-2222-2222-2222-222222222222'::uuid,
        'Compressor-EU-1',
        'Rotary screw air compressor - 90kW rated. Baseline variables: avg_production_count (flow rate proxy), ambient temperature (°C), operating hours. Backup compressor for peak demand periods. Energy source: ELECTRICITY consumption of compressor motor.',
        v_electricity_id,
        ARRAY['c0000000-0000-0000-0000-000000000006'::uuid],
        true,
        NOW()
    );
    RAISE NOTICE '✓ Created SEU: Compressor-EU-1 (Electricity)';
    
    -- ========================================================================
    -- SEU 3: HVAC-Main (ELECTRICITY)
    -- ========================================================================
    INSERT INTO seus (
        id,
        name,
        description,
        energy_source_id,
        machine_ids,
        is_active,
        created_at
    ) VALUES (
        'aaaaaaaa-3333-3333-3333-333333333333'::uuid,
        'HVAC-Main',
        'Rooftop packaged HVAC unit - 150kW rated. Baseline variables: heating_degree_days (HDD), cooling_degree_days (CDD), occupancy hours. Serves main production floor (5000 m²). Energy source: ELECTRICITY for compressor, fans, and controls.',
        v_electricity_id,
        ARRAY['c0000000-0000-0000-0000-000000000002'::uuid],
        true,
        NOW()
    );
    RAISE NOTICE '✓ Created SEU: HVAC-Main (Electricity)';
    
    -- ========================================================================
    -- SEU 4: HVAC-EU-North (ELECTRICITY)
    -- ========================================================================
    INSERT INTO seus (
        id,
        name,
        description,
        energy_source_id,
        machine_ids,
        is_active,
        created_at
    ) VALUES (
        'aaaaaaaa-4444-4444-4444-444444444444'::uuid,
        'HVAC-EU-North',
        'Rooftop packaged HVAC unit - 200kW rated. Baseline variables: heating_degree_days (HDD), cooling_degree_days (CDD), occupancy hours. Serves warehouse (3000 m²) and office spaces (1000 m²). Energy source: ELECTRICITY for compressor, fans, and controls.',
        v_electricity_id,
        ARRAY['c0000000-0000-0000-0000-000000000007'::uuid],
        true,
        NOW()
    );
    RAISE NOTICE '✓ Created SEU: HVAC-EU-North (Electricity)';
    
    -- ========================================================================
    -- SEU 5: Conveyor-A (ELECTRICITY)
    -- ========================================================================
    INSERT INTO seus (
        id,
        name,
        description,
        energy_source_id,
        machine_ids,
        is_active,
        created_at
    ) VALUES (
        'aaaaaaaa-5555-5555-5555-555555555555'::uuid,
        'Conveyor-A',
        'Variable frequency drive (VFD) conveyor motor - 22kW rated. Baseline variables: avg_production_count (throughput units/h), operating hours, speed setpoint (%). Material handling for main production line. Energy source: ELECTRICITY to VFD motor.',
        v_electricity_id,
        ARRAY['c0000000-0000-0000-0000-000000000003'::uuid],
        true,
        NOW()
    );
    RAISE NOTICE '✓ Created SEU: Conveyor-A (Electricity)';
    
    -- ========================================================================
    -- SEU 6: Hydraulic-Pump-1 (ELECTRICITY)
    -- ========================================================================
    INSERT INTO seus (
        id,
        name,
        description,
        energy_source_id,
        machine_ids,
        is_active,
        created_at
    ) VALUES (
        'aaaaaaaa-6666-6666-6666-666666666666'::uuid,
        'Hydraulic-Pump-1',
        'Hydraulic power unit - 45kW rated. Baseline variables: avg_production_count (cycle count proxy), oil temperature (°C), operating hours. Provides hydraulic pressure for injection molding machines and presses. Energy source: ELECTRICITY to pump motor.',
        v_electricity_id,
        ARRAY['c0000000-0000-0000-0000-000000000004'::uuid],
        true,
        NOW()
    );
    RAISE NOTICE '✓ Created SEU: Hydraulic-Pump-1 (Electricity)';
    
    -- ========================================================================
    -- SEU 7: Injection-Molding-1 (ELECTRICITY)
    -- ========================================================================
    INSERT INTO seus (
        id,
        name,
        description,
        energy_source_id,
        machine_ids,
        is_active,
        created_at
    ) VALUES (
        'aaaaaaaa-7777-7777-7777-777777777777'::uuid,
        'Injection-Molding-1',
        'Injection molding machine - 120kW rated. Baseline variables: avg_production_count (cycle count), barrel temperature (°C), material type (product mix factor). Produces plastic components for automotive assembly. Energy source: ELECTRICITY for heating, hydraulics, and controls.',
        v_electricity_id,
        ARRAY['c0000000-0000-0000-0000-000000000005'::uuid],
        true,
        NOW()
    );
    RAISE NOTICE '✓ Created SEU: Injection-Molding-1 (Electricity)';
    
END $$;

\echo '✓ 7 electricity SEUs created successfully'
\echo ''

-- ============================================================================
-- PHASE 2 PREPARATION: Multi-Energy Foundation
-- ============================================================================
-- Future energy source tables (commented out for Phase 2 implementation)
-- Uncomment and adapt when adding natural gas, steam, or compressed air tracking
-- ============================================================================

\echo '→ Phase 2 preparation notes added to schema...'

COMMENT ON TABLE seus IS 'Significant Energy Users (ISO 50001 requirement). Phase 1: Electricity SEUs only. Phase 2: Add natural_gas_readings, compressed_air_readings, steam_readings tables and create SEUs for those energy types.';

COMMENT ON COLUMN seus.energy_source_id IS 'References energy_sources table. Current: electricity only. Future: natural_gas, compressed_air, steam when metering added.';

-- Example Phase 2 SEU structure (for future reference):
-- 
-- Natural Gas SEUs (when gas meters installed):
--   - 'Boiler-1' → natural_gas consumption for steam production
--   - 'Furnace-1' → natural_gas consumption for heat treatment
--   - 'Dryer-1' → natural_gas consumption for product drying
--
-- Compressed Air SEUs (end-user tracking, separate from compressor electricity):
--   - 'Pneumatic Press-1' → compressed_air consumption (Nm³)
--   - 'Assembly Tools' → compressed_air consumption (Nm³)
--   - Overall efficiency: kWh (compressor electricity) per Nm³ (air delivered)
--
-- Steam SEUs (when steam meters installed):
--   - 'Autoclave-1' → steam consumption for sterilization
--   - 'Process Heater-1' → steam consumption for chemical processes

\echo '✓ Phase 2 comments added to schema'
\echo ''

-- ============================================================================
-- Validation & Summary
-- ============================================================================

DO $$
DECLARE
    v_seu_count INTEGER;
    v_electricity_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_seu_count FROM seus WHERE is_active = true;
    SELECT COUNT(*) INTO v_electricity_count 
    FROM seus s
    JOIN energy_sources es ON s.energy_source_id = es.id
    WHERE s.is_active = true AND es.name = 'electricity';
    
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE 'Migration 004 Summary:';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE 'Total active SEUs: %', v_seu_count;
    RAISE NOTICE 'Electricity SEUs: %', v_electricity_count;
    RAISE NOTICE 'Phase 1: COMPLETE (Electricity tracking ready)';
    RAISE NOTICE 'Phase 2: PREPARED (Multi-energy expansion ready)';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE '';
    
    IF v_electricity_count != 8 THEN
        RAISE EXCEPTION 'Expected 8 electricity SEUs, found %', v_electricity_count;
    END IF;
END $$;

-- List all created SEUs
\echo 'Created SEUs:'
SELECT 
    s.name,
    es.name as energy_source,
    array_length(s.machine_ids, 1) as machine_count,
    s.description
FROM seus s
JOIN energy_sources es ON s.energy_source_id = es.id
WHERE s.is_active = true
ORDER BY s.name;

COMMIT;

\echo ''
\echo '✅ Migration 004 completed successfully!'
\echo '   Next step: Train baselines with machine-specific features'
\echo '   Phase 2: Add gas/steam/air meters → create SEUs for those sources'
\echo ''
