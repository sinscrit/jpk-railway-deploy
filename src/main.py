import os
import sys
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Allow HTTP for local OAuth development (disable in production)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Flask, send_from_directory, request, session
from flask_session import Session
from src.models.user import db, PageLoadLog
from src.routes.user import user_bp
from src.routes.flask_async_converter import flask_async_converter_bp
from src.routes.auth import auth_bp
from src.routes.admin import admin_bp

def validate_converter_on_startup():
    """Validate converter functionality during app startup"""
    print("🔍 Validating converter on startup...")
    
    try:
        # Import converter
        converter_path = os.path.join(os.path.dirname(__file__), '..', 'jpk2json')
        sys.path.insert(0, converter_path)
        from converter import main as converter_main, detect_environment, get_lib_file_path
        print("✅ Converter module imported successfully")
        
        # Check environment detection
        env = detect_environment()
        print(f"✅ Environment detected: {env}")
        
        # Check critical library files
        critical_files = [
            'type1000_components.json',
            'type600_components.json'
        ]
        
        for filename in critical_files:
            file_path = get_lib_file_path(filename)
            if not os.path.exists(file_path):
                raise Exception(f"Critical converter file missing: {file_path}")
        
        print(f"✅ {len(critical_files)} critical converter files validated")
        print("✅ Converter validation passed - app ready to start")
        
    except Exception as e:
        print(f"❌ Converter validation failed: {e}")
        print("❌ App startup aborted due to converter issues")
        raise SystemExit(1)

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Session configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'asdf#FGSgvasgf$5$WGT')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'jpk_converter_'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Initialize session
Session(app)

# Register blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(flask_async_converter_bp, url_prefix='/api/converter')
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)

# Database configuration - use /tmp for Railway (ephemeral), local path for development
if os.getenv('RAILWAY_ENVIRONMENT'):
    # Railway: use /tmp which is writable
    db_path = '/tmp/app.db'
else:
    # Local development: use local database folder
    db_dir = os.path.join(os.path.dirname(__file__), 'database')
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, 'app.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()
    validate_converter_on_startup()  # Add this line

def get_client_ip():
    """Get client IP address, handling proxies"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr

def log_page_load(page_url):
    """Log page load to database"""
    try:
        client_ip = get_client_ip()
        user_info = session.get('user', {})
        
        page_load = PageLoadLog(
            client_ip=client_ip,
            user_email=user_info.get('email'),
            user_name=user_info.get('name'),
            page_url=page_url,
            user_agent=request.headers.get('User-Agent'),
            referrer=request.headers.get('Referer')
        )
        db.session.add(page_load)
        db.session.commit()
    except Exception as e:
        print(f"Error logging page load: {e}")

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    # Log page load
    full_url = request.url
    log_page_load(full_url)
    
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404


if __name__ == '__main__':
    print("🚀 Starting Asynchronous JPK to JSON Converter Service...")
    print("📊 Thread pool executor ready for concurrent processing")
    print("✅ Service configured for high-performance async operations")
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
