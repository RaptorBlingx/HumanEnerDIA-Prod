-- ============================================================================
-- EnMS - Energy Management System
-- Database Initialization Script 01: Extensions
-- ============================================================================
-- This script enables required PostgreSQL extensions
-- Execution order: First (01)
-- ============================================================================

\echo '=========================================='
\echo 'Installing PostgreSQL Extensions...'
\echo '=========================================='

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
\echo '✓ UUID extension enabled'

-- Enable TimescaleDB (time-series database)
CREATE EXTENSION IF NOT EXISTS timescaledb;
\echo '✓ TimescaleDB extension enabled'

-- Enable PostGIS (if needed for location-based queries in future)
-- CREATE EXTENSION IF NOT EXISTS postgis;

-- Enable pg_stat_statements for query performance monitoring
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
\echo '✓ pg_stat_statements enabled'

-- Enable tablefunc for crosstab queries (useful for pivot tables)
CREATE EXTENSION IF NOT EXISTS tablefunc;
\echo '✓ tablefunc enabled'

\echo ''
\echo '=========================================='
\echo 'Extensions installed successfully!'
\echo '=========================================='
\echo ''
