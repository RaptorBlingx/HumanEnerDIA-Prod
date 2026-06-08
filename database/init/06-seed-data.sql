-- ============================================================================
-- EnMS - Energy Management System
-- Database Initialization Script 06: Seed Data
-- ============================================================================
-- This script populates the database with initial sample data
-- Execution order: Sixth (06)
-- ============================================================================

\echo '=========================================='
\echo 'Seeding Initial Data...'
\echo '=========================================='

-- ============================================================================
-- FACTORIES
-- ============================================================================

\echo 'Creating sample factories...'

INSERT INTO factories (id, name, location, address, timezone, contact_email, metadata) VALUES
(
    '11111111-1111-1111-1111-111111111111',
    'Demo Manufacturing Plant',
    'Silicon Valley, CA, USA',
    '1234 Industrial Parkway, San Jose, CA 95131',
    'America/Los_Angeles',
    'operations@demoplant.com',
    '{"industry": "manufacturing", "size": "medium", "employees": 250}'::jsonb
),
(
    '22222222-2222-2222-2222-222222222222',
    'European Production Facility',
    'Munich, Germany',
    'Industriestraße 45, 80331 München, Germany',
    'Europe/Berlin',
    'facility@europlant.eu',
    '{"industry": "automotive", "size": "large", "employees": 500}'::jsonb
);

\echo '✓ Sample factories created'

-- ============================================================================
-- MACHINES (5 Types with Different Data Frequencies)
-- ============================================================================

\echo 'Creating sample machines (SEUs)...'

-- Factory 1: Demo Manufacturing Plant
-- Machine 1: Compressor (1-second intervals)
INSERT INTO machines (
    id, factory_id, name, description, type, 
    manufacturer, model, serial_number, installation_date,
    rated_power_kw, rated_voltage_v, rated_current_a, rated_frequency_hz,
    location_in_factory, data_interval_seconds, mqtt_topic,
    is_active, is_critical
) VALUES (
    'c0000000-0000-0000-0000-000000000001',
    '11111111-1111-1111-1111-111111111111',
    'Compressor-1',
    'Main air compressor for production line',
    'compressor',
    'Atlas Copco',
    'GA 55 VSD',
    'AC2024-001',
    '2023-01-15',
    55.0, 400.0, 79.3, 50.0,
    'Compressor Room - West Wing',
    1,  -- 1-second intervals
    'factory/demo/compressor-1',
    TRUE, TRUE
);

-- Machine 2: HVAC System (10-second intervals)
INSERT INTO machines (
    id, factory_id, name, description, type,
    manufacturer, model, serial_number, installation_date,
    rated_power_kw, rated_voltage_v, rated_current_a, rated_frequency_hz,
    location_in_factory, data_interval_seconds, mqtt_topic,
    is_active, is_critical
) VALUES (
    'c0000000-0000-0000-0000-000000000002',
    '11111111-1111-1111-1111-111111111111',
    'HVAC-Main',
    'Central HVAC system for entire facility',
    'hvac',
    'Carrier',
    'AquaEdge 23XRV',
    'CAR2023-HVAC-001',
    '2022-06-20',
    150.0, 400.0, 216.5, 50.0,
    'Rooftop - Central',
    10,  -- 10-second intervals
    'factory/demo/hvac-main',
    TRUE, TRUE
);

-- Machine 3: Conveyor Motor (10-second intervals)
INSERT INTO machines (
    id, factory_id, name, description, type,
    manufacturer, model, serial_number, installation_date,
    rated_power_kw, rated_voltage_v, rated_current_a, rated_frequency_hz,
    location_in_factory, data_interval_seconds, mqtt_topic,
    is_active, is_critical
) VALUES (
    'c0000000-0000-0000-0000-000000000003',
    '11111111-1111-1111-1111-111111111111',
    'Conveyor-A',
    'Main assembly line conveyor belt motor',
    'motor',
    'SEW-EURODRIVE',
    'DRS 90L4',
    'SEW2023-MOT-045',
    '2023-03-10',
    22.0, 400.0, 31.7, 50.0,
    'Production Floor - Line A',
    10,  -- 10-second intervals
    'factory/demo/conveyor-a',
    TRUE, FALSE
);

