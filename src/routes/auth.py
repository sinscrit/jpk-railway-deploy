import os
import json
import secrets
from flask import Blueprint, request, redirect, session, url_for, jsonify, current_app
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
import requests
from src.models.user import db, LoginLog

# Allow HTTP for local development (disable in production)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

auth_bp = Blueprint('auth', __name__)

def get_client_ip():
    """Get client IP address, handling proxies"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

def log_login_attempt(user_email, user_name, success=True, error_message=None):
    """Log login attempt to database"""
    try:
        client_ip = get_client_ip()
        
        login_log = LoginLog(
            client_ip=client_ip,
            user_email=user_email,
            user_name=user_name,
            login_method='google_oauth',
            success=success,
            error_message=error_message,
            user_agent=request.headers.get('User-Agent')
        )
        db.session.add(login_log)
        db.session.commit()
    except Exception as e:
        print(f"Error logging login attempt: {e}")

# OAuth configuration
OAUTH_CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'oauth_config.json')

def load_oauth_config():
    """Load OAuth configuration from file or environment variables"""
    try:
        # Try to load from environment variables first (for Railway deployment)
        if os.getenv('GOOGLE_CLIENT_ID'):
            return {
                'web': {
                    'client_id': os.getenv('GOOGLE_CLIENT_ID'),
                    'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
                    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
                    'redirect_uris': [
                        'http://localhost:8000',
                        'https://j2j.iointegrated.com',
                        'https://jbjpk2json-production.up.railway.app'
                    ]
                }
            }
        
        # Fallback to config file
        if os.path.exists(OAUTH_CONFIG_FILE):
            with open(OAUTH_CONFIG_FILE, 'r') as f:
                return json.load(f)
        
        raise FileNotFoundError("OAuth config not found")
        
    except Exception as e:
        print(f"Error loading OAuth config: {e}")
        return None

def get_redirect_uri():
    """Get the appropriate redirect URI based on the current request"""
    if request.is_secure or 'localhost' not in request.host:
        scheme = 'https'
    else:
        scheme = 'http'
    
    return f"{scheme}://{request.host}/auth/callback"

@auth_bp.route('/login')
def login():
    """Initiate Google OAuth login"""
    try:
        oauth_config = load_oauth_config()
        if not oauth_config:
            return jsonify({'error': 'OAuth configuration not available'}), 500
        
        # Create flow instance with full scope URLs
        flow = Flow.from_client_config(
            oauth_config,
            scopes=[
                'openid',
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/userinfo.profile'
            ]
        )
        
        # Set redirect URI dynamically
        flow.redirect_uri = get_redirect_uri()
        
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        
        # Get authorization URL
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state
        )
        
        return redirect(authorization_url)
        
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

@auth_bp.route('/auth/callback')
def auth_callback():
    """Handle OAuth callback"""
    try:
        # Verify state parameter
        if request.args.get('state') != session.get('oauth_state'):
            return jsonify({'error': 'Invalid state parameter'}), 400
        
        oauth_config = load_oauth_config()
        if not oauth_config:
            return jsonify({'error': 'OAuth configuration not available'}), 500
        
        # Create flow instance with full scope URLs
        flow = Flow.from_client_config(
            oauth_config,
            scopes=[
                'openid',
                'https://www.googleapis.com/auth/userinfo.email',
                'https://www.googleapis.com/auth/userinfo.profile'
            ]
        )
        
        flow.redirect_uri = get_redirect_uri()
        
        # Exchange authorization code for tokens
        flow.fetch_token(authorization_response=request.url)
        
        # Get user info from ID token with clock skew tolerance
        credentials = flow.credentials
        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            google_requests.Request(),
            oauth_config['web']['client_id'],
            clock_skew_in_seconds=300  # Allow 5 minutes clock skew
        )
        
        # Store user info in session
        user_info = {
            'id': id_info['sub'],
            'email': id_info['email'],
            'name': id_info.get('name', ''),
            'picture': id_info.get('picture', ''),
            'verified_email': id_info.get('email_verified', False)
        }
        session['user'] = user_info
        
        # Log successful login
        log_login_attempt(
            user_email=user_info['email'],
            user_name=user_info['name'],
            success=True
        )
        
        # Clear OAuth state
        session.pop('oauth_state', None)
        
        # Redirect to home page
        return redirect('/')
        
    except Exception as e:
        print(f"Auth callback error: {e}")
        error_msg = str(e)
        
        # Log failed login attempt (if we have user info from the error)
        try:
            # Try to extract email from error context if available
            user_email = request.args.get('email', 'unknown')
            log_login_attempt(
                user_email=user_email,
                user_name='unknown',
                success=False,
                error_message=error_msg
            )
        except:
            pass  # Don't fail the error response if logging fails
        
        # Provide more specific error messages
        if 'insecure_transport' in error_msg:
            return jsonify({
                'error': 'OAuth configuration error',
                'message': 'HTTPS required for OAuth in production. Please update Google Cloud Console redirect URIs.'
            }), 500
        elif 'Token used too early' in error_msg or 'clock' in error_msg.lower():
            return jsonify({
                'error': 'Clock synchronization error',
                'message': 'Please check your system clock and try again.'
            }), 500
        elif 'redirect_uri_mismatch' in error_msg:
            return jsonify({
                'error': 'OAuth configuration error',
                'message': 'Redirect URI mismatch. Please update Google Cloud Console settings.'
            }), 500
        else:
            return jsonify({
                'error': 'Authentication failed',
                'message': 'Please try logging in again.'
            }), 500

@auth_bp.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect('/')

@auth_bp.route('/user')
def get_user():
    """Get current user info"""
    user = session.get('user')
    if user:
        return jsonify({
            'authenticated': True,
            'user': user
        })
    else:
        return jsonify({
            'authenticated': False,
            'user': None
        })

@auth_bp.route('/auth/status')
def auth_status():
    """Check authentication status including approval"""
    from src.routes.admin import is_approved_user, is_admin

    user = session.get('user')
    if not user:
        return jsonify({
            'authenticated': False,
            'approved': False,
            'user': None
        })

    email = user.get('email', '')
    return jsonify({
        'authenticated': True,
        'approved': is_approved_user(email),
        'is_admin': is_admin(),
        'user': user
    })

def require_auth(f):
    """Decorator to require authentication"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function
