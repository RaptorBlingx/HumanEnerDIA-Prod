-- ============================================================================
-- Authentication System Database Schema
-- Created: December 11, 2025
-- Purpose: User authentication, sessions, and audit logging for ENMS Demo
-- ============================================================================

-- ============================================================================
-- 1. Users Table (demo_users)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.demo_users (
    id SERIAL PRIMARY KEY,
    
    -- Core Authentication
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    
    -- User Information
    organization VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    position VARCHAR(255) NOT NULL,
    mobile VARCHAR(50),
    country VARCHAR(100) NOT NULL,
    
    -- Email Verification
    email_verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(255),
    verification_sent_at TIMESTAMP WITH TIME ZONE,
    verified_at TIMESTAMP WITH TIME ZONE,
    
    -- Password Reset
    password_reset_token VARCHAR(255),
    password_reset_sent_at TIMESTAMP WITH TIME ZONE,
    
    -- Role Management
    role VARCHAR(50) DEFAULT 'user', -- 'user', 'admin'
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Account Status
    is_active BOOLEAN DEFAULT TRUE,
    deactivated_at TIMESTAMP WITH TIME ZONE,
    
    -- Tracking
    ip_address_signup VARCHAR(50),
    user_agent TEXT,
    
    CONSTRAINT email_lowercase CHECK (email = LOWER(email))
);

-- Indexes for demo_users
CREATE INDEX IF NOT EXISTS idx_demo_users_email ON public.demo_users(email);
CREATE INDEX IF NOT EXISTS idx_demo_users_verification_token ON public.demo_users(verification_token);
CREATE INDEX IF NOT EXISTS idx_demo_users_password_reset_token ON public.demo_users(password_reset_token);
CREATE INDEX IF NOT EXISTS idx_demo_users_created_at ON public.demo_users(created_at);
CREATE INDEX IF NOT EXISTS idx_demo_users_role ON public.demo_users(role);

-- ============================================================================
-- 2. Sessions Table (demo_sessions)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.demo_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.demo_users(id) ON DELETE CASCADE,
    session_token TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address VARCHAR(50),
    user_agent TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- Indexes for demo_sessions
CREATE INDEX IF NOT EXISTS idx_demo_sessions_user_id ON public.demo_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_demo_sessions_token ON public.demo_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_demo_sessions_expires_at ON public.demo_sessions(expires_at);

-- ============================================================================
-- 3. Audit Log Table (demo_audit_log)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.demo_audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.demo_users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address VARCHAR(50),
    user_agent TEXT,
    metadata JSONB
);

-- Indexes for demo_audit_log
CREATE INDEX IF NOT EXISTS idx_demo_audit_log_user_id ON public.demo_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_demo_audit_log_action ON public.demo_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_demo_audit_log_timestamp ON public.demo_audit_log(timestamp);

-- ============================================================================
-- 4. Helper Functions
-- ============================================================================

-- Function to update updated_at timestamp automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at on demo_users
DROP TRIGGER IF EXISTS update_demo_users_updated_at ON public.demo_users;
CREATE TRIGGER update_demo_users_updated_at
    BEFORE UPDATE ON public.demo_users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 5. Cleanup Function for Expired Sessions
-- ============================================================================
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void AS $$
BEGIN
    DELETE FROM public.demo_sessions 
    WHERE expires_at < NOW() OR (is_active = FALSE AND created_at < NOW() - INTERVAL '30 days');
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 6. Grant Permissions
-- ============================================================================
-- Grant permissions to current database user
GRANT ALL PRIVILEGES ON public.demo_users TO CURRENT_USER;
GRANT ALL PRIVILEGES ON public.demo_sessions TO CURRENT_USER;
GRANT ALL PRIVILEGES ON public.demo_audit_log TO CURRENT_USER;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO CURRENT_USER;

-- ============================================================================
-- Initialization Complete
-- ============================================================================
SELECT 'Authentication schema initialized successfully!' AS status;
