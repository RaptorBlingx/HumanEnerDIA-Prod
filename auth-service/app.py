"""
Authentication Service API
ENMS Demo Platform
Created: December 11, 2025
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from auth_service import (
    register_user,
    login_user,
    verify_email_token,
    request_password_reset,
    reset_password,
    require_admin,
    get_db_connection,
    verify_token
)
from psycopg2.extras import RealDictCursor
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configure CORS
CORS(app, resources={
    r"/api/*": {
        "origins": ["*"],  # Configure appropriately for production
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# ============================================================================
# Health Check
# ============================================================================

@app.route('/api/auth/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'auth-service',
        'status': 'healthy'
    }), 200

# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """Register new user"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'password', 'organization', 'full_name', 'position', 'country']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        result = register_user(
            email=data['email'],
            password=data['password'],
            organization=data['organization'],
            full_name=data['full_name'],
            position=data['position'],
            mobile=data.get('mobile', ''),
            country=data['country'],
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        
        status_code = 201 if result['success'] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Registration endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Registration failed'
        }), 500

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """User login"""
    try:
        data = request.get_json()
        
        if not data.get('email') or not data.get('password'):
            return jsonify({
                'success': False,
                'error': 'Email and password are required'
            }), 400
        
        result = login_user(
            email=data['email'],
            password=data['password'],
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')
        )
        
        status_code = 200 if result['success'] else 401
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Login endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Login failed'
        }), 500

@app.route('/api/auth/verify-email', methods=['POST'])
def auth_verify_email():
    """Verify email with token"""
    try:
        data = request.get_json()
        
        if not data.get('token'):
            return jsonify({
                'success': False,
                'error': 'Verification token is required'
            }), 400
        
        result = verify_email_token(data['token'])
        status_code = 200 if result['success'] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Email verification endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Verification failed'
        }), 500

@app.route('/api/auth/forgot-password', methods=['POST'])
def auth_forgot_password():
    """Request password reset"""
    try:
        data = request.get_json()
        
        if not data.get('email'):
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        result = request_password_reset(data['email'])
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Forgot password endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Request failed'
        }), 500

@app.route('/api/auth/reset-password', methods=['POST'])
def auth_reset_password():
    """Reset password with token"""
    try:
        data = request.get_json()
        
        if not data.get('token') or not data.get('new_password'):
            return jsonify({
                'success': False,
                'error': 'Token and new password are required'
            }), 400
        
        result = reset_password(data['token'], data['new_password'])
        status_code = 200 if result['success'] else 400
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Reset password endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Password reset failed'
        }), 500

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """Logout user (invalidate session)"""
    try:
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'success': False,
                'error': 'No authorization token'
            }), 401
        
        token = auth_header.split(' ')[1]
        token_data = verify_token(token)
        
        if token_data['valid']:
            # Invalidate session in database
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE demo_sessions 
                SET is_active = false 
                WHERE session_token = %s
            """, (token,))
            conn.commit()
            cursor.close()
            conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Logout endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Logout failed'
        }), 500

@app.route('/api/auth/verify-token', methods=['POST'])
def auth_verify_token():
    """Verify JWT token validity"""
    try:
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'success': False,
                'valid': False,
                'error': 'No authorization token'
            }), 401
        
        token = auth_header.split(' ')[1]
        token_data = verify_token(token)
        
        if token_data['valid']:
            return jsonify({
                'success': True,
                'valid': True,
                'user': token_data['payload']
            }), 200
        else:
            return jsonify({
                'success': False,
                'valid': False,
                'error': token_data['error']
            }), 401
            
    except Exception as e:
        logger.error(f"Token verification endpoint error: {e}")
        return jsonify({
            'success': False,
            'valid': False,
            'error': 'Verification failed'
        }), 500

# ============================================================================
# Admin Endpoints
# ============================================================================

@app.route('/api/admin/stats', methods=['GET'])
@require_admin
def admin_get_stats():
    """Get user statistics (admin only)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_users,
                COUNT(*) FILTER (WHERE email_verified = true) as verified_users,
                COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as new_today,
                COUNT(*) FILTER (WHERE last_login >= NOW() - INTERVAL '7 days') as active_7_days,
                COUNT(*) FILTER (WHERE role = 'admin') as admin_users
            FROM demo_users
            WHERE is_active = true
        """)
        
        stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': dict(stats)
        }), 200
        
    except Exception as e:
        logger.error(f"Admin stats endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch statistics'
        }), 500

@app.route('/api/admin/users', methods=['GET'])
@require_admin
def admin_get_users():
    """Get paginated user list with search (admin only)"""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        search = request.args.get('search', '').strip()
        
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Build query with search
        where_clause = ""
        params = []
        
        if search:
            where_clause = """
                WHERE (full_name ILIKE %s OR email ILIKE %s OR organization ILIKE %s)
            """
            search_pattern = f'%{search}%'
            params = [search_pattern, search_pattern, search_pattern]
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM demo_users {where_clause}"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()['total']
        
        # Get users
        users_query = f"""
            SELECT id, email, full_name, organization, position, mobile, country,
                   email_verified, role, created_at, last_login, is_active
            FROM demo_users
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(users_query, params + [limit, offset])
        users = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Convert datetime objects to ISO format
        for user in users:
            if user['created_at']:
                user['created_at'] = user['created_at'].isoformat()
            if user['last_login']:
                user['last_login'] = user['last_login'].isoformat()
        
        total_pages = (total_count + limit - 1) // limit
        
        return jsonify({
            'success': True,
            'users': users,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Admin users endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch users'
        }), 500

