#!/usr/bin/env python3
"""
WSGI entry point for Railway deployment
"""
import os
import sys

print("🔧 WSGI: Starting import process", flush=True)
print(f"🔧 WSGI: Current directory: {os.getcwd()}", flush=True)
print(f"🔧 WSGI: __file__: {__file__}", flush=True)

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
print(f"🔧 WSGI: Added to path: {project_root}", flush=True)

# Import the Flask app
try:
    print("🔧 WSGI: Attempting to import src.main", flush=True)
    from src.main import app
    print("🔧 WSGI: Successfully imported Flask app", flush=True)
except Exception as e:
    print(f"❌ WSGI: Failed to import src.main: {e}", flush=True)
    import traceback
    traceback.print_exc()
    raise

# Configure for production
app.config['ENV'] = 'production'
app.config['DEBUG'] = False

# WSGI application
application = app

if __name__ == "__main__":
    from app import *
