import os
import sys
import asyncio
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory
from src.models.user import db
from src.routes.user import user_bp
from src.routes.async_converter import async_converter_bp

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Register blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(async_converter_bp, url_prefix='/api/converter')

# Database configuration (optional for this service)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
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

@app.before_first_request
def startup():
    """Initialize the application on startup"""
    print("🚀 Asynchronous JPK to JSON Converter Service starting...")
    print("📊 Thread pool initialized for concurrent conversions")
    print("✅ Service ready to handle multiple simultaneous conversions")

if __name__ == '__main__':
    print("🚀 Starting Asynchronous JPK to JSON Converter Service...")
    print("📊 Thread pool executor ready for concurrent processing")
    print("✅ Service configured for high-performance async operations")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