@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@require_admin
def admin_get_user(user_id):
    """Get detailed user information (admin only)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, email, full_name, organization, position, mobile, country,
                   email_verified, verified_at, role, created_at, last_login, is_active,
                   ip_address_signup, deactivated_at
            FROM demo_users
            WHERE id = %s
        """, (user_id,))
        
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Get user's sessions
        cursor.execute("""
            SELECT id, created_at, expires_at, last_activity, ip_address, is_active
            FROM demo_sessions
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (user_id,))
        
        sessions = cursor.fetchall()
        
        # Get user's audit log
        cursor.execute("""
            SELECT action, status, timestamp, ip_address, metadata
            FROM demo_audit_log
            WHERE user_id = %s
            ORDER BY timestamp DESC
            LIMIT 20
        """, (user_id,))
        
        audit_logs = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Convert datetime objects to ISO format
        for key in ['created_at', 'last_login', 'verified_at', 'deactivated_at']:
            if user.get(key):
                user[key] = user[key].isoformat()
        
        for session in sessions:
            for key in ['created_at', 'expires_at', 'last_activity']:
                if session.get(key):
                    session[key] = session[key].isoformat()
        
        for log in audit_logs:
            if log.get('timestamp'):
                log['timestamp'] = log['timestamp'].isoformat()
        
        return jsonify({
            'success': True,
            'user': dict(user),
            'sessions': [dict(s) for s in sessions],
            'audit_logs': [dict(l) for l in audit_logs]
        }), 200
        
    except Exception as e:
        logger.error(f"Admin get user endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch user details'
        }), 500

@app.route('/api/admin/users/<int:user_id>/toggle-active', methods=['POST'])
@require_admin
def admin_toggle_user_active(user_id):
    """Activate/deactivate user account (admin only)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT is_active FROM demo_users WHERE id = %s
        """, (user_id,))
        
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        new_status = not user['is_active']
        deactivated_at = 'NOW()' if not new_status else 'NULL'
        
        cursor.execute(f"""
            UPDATE demo_users
            SET is_active = %s, deactivated_at = {deactivated_at}
            WHERE id = %s
        """, (new_status, user_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        action = 'activated' if new_status else 'deactivated'
        
        return jsonify({
            'success': True,
            'message': f'User {action} successfully',
            'is_active': new_status
        }), 200
        
    except Exception as e:
        logger.error(f"Admin toggle user endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to update user status'
        }), 500

@app.route('/api/admin/export-users', methods=['GET'])
@require_admin
def admin_export_users():
    """Export users to CSV (admin only)"""
    try:
        import csv
        from io import StringIO
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT id, email, full_name, organization, position, mobile, country,
                   email_verified, role, created_at, last_login, is_active
            FROM demo_users
            ORDER BY created_at DESC
        """)
        
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Create CSV
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'id', 'email', 'full_name', 'organization', 'position', 'mobile', 
            'country', 'email_verified', 'role', 'created_at', 'last_login', 'is_active'
        ])
        writer.writeheader()
        
        for user in users:
            user_dict = dict(user)
            if user_dict['created_at']:
                user_dict['created_at'] = user_dict['created_at'].isoformat()
            if user_dict['last_login']:
                user_dict['last_login'] = user_dict['last_login'].isoformat()
            writer.writerow(user_dict)
        
        csv_content = output.getvalue()
        output.close()
        
        from flask import make_response
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = 'attachment; filename=users_export.csv'
        
        return response
        
    except Exception as e:
        logger.error(f"Admin export endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to export users'
        }), 500

# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

# ============================================================================
# Contact Form
# ============================================================================

@app.route('/api/contact', methods=['POST'])
def contact_form():
    """Handle contact form submissions"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'email', 'subject', 'message']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'{field.capitalize()} is required'
                }), 400
        
        # Get admin emails from environment
        admin_emails = os.environ.get('ADMIN_EMAILS', '').split(',')
        admin_emails = [email.strip() for email in admin_emails if email.strip()]
        
        if not admin_emails:
            logger.error("No admin emails configured for contact form")
            return jsonify({
                'success': False,
                'error': 'Contact form is not configured'
            }), 500
        
        # Send email to admins
        success = send_contact_form_email(data, admin_emails)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Thank you for contacting us! We will get back to you within 24 hours.'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to send message. Please try again later.'
            }), 500
            
    except Exception as e:
        logger.error(f"Contact form endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to process contact form'
        }), 500

def send_contact_form_email(data: dict, admin_emails: list) -> bool:
    """Send contact form data to admin emails"""
    from auth_service import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL, SMTP_FROM_NAME, EMAIL_ENABLED
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import smtplib
    
    if not EMAIL_ENABLED:
        logger.warning("Email not enabled - skipping contact form email")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"📧 Contact Form: {data.get('subject', 'No Subject')}"
        msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg['To'] = ', '.join(admin_emails)
        msg['Reply-To'] = data.get('email', '')
        
        # Create HTML email
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f5f5f5;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 20px 0;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                            
                            <!-- Header -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); padding: 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">
                                        📧 New Contact Form Submission
                                    </h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; opacity: 0.95;">
                                        HumanEnerDIA Website
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- Content -->
                            <tr>
                                <td style="padding: 30px;">
                                    <h2 style="color: #333; font-size: 18px; margin: 0 0 20px 0;">Contact Details</h2>
                                    
                                    <table width="100%" cellpadding="8" cellspacing="0" style="border: 1px solid #e5e7eb; border-radius: 6px;">
                                        <tr style="background-color: #f9fafb;">
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; width: 30%; font-weight: 600; color: #4b5563;">
                                                Full Name:
                                            </td>
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; color: #1f2937;">
                                                {data.get('name', 'N/A')}
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-weight: 600; color: #4b5563;">
                                                Email:
                                            </td>
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; color: #1f2937;">
                                                <a href="mailto:{data.get('email', '')}" style="color: #3b82f6; text-decoration: none;">
                                                    {data.get('email', 'N/A')}
                                                </a>
                                            </td>
                                        </tr>
                                        <tr style="background-color: #f9fafb;">
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-weight: 600; color: #4b5563;">
                                                Organization:
                                            </td>
                                            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; color: #1f2937;">
                                                {data.get('organization', 'Not provided')}
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 12px; font-weight: 600; color: #4b5563;">
                                                Subject:
                                            </td>
                                            <td style="padding: 12px; color: #1f2937;">
                                                {data.get('subject', 'N/A')}
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <h3 style="color: #333; font-size: 16px; margin: 30px 0 15px 0;">Message:</h3>
                                    <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 20px; color: #1f2937; line-height: 1.6;">
                                        {data.get('message', 'No message provided')}
                                    </div>
                                    
                                    <div style="margin-top: 30px; padding: 15px; background: #eff6ff; border-left: 4px solid #3b82f6; border-radius: 4px;">
                                        <p style="margin: 0; color: #1e40af; font-size: 14px;">
                                            <strong>💡 Tip:</strong> Reply directly to this email to respond to {data.get('name', 'the sender')}.
                                        </p>
                                    </div>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f5f5f5; padding: 20px; text-align: center;">
                                    <p style="margin: 0; color: #666666; font-size: 12px;">
                                        This is an automated notification from the HumanEnerDIA contact form.
                                    </p>
                                </td>
                            </tr>
                            
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        # Create plain text version
        text_body = f"""
New Contact Form Submission - HumanEnerDIA

Contact Details:
================
Full Name: {data.get('name', 'N/A')}
Email: {data.get('email', 'N/A')}
Organization: {data.get('organization', 'Not provided')}
Subject: {data.get('subject', 'N/A')}

Message:
========
{data.get('message', 'No message provided')}

---
Reply directly to this email to respond to {data.get('name', 'the sender')}.
        """
        
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Contact form email sent to admins from {data.get('email')}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send contact form email: {e}")
        return False

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('AUTH_SERVICE_PORT', 5000))
    debug = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
    
    logger.info(f"Starting Auth Service on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
