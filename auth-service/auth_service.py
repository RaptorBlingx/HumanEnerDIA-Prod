"""
Authentication Service - Core Functions
ENMS Demo Platform
Created: December 11, 2025
"""

import os
import jwt
import bcrypt
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email_validator import validate_email, EmailNotValidError
import psycopg2
from psycopg2.extras import RealDictCursor
from functools import wraps
from flask import request, jsonify
from typing import Dict, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration from Environment Variables
# ============================================================================

JWT_SECRET = os.environ.get('JWT_SECRET', 'default_secret_change_me')
JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS', 168))

# Database Configuration
POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'enms')
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')

# SMTP Configuration
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT') or 587)
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SMTP_FROM_EMAIL = os.environ.get('SMTP_FROM_EMAIL', '')
SMTP_FROM_NAME = os.environ.get('SMTP_FROM_NAME', 'HumanEnerDIA')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@humanenerdia.example')

# Email enabled only if SMTP_USER and SMTP_PASSWORD are configured
EMAIL_ENABLED = bool(SMTP_USER and SMTP_PASSWORD and SMTP_FROM_EMAIL)

# Frontend URL
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:8080')

# Admin Configuration
ADMIN_EMAILS = [email.strip().lower() for email in os.environ.get(
    'ADMIN_EMAILS', ''
).split(',') if email.strip()]

SIGNUP_ALERT_RECIPIENTS = [email.strip().lower() for email in os.environ.get(
    'SIGNUP_ALERT_RECIPIENTS', ''
).split(',') if email.strip()]

# ============================================================================
# Database Connection
# ============================================================================

def get_db_connection():
    """Create and return database connection"""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

# ============================================================================
# Password Management
# ============================================================================

