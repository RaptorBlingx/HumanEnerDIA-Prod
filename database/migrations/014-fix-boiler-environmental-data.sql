-- ============================================================================
-- Migration 014: Repair Boiler-1 historical simulator data
-- ============================================================================
-- Purpose: Rebuild historical Boiler-1 production/environmental rows from the
-- electricity stream so all published telemetry for a timestamp describes the
-- same underlying physical state.

\echo '=========================================='
\echo 'Repairing Boiler-1 historical simulator data...'
\echo '=========================================='

-- Large Timescale hypertable updates can exceed the default decompression cap.
-- Run this repair with an unlimited cap for the current psql session.
SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0;
SELECT pg_advisory_lock(hashtext('boiler_repair_014'));

DO $$
DECLARE
    v_boiler_id UUID := 'c0000000-0000-0000-0000-000000000008';
    v_rated_power_kw NUMERIC;
    v_min_time TIMESTAMPTZ;
    v_inserted_env INTEGER;
    v_updated_env INTEGER;
    v_inserted_prod INTEGER;
    v_updated_prod INTEGER;
BEGIN
    SELECT rated_power_kw INTO v_rated_power_kw
    FROM machines
    WHERE id = v_boiler_id;

    IF v_rated_power_kw IS NULL THEN
        RAISE NOTICE 'Boiler-1 not found, skipping...';
        RETURN;
    END IF;

    WITH boiler_energy AS (
        SELECT
            er.time,
            er.machine_id,
            er.power_kw,
            GREATEST(0.05, LEAST(1.0, er.power_kw / NULLIF(v_rated_power_kw, 0))) AS effective_load,
            EXTRACT(HOUR FROM er.time) AS hour_of_day,
            EXTRACT(DOY FROM er.time) AS day_of_year
        FROM energy_readings er
        WHERE er.machine_id = v_boiler_id
          AND er.energy_type = 'electricity'
    ), derived AS (
        SELECT
            be.time,
            be.machine_id,
            be.effective_load,
            LEAST(
                35.0,
                GREATEST(
                    -10.0,
                    10.0 + 15.0 * SIN(2 * PI() * ((be.day_of_year - 15) / 365.0))
                    + 5.0 * SIN(2 * PI() * ((be.hour_of_day - 6) / 24.0))
                )
            ) AS outdoor_temp_c,
            ((v_rated_power_kw * 1.5 * be.effective_load) / 0.85) / 10.55 AS gas_flow_m3h,
            (v_rated_power_kw * 1.5 * be.effective_load * 0.85) / 2.26 AS steam_kg_per_hour
        FROM boiler_energy be
    )
    INSERT INTO environmental_data (
        time,
        machine_id,
        outdoor_temp_c,
        indoor_temp_c,
        machine_temp_c,
        outdoor_humidity_percent,
        indoor_humidity_percent,
        pressure_bar,
        flow_rate_m3h,
        vibration_mm_s
    )
    SELECT
        d.time,
        d.machine_id,
        ROUND(d.outdoor_temp_c::NUMERIC, 2),
        ROUND((d.outdoor_temp_c + 8.0 + d.effective_load * 2.5)::NUMERIC, 2),
        ROUND((170.0 + d.effective_load * 15.0 + ABS(d.outdoor_temp_c) * 0.2)::NUMERIC, 2),
        ROUND((55.0 + 15.0 * COS(2 * PI() * ((EXTRACT(DOY FROM d.time) - 15) / 365.0)))::NUMERIC, 2),
        ROUND((45.0 + d.effective_load * 5.0)::NUMERIC, 2),
        ROUND((9.5 + d.effective_load * 1.0)::NUMERIC, 3),
        ROUND(d.gas_flow_m3h::NUMERIC, 3),
        ROUND((0.6 + d.effective_load * 0.9)::NUMERIC, 4)
    FROM derived d
    LEFT JOIN environmental_data env
      ON env.machine_id = d.machine_id
     AND env.time = d.time
        WHERE env.time IS NULL
        ON CONFLICT (machine_id, time) DO NOTHING;

    GET DIAGNOSTICS v_inserted_env = ROW_COUNT;

    WITH boiler_energy AS (
        SELECT
            er.time,
            er.machine_id,
            er.power_kw,
            GREATEST(0.05, LEAST(1.0, er.power_kw / NULLIF(v_rated_power_kw, 0))) AS effective_load,
            EXTRACT(HOUR FROM er.time) AS hour_of_day,
            EXTRACT(DOY FROM er.time) AS day_of_year
        FROM energy_readings er
        WHERE er.machine_id = v_boiler_id
          AND er.energy_type = 'electricity'
    ), derived AS (
        SELECT
            be.time,
            be.machine_id,
            be.effective_load,
            LEAST(
                35.0,
                GREATEST(
                    -10.0,
                    10.0 + 15.0 * SIN(2 * PI() * ((be.day_of_year - 15) / 365.0))
                    + 5.0 * SIN(2 * PI() * ((be.hour_of_day - 6) / 24.0))
                )
            ) AS outdoor_temp_c,
            ((v_rated_power_kw * 1.5 * be.effective_load) / 0.85) / 10.55 AS gas_flow_m3h
        FROM boiler_energy be
    )
    UPDATE environmental_data env
    SET
        outdoor_temp_c = ROUND(d.outdoor_temp_c::NUMERIC, 2),
        indoor_temp_c = ROUND((d.outdoor_temp_c + 8.0 + d.effective_load * 2.5)::NUMERIC, 2),
        machine_temp_c = ROUND((170.0 + d.effective_load * 15.0 + ABS(d.outdoor_temp_c) * 0.2)::NUMERIC, 2),
        outdoor_humidity_percent = ROUND((55.0 + 15.0 * COS(2 * PI() * ((EXTRACT(DOY FROM env.time) - 15) / 365.0)))::NUMERIC, 2),
        indoor_humidity_percent = ROUND((45.0 + d.effective_load * 5.0)::NUMERIC, 2),
        pressure_bar = ROUND((9.5 + d.effective_load * 1.0)::NUMERIC, 3),
        flow_rate_m3h = ROUND(d.gas_flow_m3h::NUMERIC, 3),
        vibration_mm_s = ROUND((0.6 + d.effective_load * 0.9)::NUMERIC, 4)
    FROM derived d
    WHERE env.machine_id = d.machine_id
      AND env.time = d.time;

    GET DIAGNOSTICS v_updated_env = ROW_COUNT;

    WITH boiler_energy AS (
        SELECT
            er.time,
            er.machine_id,
            GREATEST(0.05, LEAST(1.0, er.power_kw / NULLIF(v_rated_power_kw, 0))) AS effective_load
        FROM energy_readings er
        WHERE er.machine_id = v_boiler_id
          AND er.energy_type = 'electricity'
    ), derived AS (
        SELECT
            be.time,
            be.machine_id,
            be.effective_load,
            (v_rated_power_kw * 1.5 * be.effective_load * 0.85) / 2.26 AS steam_kg_per_hour,
            GREATEST(
                1,
                FLOOR((((v_rated_power_kw * 1.5 * be.effective_load * 0.85) / 2.26) * (30.0 / 3600.0) * 10.0))::INT
            ) AS production_count
        FROM boiler_energy be
    )
    INSERT INTO production_data (
        time,
        machine_id,
        production_count,
        production_count_good,
        production_count_bad,
        throughput_units_per_hour,
        speed_percent
    )
    SELECT
        d.time,
        d.machine_id,
        d.production_count,
        d.production_count,
        0,
        ROUND(d.steam_kg_per_hour::NUMERIC, 2),
        ROUND((d.effective_load * 100.0)::NUMERIC, 2)
    FROM derived d
    LEFT JOIN production_data prod
      ON prod.machine_id = d.machine_id
     AND prod.time = d.time
        WHERE prod.time IS NULL
        ON CONFLICT (machine_id, time) DO NOTHING;

    GET DIAGNOSTICS v_inserted_prod = ROW_COUNT;

    WITH boiler_energy AS (
        SELECT
            er.time,
            er.machine_id,
            GREATEST(0.05, LEAST(1.0, er.power_kw / NULLIF(v_rated_power_kw, 0))) AS effective_load
        FROM energy_readings er
        WHERE er.machine_id = v_boiler_id
          AND er.energy_type = 'electricity'
    ), derived AS (
        SELECT
            be.time,
            be.machine_id,
            be.effective_load,
            (v_rated_power_kw * 1.5 * be.effective_load * 0.85) / 2.26 AS steam_kg_per_hour,
            GREATEST(
                1,
                FLOOR((((v_rated_power_kw * 1.5 * be.effective_load * 0.85) / 2.26) * (30.0 / 3600.0) * 10.0))::INT
            ) AS production_count
        FROM boiler_energy be
    )
    UPDATE production_data prod
    SET
        production_count = d.production_count,
        production_count_good = d.production_count,
        production_count_bad = 0,
        throughput_units_per_hour = ROUND(d.steam_kg_per_hour::NUMERIC, 2),
        speed_percent = ROUND((d.effective_load * 100.0)::NUMERIC, 2)
    FROM derived d
    WHERE prod.machine_id = d.machine_id
      AND prod.time = d.time;

    GET DIAGNOSTICS v_updated_prod = ROW_COUNT;

    SELECT MIN(time) INTO v_min_time
    FROM energy_readings
        WHERE machine_id = v_boiler_id
            AND energy_type = 'electricity';

    IF v_min_time IS NOT NULL THEN
        CALL refresh_continuous_aggregate('production_data_1hour'::regclass, v_min_time, NOW());
        CALL refresh_continuous_aggregate('environmental_data_1hour'::regclass, v_min_time, NOW());
        CALL refresh_continuous_aggregate('production_data_15min'::regclass, v_min_time, NOW());
        CALL refresh_continuous_aggregate('environmental_data_15min'::regclass, v_min_time, NOW());
        CALL refresh_continuous_aggregate('production_data_1min'::regclass, v_min_time, NOW());
        CALL refresh_continuous_aggregate('environmental_data_1min'::regclass, v_min_time, NOW());
        CALL refresh_continuous_aggregate('environmental_degree_days_daily'::regclass, v_min_time, NOW());
        CALL refresh_continuous_aggregate('production_data_1day'::regclass, v_min_time, NOW());
    END IF;

    RAISE NOTICE '✓ Inserted % missing Boiler-1 environmental rows', v_inserted_env;
    RAISE NOTICE '✓ Updated % Boiler-1 environmental rows', v_updated_env;
    RAISE NOTICE '✓ Inserted % missing Boiler-1 production rows', v_inserted_prod;
    RAISE NOTICE '✓ Updated % Boiler-1 production rows', v_updated_prod;
    RAISE NOTICE '✓ Refreshed Boiler-1 continuous aggregates';
END $$;

RESET timescaledb.max_tuples_decompressed_per_dml_transaction;
SELECT pg_advisory_unlock(hashtext('boiler_repair_014'));