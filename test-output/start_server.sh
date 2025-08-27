#!/bin/bash

# Slack Events API Mock Server Startup Script

echo "🚀 Starting Slack Events API Mock Server"
echo "========================================"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is required but not installed."
    exit 1
fi

# Check if pip is available
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is required but not installed."
    exit 1
fi

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "📦 Installing dependencies..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies"
        exit 1
    fi
fi

# Set environment variables for development
export DEBUG=true
export POPULATE_SAMPLE_DATA=true
export HOST=0.0.0.0
export PORT=5000

echo "🔧 Configuration:"
echo "   Host: $HOST"
echo "   Port: $PORT"
echo "   Debug: $DEBUG"
echo "   Sample Data: $POPULATE_SAMPLE_DATA"
echo ""

# Start the server
echo "🌟 Starting server..."
python3 server/run.py