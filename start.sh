#!/bin/bash
# CB Monitor - Web Server Start Script
# Starts web server only - monitoring controlled via web interface

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║          📡 CB MONITOR - STARTING WEB SERVER                 ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found"
    exit 1
fi

echo "✅ Python 3: $(python3 --version)"

echo ""
echo "🚀 Starting Web Server..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo ""
    echo "⏹️  Stopping CB Monitor..."
    echo "   Killing background processes..."

    # Kill web server
    if [ ! -z "$SERVER_PID" ]; then
        kill -- -$SERVER_PID 2>/dev/null
    fi

    # Also kill monitoring if running
    pkill -f "cb_monitor.py monitor" 2>/dev/null
    pkill -f "api_server.py" 2>/dev/null

    # Wait a moment for processes to terminate
    sleep 1

    echo "✅ All processes stopped"
    exit 0
}

# Trap Ctrl+C and cleanup
trap cleanup INT TERM

# Start web server
echo "🌐 Starting web server..."
{
    python3 api_server.py 8888 2>&1 | while IFS= read -r line; do
        echo "[SERVER]  $line"
    done
} &
SERVER_PID=$!

# Wait a moment for server to start
sleep 2

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ CB Monitor is running!"
echo ""
echo "   📊 Dashboard:  http://localhost:8888/dashboard.html"
echo "   🗺️  Heatmap:    http://localhost:8888/heatmap.html"
echo "   🏠 Main Menu:  http://localhost:8888/index.html"
echo ""
echo "   Press Ctrl+C to stop monitoring and save session"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Live logs:"
echo ""

# Wait for both processes
wait
