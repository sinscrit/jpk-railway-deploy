#!/usr/bin/env python3
"""
Railway deployment entry point for Asynchronous JPK to JSON Converter
"""
import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask app
from src.main import app

# Configure for Railway deployment
app.config['ENV'] = 'production'
app.config['DEBUG'] = False

# Railway-specific configuration
PORT = int(os.environ.get('PORT', 5000))

if __name__ == "__main__":
    print("🚀 Starting JPK to JSON Converter on Railway...")
    print(f"📊 Running on port {PORT}")
    print("✅ Asynchronous processing enabled")
    
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=False,
        threaded=True
    )
