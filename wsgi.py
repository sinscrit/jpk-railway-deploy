#!/usr/bin/env python3
"""
WSGI entry point for Railway deployment
"""
import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask app
from src.main import app

# Configure for production
app.config['ENV'] = 'production'
app.config['DEBUG'] = False

# WSGI application
application = app

if __name__ == "__main__":
    from app import *