def hash_password(password: str) -> str:
    """Hash password using bcrypt with 12 rounds"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

# ============================================================================
# JWT Token Management
# ============================================================================

def generate_token(user_id: int, email: str, role: str = 'user') -> str:
    """Generate JWT token for user session"""
    payload = {
        'user_id': user_id,
        'email': email,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_token(token: str) -> Dict:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return {'valid': True, 'payload': payload}
    except jwt.ExpiredSignatureError:
        return {'valid': False, 'error': 'Token expired'}
    except jwt.InvalidTokenError as e:
        return {'valid': False, 'error': f'Invalid token: {str(e)}'}

# ============================================================================
# Email Verification
# ============================================================================

def generate_verification_token() -> str:
    """Generate secure verification token"""
    return secrets.token_urlsafe(32)

def send_verification_email(email: str, token: str, full_name: str) -> bool:
    """Send email verification link to user"""
    if not EMAIL_ENABLED:
        logger.info(f"Email disabled - skipping verification email for {email}")
        return True
    
    try:
        verification_link = f"{FRONTEND_URL}/verify-email.html?token={token}"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Verify Your HumanEnerDIA Account'
        msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg['To'] = email
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #0A2463 0%, #1E3A8A 50%, #00A8E8 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 28px;">HumanEnerDIA</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">Energy Management System</p>
            </div>
            
            <div style="background: white; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <h2 style="color: #0A2463; margin-top: 0;">Welcome, {full_name}!</h2>
                
                <p>Thank you for registering with HumanEnerDIA. To complete your registration and access your dashboard, please verify your email address.</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_link}" 
                       style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #0A2463 0%, #00A8E8 100%); color: white; 
                              text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">
                        Verify Email Address
                    </a>
                </div>
                
                <p style="color: #666; font-size: 14px;">Or copy and paste this link into your browser:</p>
                <p style="background: #f5f5f5; padding: 12px; border-radius: 4px; word-break: break-all; font-size: 12px; color: #0A2463;">
                    {verification_link}
                </p>
                
                <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px; margin: 20px 0; border-radius: 4px;">
                    <p style="margin: 0; font-size: 14px; color: #856404;">
                        <strong>⏰ Important:</strong> This verification link expires in 24 hours.
                    </p>
                </div>
                
                <p style="color: #999; font-size: 13px; margin-top: 30px;">
                    If you didn't create an account with HumanEnerDIA, please ignore this email.
                </p>
            </div>
            
            <div style="background: #f8f9fa; padding: 20px; text-align: center; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="color: #666; font-size: 12px; margin: 0;">
                    © 2026 HumanEnerDIA. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Verification email sent to {email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")
        return False

# ============================================================================
# Admin Notifications
# ============================================================================

def send_signup_notification(user_data: Dict) -> bool:
    """Send new user registration notification to admins"""
    if not EMAIL_ENABLED:
        logger.info("Email disabled - skipping signup notification")
        return True
    
    try:
        recipients = SIGNUP_ALERT_RECIPIENTS
        if not recipients:
            logger.info("No signup alert recipients configured")
            return True
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = '🆕 New User Registration - HumanEnerDIA'
        msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg['To'] = ', '.join(recipients)
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #0A2463 0%, #1E3A8A 50%, #00A8E8 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">New User Registration</h1>
            </div>
            
            <div style="background: white; padding: 30px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="font-size: 16px; margin-top: 0;">A new user has registered on HumanEnerDIA:</p>
                
                <div style="background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold; width: 140px;">👤 Full Name:</td>
                            <td style="padding: 8px 0;">{user_data.get('full_name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">📧 Email:</td>
                            <td style="padding: 8px 0;">{user_data.get('email', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">🏢 Organization:</td>
                            <td style="padding: 8px 0;">{user_data.get('organization', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">💼 Position:</td>
                            <td style="padding: 8px 0;">{user_data.get('position', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">📱 Mobile:</td>
                            <td style="padding: 8px 0;">{user_data.get('mobile', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">🌍 Country:</td>
                            <td style="padding: 8px 0;">{user_data.get('country', 'N/A')}</td>
                        </tr>
                        <tr style="border-top: 1px solid #e0e0e0;">
                            <td style="padding: 12px 0 8px 0; font-weight: bold;">🌐 IP Address:</td>
                            <td style="padding: 12px 0 8px 0; color: #666;">{user_data.get('ip_address', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-weight: bold;">⏰ Timestamp:</td>
                            <td style="padding: 8px 0; color: #666;">{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                        </tr>
                    </table>
                </div>
                
                <div style="text-align: center; margin: 25px 0;">
                    <a href="{FRONTEND_URL}/admin/dashboard.html" 
                       style="display: inline-block; padding: 12px 28px; background: linear-gradient(135deg, #0A2463 0%, #00A8E8 100%); color: white; 
                              text-decoration: none; border-radius: 6px; font-weight: bold;">
                        View Admin Dashboard
                    </a>
                </div>
            </div>
            
            <div style="background: #f8f9fa; padding: 20px; text-align: center; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="color: #666; font-size: 12px; margin: 0;">
                    © 2026 HumanEnerDIA - Automated Notification
                </p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Signup notification sent to admins")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send signup notification: {e}")
        return False

# ============================================================================
# User Registration
# ============================================================================

def register_user(email: str, password: str, organization: str, full_name: str,
                 position: str, mobile: str, country: str, ip_address: str = None,
                 user_agent: str = None) -> Dict:
    """Register new user with email verification"""
    try:
        # Validate and normalize email
        email = email.lower().strip()
        try:
            valid = validate_email(email)
            email = valid.email
        except EmailNotValidError as e:
            return {'success': False, 'error': f'Invalid email: {str(e)}'}
        
        # Validate password
        if len(password) < 8:
            return {'success': False, 'error': 'Password must be at least 8 characters'}
        
        # Determine role
        user_role = 'admin' if email in ADMIN_EMAILS else 'user'
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if email already exists
        cursor.execute("SELECT id FROM demo_users WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'Email already registered'}
        
        # Hash password and generate verification token
        password_hash = hash_password(password)
        verification_token = generate_verification_token()
        
        # If email is disabled, auto-verify user
        email_verified = not EMAIL_ENABLED
        verified_at_sql = "NOW()" if email_verified else "NULL"
        
        # Insert user
        cursor.execute(f"""
            INSERT INTO demo_users 
            (email, password_hash, organization, full_name, position, mobile, country, role,
             verification_token, verification_sent_at, email_verified, verified_at, ip_address_signup, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, {verified_at_sql}, %s, %s)
            RETURNING id, email, full_name, role
        """, (email, password_hash, organization, full_name, position, mobile, country,
              user_role, verification_token, email_verified, ip_address, user_agent))
        
        user = cursor.fetchone()
        conn.commit()
        
        # Log audit
        cursor.execute("""
            INSERT INTO demo_audit_log (user_id, action, status, ip_address, user_agent, metadata)
            VALUES (%s, 'REGISTER', 'SUCCESS', %s, %s, %s)
        """, (user['id'], ip_address, user_agent, 
              psycopg2.extras.Json({'organization': organization, 'country': country})))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        # Send emails (non-blocking, failures logged but don't stop registration)
        send_verification_email(email, verification_token, full_name)
        send_signup_notification({
            'full_name': full_name,
            'email': email,
            'organization': organization,
            'position': position,
            'mobile': mobile,
            'country': country,
            'ip_address': ip_address
        })
        
        # Different message based on email status
        if EMAIL_ENABLED:
            message = 'Registration successful. Please check your email to verify your account.'
        else:
            message = 'Registration successful. Your account is ready to use. You can log in now.'
        
        return {
            'success': True,
            'message': message,
            'user_id': user['id'],
            'role': user['role'],
            'email_verified': email_verified
        }
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return {'success': False, 'error': 'Registration failed. Please try again.'}

# ============================================================================
# Email Verification
# ============================================================================

def verify_email_token(token: str) -> Dict:
    """Verify email using token"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Find user with token
        cursor.execute("""
            SELECT id, email, full_name, email_verified, verification_sent_at
            FROM demo_users
            WHERE verification_token = %s
        """, (token,))
        
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'Invalid verification token'}
        
        if user['email_verified']:
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'Email already verified'}
        
        # Check token expiration (24 hours)
        if user['verification_sent_at']:
            expiry = user['verification_sent_at'] + timedelta(hours=24)
            if datetime.now(user['verification_sent_at'].tzinfo) > expiry:
                cursor.close()
                conn.close()
                return {'success': False, 'error': 'Verification token expired'}
        
        # Mark email as verified
        cursor.execute("""
            UPDATE demo_users
            SET email_verified = true, 
                verified_at = NOW(),
                verification_token = NULL
            WHERE id = %s
        """, (user['id'],))
        
        conn.commit()
        
        # Log audit
        cursor.execute("""
            INSERT INTO demo_audit_log (user_id, action, status, metadata)
            VALUES (%s, 'EMAIL_VERIFY', 'SUCCESS', %s)
        """, (user['id'], psycopg2.extras.Json({'method': 'email_token'})))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        logger.info(f"Email verified for user {user['email']}")
        
        return {
            'success': True,
            'message': 'Email verified successfully! You can now log in.',
            'email': user['email']
        }
        
    except Exception as e:
        logger.error(f"Email verification error: {e}")
        return {'success': False, 'error': 'Verification failed. Please try again.'}

