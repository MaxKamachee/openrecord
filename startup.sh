#!/bin/bash
# Enhanced startup script for NJ OPRA Redaction Service
# Handles dependencies, port conflicts, and provides better logging

set -e  # Exit on any error

LOGFILE="logs/startup.log"
BACKEND_DIR="backend"
FRONTEND_DIR="frontend"
BACKEND_PORT=8000
FRONTEND_PORT=3000

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_color() {
    echo -e "${1}${2}${NC}"
}

# Create logs directory
mkdir -p logs

echo_color $BLUE "🚀 Starting NJ OPRA Redaction Service..."
echo "$(date): Starting NJ OPRA Redaction Service" > $LOGFILE

# Function to kill processes on ports
kill_port() {
    local port=$1
    local pids=$(lsof -ti tcp:$port 2>/dev/null || true)
    if [ ! -z "$pids" ]; then
        echo_color $YELLOW "⚡ Killing processes on port $port..."
        echo $pids | xargs kill -9
        echo "$(date): Killed processes on port $port: $pids" >> $LOGFILE
        sleep 2
    fi
}

# Kill existing processes
kill_port $BACKEND_PORT
kill_port $FRONTEND_PORT

# Check for API key
if [ ! -f "$BACKEND_DIR/.env" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo_color $RED "❌ ANTHROPIC_API_KEY not found!"
    echo_color $YELLOW "Create $BACKEND_DIR/.env with: ANTHROPIC_API_KEY=your_key_here"
    echo_color $YELLOW "Or export ANTHROPIC_API_KEY=your_key_here"
    exit 1
fi

# Setup backend
echo_color $BLUE "🔧 Setting up backend..."
cd $BACKEND_DIR

# Check Python version
if command -v python3 > /dev/null; then
    python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1-2)
    echo_color $GREEN "✅ Python version: $python_version"
else
    echo_color $RED "❌ Python3 not found. Please install Python 3.8+"
    exit 1
fi

# Install Python dependencies
if [ -f "requirements.txt" ]; then
    echo_color $BLUE "📦 Installing Python dependencies..."
    pip install -r requirements.txt >> ../$LOGFILE 2>&1
    if [ $? -eq 0 ]; then
        echo_color $GREEN "✅ Backend dependencies installed"
    else
        echo_color $RED "❌ Failed to install backend dependencies"
        exit 1
    fi
else
    echo_color $RED "❌ requirements.txt not found in backend directory"
    exit 1
fi

# Start backend
echo_color $BLUE "🚀 Starting backend server..."
nohup python3 main.py >> ../$LOGFILE 2>&1 &
BACKEND_PID=$!
echo "$(date): Started backend with PID $BACKEND_PID" >> ../$LOGFILE

cd ..

# Setup frontend
echo_color $BLUE "🔧 Setting up frontend..."
if [ -d "$FRONTEND_DIR" ]; then
    cd $FRONTEND_DIR
    
    # Check Node.js version
    if command -v node > /dev/null; then
        node_version=$(node --version)
        echo_color $GREEN "✅ Node.js version: $node_version"
    else
        echo_color $RED "❌ Node.js not found. Please install Node.js 16+"
        exit 1
    fi
    
    # Install dependencies
    if [ -f "package.json" ]; then
        if command -v npm > /dev/null; then
            echo_color $BLUE "📦 Installing frontend dependencies..."
            npm install >> ../$LOGFILE 2>&1
            if [ $? -eq 0 ]; then
                echo_color $GREEN "✅ Frontend dependencies installed"
            else
                echo_color $RED "❌ Failed to install frontend dependencies"
                exit 1
            fi
            
            echo_color $BLUE "🚀 Starting frontend server..."
            nohup npm start >> ../$LOGFILE 2>&1 &
            FRONTEND_PID=$!
            echo "$(date): Started frontend with PID $FRONTEND_PID" >> ../$LOGFILE
        else
            echo_color $RED "❌ npm not found. Please install Node.js with npm"
            exit 1
        fi
    else
        echo_color $RED "❌ package.json not found in frontend directory"
        exit 1
    fi
    cd ..
else
    echo_color $RED "❌ Frontend directory not found"
    exit 1
fi

# Wait for services to start
echo_color $BLUE "⏳ Waiting for services to start..."
sleep 15

# Test backend
echo_color $BLUE "🧪 Testing backend..."
for i in {1..10}; do
    if curl -f http://localhost:$BACKEND_PORT/test > /dev/null 2>&1; then
        echo_color $GREEN "✅ Backend is running on http://localhost:$BACKEND_PORT"
        BACKEND_OK=true
        break
    else
        echo_color $YELLOW "⏳ Backend starting... (attempt $i/10)"
        sleep 3
    fi
done

if [ "$BACKEND_OK" != "true" ]; then
    echo_color $RED "❌ Backend failed to start. Check logs/startup.log"
    exit 1
fi

# Test frontend (simple check for port response)
echo_color $BLUE "🧪 Testing frontend..."
for i in {1..5}; do
    if curl -f http://localhost:$FRONTEND_PORT > /dev/null 2>&1; then
        echo_color $GREEN "✅ Frontend is running on http://localhost:$FRONTEND_PORT"
        FRONTEND_OK=true
        break
    else
        echo_color $YELLOW "⏳ Frontend starting... (attempt $i/5)"
        sleep 5
    fi
done

if [ "$FRONTEND_OK" != "true" ]; then
    echo_color $YELLOW "⚠️ Frontend might still be starting. Check http://localhost:$FRONTEND_PORT in a moment"
fi

echo ""
echo_color $GREEN "🎉 Setup Complete!"
echo ""
echo_color $BLUE "📱 Frontend: http://localhost:$FRONTEND_PORT"
echo_color $BLUE "🔧 Backend API: http://localhost:$BACKEND_PORT"
echo_color $BLUE "📚 API Docs: http://localhost:$BACKEND_PORT/docs"
echo_color $BLUE "🧪 Test Backend: http://localhost:$BACKEND_PORT/test"
echo_color $BLUE "📝 Logs: $LOGFILE"
echo ""
echo_color $YELLOW "💡 Tips:"
echo_color $YELLOW "  • Upload PDF files to test the redaction system"
echo_color $YELLOW "  • Check API documentation for advanced usage"
echo_color $YELLOW "  • Monitor $LOGFILE for troubleshooting"
echo_color $YELLOW "  • Use Ctrl+C to stop services"
echo ""

# Save PIDs for cleanup
echo "BACKEND_PID=$BACKEND_PID" > .pids
echo "FRONTEND_PID=$FRONTEND_PID" >> .pids
echo "$(date): PIDs saved - Backend: $BACKEND_PID, Frontend: $FRONTEND_PID" >> $LOGFILE

# Create stop script
cat > stop.sh << 'EOF'
#!/bin/bash
echo "Stopping NJ OPRA Redaction Service..."
if [ -f .pids ]; then
    source .pids
    [ ! -z "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null && echo "Stopped backend (PID: $BACKEND_PID)"
    [ ! -z "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null && echo "Stopped frontend (PID: $FRONTEND_PID)"
    rm .pids
fi

# Kill by port as backup
for port in 8000 3000; do
    pids=$(lsof -ti tcp:$port 2>/dev/null || true)
    [ ! -z "$pids" ] && echo $pids | xargs kill -9 && echo "Killed remaining processes on port $port"
done

echo "Services stopped."
EOF
chmod +x stop.sh

echo_color $GREEN "✨ Ready to process OPRA redactions!"
echo_color $BLUE "💡 Run './stop.sh' to stop all services"