-- Machine 4: Hydraulic Pump (30-second intervals)
INSERT INTO machines (
    id, factory_id, name, description, type,
    manufacturer, model, serial_number, installation_date,
    rated_power_kw, rated_voltage_v, rated_current_a, rated_frequency_hz,
    location_in_factory, data_interval_seconds, mqtt_topic,
    is_active, is_critical
) VALUES (
    'c0000000-0000-0000-0000-000000000004',
    '11111111-1111-1111-1111-111111111111',
    'Hydraulic-Pump-1',
    'Hydraulic power unit for press machines',
    'pump',
    'Bosch Rexroth',
    'A10VSO 140',
    'BRX2022-PMP-078',
    '2022-11-05',
    45.0, 400.0, 64.9, 50.0,
    'Press Section - Bay 3',
    30,  -- 30-second intervals
    'factory/demo/hydraulic-pump-1',
    TRUE, TRUE
);

-- Machine 5: Injection Molding Machine (30-second intervals)
INSERT INTO machines (
    id, factory_id, name, description, type,
    manufacturer, model, serial_number, installation_date,
    rated_power_kw, rated_voltage_v, rated_current_a, rated_frequency_hz,
    location_in_factory, data_interval_seconds, mqtt_topic,
    is_active, is_critical
) VALUES (
    'c0000000-0000-0000-0000-000000000005',
    '11111111-1111-1111-1111-111111111111',
    'Injection-Molding-1',
    'Large injection molding machine for plastic parts',
    'injection_molding',
    'Arburg',
    'Allrounder 820 S',
    'ARB2023-INJ-012',
    '2023-05-18',
    120.0, 400.0, 173.2, 50.0,
    'Molding Department - Cell 1',
    30,  -- 30-second intervals
    'factory/demo/injection-molding-1',
    TRUE, TRUE
);

-- Machine 6: Boiler (30-second intervals)
INSERT INTO machines (
    id, factory_id, name, description, type,
    manufacturer, model, serial_number, installation_date,
    rated_power_kw, rated_voltage_v, rated_current_a, rated_frequency_hz,
    location_in_factory, data_interval_seconds, mqtt_topic,
    is_active, is_critical
) VALUES (
    'c0000000-0000-0000-0000-000000000008',
    '11111111-1111-1111-1111-111111111111',
    'Boiler-1',
    'Industrial steam boiler for heating',
    'boiler',
    'Viessmann',
    'Vitomax 200-LW',
    'VIE2024-BOI-001',
    '2024-01-10',
    45.0, 400.0, 64.9, 50.0,
    'Boiler Room - East Wing',
    30,  -- 30-second intervals
    'factory/DemoPlant/Boiler-1',
    TRUE, FALSE
);

\echo '✓ 6 machines created for Demo Manufacturing Plant'

-- Factory 2: European Production Facility
-- Additional machines for multi-factory demonstration

INSERT INTO machines (
    id, factory_id, name, description, type,
    manufacturer, model, serial_number, installation_date,
    rated_power_kw, rated_voltage_v, rated_current_a, rated_frequency_hz,
    location_in_factory, data_interval_seconds, mqtt_topic,
    is_active, is_critical
) VALUES 
(
    'c0000000-0000-0000-0000-000000000006',
    '22222222-2222-2222-2222-222222222222',
    'Compressor-EU-1',
    'Primary screw compressor',
    'compressor',
    'Kaeser',
    'DSG 90',
    'KAE2023-EU-001',
    '2023-02-12',
    90.0, 400.0, 129.9, 50.0,
    'Compressor Station - Building B',
    1,
    'factory/europe/compressor-1',
    TRUE, TRUE
),
(
    'c0000000-0000-0000-0000-000000000007',
    '22222222-2222-2222-2222-222222222222',
    'HVAC-EU-North',
    'North wing climate control',
    'hvac',
    'Daikin',
    'EWAD-TZ-C',
    'DAI2022-EU-HVAC-N',
    '2022-08-30',
    200.0, 400.0, 288.7, 50.0,
    'North Wing - Rooftop',
    10,
    'factory/europe/hvac-north',
    TRUE, TRUE
);

\echo '✓ 2 additional machines created for European facility'

-- ============================================================================
-- MACHINE STATUS (Initial state)
-- ============================================================================

\echo 'Initializing machine status...'

INSERT INTO machine_status (
    machine_id, is_running, current_mode, current_power_kw,
    operating_hours_total, energy_total_kwh, production_total_units,
    alert_level, health_score, last_updated
)
SELECT 
    id,
    FALSE,  -- Initially not running
    'offline'::operating_mode,
    0.0,
    0.0,
    0.0,
    0,
    'normal'::alert_level,
    100.0,
    NOW()
FROM machines;

\echo '✓ Machine status initialized'