# ============================================================================
# User Login
# ============================================================================

def login_user(email: str, password: str, ip_address: str = None, user_agent: str = None) -> Dict:
    """Authenticate user and create session"""
    try:
        email = email.lower().strip()
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get user
        cursor.execute("""
            SELECT id, email, password_hash, full_name, organization, role, 
                   email_verified, is_active
            FROM demo_users
            WHERE email = %s
        """, (email,))
        
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'Invalid email or password'}
        
        # Verify password
        if not verify_password(password, user['password_hash']):
            # Log failed attempt
            cursor.execute("""
                INSERT INTO demo_audit_log (user_id, action, status, ip_address, user_agent)
                VALUES (%s, 'LOGIN', 'FAILED', %s, %s)
            """, (user['id'], ip_address, user_agent))
            conn.commit()
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'Invalid email or password'}
        
        # Check if account is active
        if not user['is_active']:
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'Account is deactivated'}
        
        # Check email verification
        if not user['email_verified']:
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'Please verify your email before logging in'}
        
        # Generate JWT token
        token = generate_token(user['id'], user['email'], user['role'])
        
        # Create session
        expires_at = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
        cursor.execute("""
            INSERT INTO demo_sessions (user_id, session_token, expires_at, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (user['id'], token, expires_at, ip_address, user_agent))
        
        session = cursor.fetchone()
        
        # Update last login
        cursor.execute("""
            UPDATE demo_users SET last_login = NOW() WHERE id = %s
        """, (user['id'],))
        
        # Log successful login
        cursor.execute("""
            INSERT INTO demo_audit_log (user_id, action, status, ip_address, user_agent)
            VALUES (%s, 'LOGIN', 'SUCCESS', %s, %s)
        """, (user['id'], ip_address, user_agent))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"User {email} logged in successfully")
        
        return {
            'success': True,
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': user['id'],
                'email': user['email'],
                'full_name': user['full_name'],
                'organization': user['organization'],
                'role': user['role']
            }
        }
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return {'success': False, 'error': 'Login failed. Please try again.'}

# ============================================================================
# Admin Access Control Decorator
# ============================================================================

def require_admin(f):
    """Decorator to require admin role for endpoint access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        token_data = verify_token(token)
        
        if not token_data['valid']:
            return jsonify({'success': False, 'error': token_data['error']}), 401
        
        user_email = token_data['payload'].get('email', '').lower()
        
        # Check admin allowlist
        if user_email not in ADMIN_EMAILS:
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        # Verify role in database
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT role, is_active, email_verified FROM demo_users WHERE email = %s",
                (user_email,)
            )
            user_row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not user_row or user_row['role'] != 'admin' or not user_row['is_active'] or not user_row['email_verified']:
                return jsonify({'success': False, 'error': 'Admin access required'}), 403
            
            # Attach user info to request
            request.user = token_data['payload']
            return f(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Admin verification error: {e}")
            return jsonify({'success': False, 'error': 'Authorization failed'}), 500
    
    return decorated_function

# ============================================================================
# Password Reset Functions
# ============================================================================

def request_password_reset(email: str) -> Dict:
    """Send password reset email"""
    try:
        email = email.lower().strip()
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, full_name, email_verified
            FROM demo_users
            WHERE email = %s AND is_active = true
        """, (email,))
        
        user = cursor.fetchone()
        
        # Don't reveal if email exists (security best practice)
        if not user:
            cursor.close()
            conn.close()
            return {'success': True, 'message': 'If the email exists, a reset link has been sent.'}
        
        if not user['email_verified']:
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'Please verify your email first'}
        
        # Generate reset token
        reset_token = generate_verification_token()
        
        cursor.execute("""
            UPDATE demo_users
            SET password_reset_token = %s, password_reset_sent_at = NOW()
            WHERE id = %s
        """, (reset_token, user['id']))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Send reset email
        send_password_reset_email(email, reset_token, user['full_name'])
        
        return {'success': True, 'message': 'Password reset link sent to your email'}
        
    except Exception as e:
        logger.error(f"Password reset request error: {e}")
        return {'success': False, 'error': 'Failed to process request'}

def send_password_reset_email(email: str, token: str, full_name: str) -> bool:
    """Send password reset email"""
    try:
        reset_link = f"{FRONTEND_URL}/reset-password.html?token={token}"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Reset Your ENMS Password'
        msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg['To'] = email
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Password Reset Request</h2>
            <p>Hello {full_name},</p>
            <p>We received a request to reset your password. Click the button below to create a new password:</p>
            <a href="{reset_link}" style="display: inline-block; padding: 12px 24px; 
               background: #3b82f6; color: white; text-decoration: none; border-radius: 6px;">
               Reset Password
            </a>
            <p>Link expires in 1 hour.</p>
            <p>If you didn't request this, please ignore this email.</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        return True
    except Exception as e:
        logger.error(f"Failed to send password reset email: {e}")
        return False

def reset_password(token: str, new_password: str) -> Dict:
    """Reset password using token"""
    try:
        if len(new_password) < 8:
            return {'success': False, 'error': 'Password must be at least 8 characters'}
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, email, password_reset_sent_at
            FROM demo_users
            WHERE password_reset_token = %s AND is_active = true
        """, (token,))
        
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return {'success': False, 'error': 'Invalid or expired reset token'}
        
        # Check token expiration (1 hour)
        if user['password_reset_sent_at']:
            expiry = user['password_reset_sent_at'] + timedelta(hours=1)
            if datetime.now(user['password_reset_sent_at'].tzinfo) > expiry:
                cursor.close()
                conn.close()
                return {'success': False, 'error': 'Reset token expired'}
        
        # Hash new password
        password_hash = hash_password(new_password)
        
        # Update password and clear reset token
        cursor.execute("""
            UPDATE demo_users
            SET password_hash = %s,
                password_reset_token = NULL,
                password_reset_sent_at = NULL
            WHERE id = %s
        """, (password_hash, user['id']))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return {'success': True, 'message': 'Password reset successfully'}
        
    except Exception as e:
        logger.error(f"Password reset error: {e}")
        return {'success': False, 'error': 'Failed to reset password'}
