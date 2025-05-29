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
