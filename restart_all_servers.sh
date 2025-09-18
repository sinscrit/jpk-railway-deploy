#!/bin/bash

# restart_all_servers.sh
# Purpose: Kill any running Flask servers and restart them cleanly
# Used for: Task 001-4.2 - Testing startup validation functionality

echo "🔄 Restarting all servers..."

# Kill any existing Flask processes
echo "🛑 Stopping existing Flask servers..."
pkill -f "flask run" 2>/dev/null || echo "   No Flask processes found"
pkill -f "python -m flask" 2>/dev/null || echo "   No Python Flask processes found"

# Wait a moment for processes to terminate
sleep 2

# Start Flask server in background
echo "🚀 Starting Flask server on port 8000..."
python -m flask run --port 8000 &
FLASK_PID=$!

# Wait for server to start
echo "⏳ Waiting for server to initialize..."
sleep 3

# Check if server is running
if ps -p $FLASK_PID > /dev/null; then
    echo "✅ Flask server started successfully (PID: $FLASK_PID)"
    echo "🌐 Server available at: http://localhost:8000"
    echo "📊 Health check: http://localhost:8000/api/converter/health"
    echo ""
    echo "To stop the server, run: kill $FLASK_PID"
    echo "Or use: pkill -f flask"
else
    echo "❌ Flask server failed to start"
    exit 1
fi
