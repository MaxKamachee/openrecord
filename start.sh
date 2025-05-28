#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting OpenRecord setup...${NC}"

# Kill processes on required ports
echo -e "\n${YELLOW}Killing processes on ports 3000, 8000, and Vite ports (5173-5176)...${NC}"

# Function to kill process on a given port
kill_port() {
    local port=$1
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if lsof -ti:${port} > /dev/null; then
            echo -e "${YELLOW}Killing process on port ${port}...${NC}"
            kill -9 $(lsof -ti:${port}) 2>/dev/null || true
        fi
    else
        # Linux
        if ss -tuln | grep -q ":${port}\b"; then
            echo -e "${YELLOW}Killing process on port ${port}...${NC}"
            fuser -k ${port}/tcp 2>/dev/null || true
        fi
    fi
}

# Kill processes on standard ports
kill_port 3000  # Frontend
kill_port 8000  # Backend

# Kill processes on Vite's default port range (5173-5176)
for port in {5173..5176}; do
    kill_port $port
done

echo -e "${GREEN}All required ports are now free.${NC}"

# Setup backend
echo -e "\n${YELLOW}Setting up backend...${NC}"
cd backend

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "\n${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv venv
    
    echo -e "\n${YELLOW}Activating virtual environment and installing requirements...${NC}"
    source venv/bin/activate
    pip install --upgrade pip
    
    # Then install other requirements
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Run database migrations if needed
# echo -e "\n${YELLOW}Running database migrations...${NC}
# python manage.py migrate

# Create a temporary log file for the backend
BACKEND_LOG="$(mktemp)"
echo -e "\n${YELLOW}Backend logs: $BACKEND_LOG${NC}"

# Start backend server and log to the temporary file
echo -e "\n${YELLOW}Starting backend server...${NC}" 
python main.py 2>&1 | tee "$BACKEND_LOG" &
BACKEND_PID=$!

# Function to show backend logs
show_backend_logs() {
    echo -e "\n${YELLOW}=== Backend Logs ===${NC}"
    tail -f "$BACKEND_LOG"
}

# Start showing logs in background
show_backend_logs &

# Go back to project root
cd ..

# Start frontend in a new terminal window
echo -e "\n${YELLOW}Starting frontend server...${NC}"
cd frontend
npm run dev &
FRONTEND_PID=$!

# Function to handle script termination
cleanup() {
    echo -e "\n${YELLOW}Shutting down servers...${NC}"
    # Kill all child processes including the log tail
    pkill -P $$
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    # Clean up the log file
    rm -f "$BACKEND_LOG"
    deactivate 2>/dev/null
    exit 0
}

# Set up trap to catch script termination
trap cleanup SIGINT SIGTERM

echo -e "\n${GREEN}OpenRecord is running!${NC}"
echo -e "${GREEN}Frontend: http://localhost:3000${NC}"
echo -e "${GREEN}Backend API: http://localhost:8000${NC}"
echo -e "\n${YELLOW}Press Ctrl+C to stop the servers${NC}"

# Keep script running
wait $BACKEND_PID $FRONTEND_PID