-- ============================================================================
-- ENERGY TARIFFS
-- ============================================================================

\echo 'Creating sample energy tariffs...'

-- US tariff (time-of-use)
INSERT INTO energy_tariffs (
    factory_id, name, description,
    rate_per_kwh, currency, is_time_of_use,
    start_hour, end_hour, applicable_days,
    valid_from, is_active
) VALUES
(
    '11111111-1111-1111-1111-111111111111',
    'Peak Hours Rate',
    'Weekday peak hours (9 AM - 9 PM)',
    0.25,
    'USD',
    TRUE,
    9, 21,
    ARRAY[1, 2, 3, 4, 5],  -- Monday to Friday
    '2024-01-01',
    TRUE
),
(
    '11111111-1111-1111-1111-111111111111',
    'Off-Peak Rate',
    'Nights and weekends',
    0.10,
    'USD',
    TRUE,
    21, 9,
    ARRAY[0, 1, 2, 3, 4, 5, 6],  -- All days
    '2024-01-01',
    TRUE
);

-- EU tariff
INSERT INTO energy_tariffs (
    factory_id, name, description,
    rate_per_kwh, currency, is_time_of_use,
    valid_from, is_active
) VALUES
(
    '22222222-2222-2222-2222-222222222222',
    'Standard Industrial Rate',
    'Fixed rate for industrial customers',
    0.18,
    'EUR',
    FALSE,
    '2024-01-01',
    TRUE
);

\echo '✓ Energy tariffs created'

-- ============================================================================
-- CARBON EMISSION FACTORS
-- ============================================================================

\echo 'Creating carbon emission factors...'

INSERT INTO carbon_factors (
    region, grid_name, emission_factor_kg_co2_per_kwh,
    source, valid_from, is_active
) VALUES
(
    'US-California',
    'CAISO',
    0.22,
    'EPA eGRID 2023',
    '2024-01-01',
    TRUE
),
(
    'Germany',
    'Germany National Grid',
    0.35,
    'European Environment Agency 2023',
    '2024-01-01',
    TRUE
),
(
    'default',
    'Global Average',
    0.45,
    'IEA 2023 Global Average',
    '2024-01-01',
    TRUE
);

\echo '✓ Carbon emission factors created'

-- ============================================================================
-- AUDIT LOG ENTRY
-- ============================================================================

INSERT INTO audit_log (
    event_type, entity_type, action, metadata
) VALUES (
    'database_initialization',
    'system',
    'seed_data_completed',
    jsonb_build_object(
        'factories_created', 2,
        'machines_created', 8,
        'timestamp', NOW()
    )
);

\echo '✓ Audit log entry created'

-- ============================================================================
-- SUMMARY
-- ============================================================================

\echo ''
\echo '=========================================='
\echo 'Seed data loaded successfully!'
\echo '=========================================='
\echo ''
\echo 'Summary:'
\echo '  - 2 Factories created'
\echo '  - 8 Machines (SEUs) created'
\echo '    ├─ 2 Compressors (1s interval)'
\echo '    ├─ 2 HVAC Systems (10s interval)'
\echo '    ├─ 1 Conveyor Motor (10s interval)'
\echo '    ├─ 1 Hydraulic Pump (30s interval)'
\echo '    ├─ 1 Injection Molding (30s interval)'
\echo '    └─ 1 Boiler (30s interval)'
\echo '  - Machine status initialized'
\echo '  - Energy tariffs configured'
\echo '  - Carbon factors added'
\echo ''
\echo 'Demo Factory: Demo Manufacturing Plant'
\echo '  Machine IDs:'
\echo '    - Compressor-1:        c0000000-0000-0000-0000-000000000001'
\echo '    - HVAC-Main:           c0000000-0000-0000-0000-000000000002'
\echo '    - Conveyor-A:          c0000000-0000-0000-0000-000000000003'
\echo '    - Hydraulic-Pump-1:    c0000000-0000-0000-0000-000000000004'
\echo '    - Injection-Molding-1: c0000000-0000-0000-0000-000000000005'
\echo '    - Boiler-1:            c0000000-0000-0000-0000-000000000008'
\echo ''
\echo 'European Facility: European Production Facility'
\echo '  Machine IDs:'
\echo '    - Compressor-EU-1:    c0000000-0000-0000-0000-000000000006'
\echo '    - HVAC-EU-North:      c0000000-0000-0000-0000-000000000007'
\echo ''
\echo 'Ready for simulator to start generating data!'
\echo ''
