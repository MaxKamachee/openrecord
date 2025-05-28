#!/bin/bash
# Robust startup script for OpenRecord
# Kills processes on backend/frontend ports, sets up and starts backend and frontend
# Logs output to logs/startup.log

LOGFILE="logs/startup.log"
BACKEND_DIR="backend"
FRONTEND_DIR="frontend"
BACKEND_PORT=8000
FRONTEND_PORT=3000

mkdir -p logs

echo "[Startup] Killing processes on ports $BACKEND_PORT and $FRONTEND_PORT..." | tee $LOGFILE
for PORT in $BACKEND_PORT $FRONTEND_PORT; do
  PID=$(lsof -ti tcp:$PORT)
  if [ ! -z "$PID" ]; then
    kill -9 $PID && echo "[Startup] Killed process $PID on port $PORT" | tee -a $LOGFILE
  fi
done

echo "[Startup] Setting up backend..." | tee -a $LOGFILE
cd $BACKEND_DIR
pip install -r requirements.txt >> ../$LOGFILE 2>&1
nohup python3 main.py >> ../$LOGFILE 2>&1 &
cd ..

echo "[Startup] Setting up frontend..." | tee -a $LOGFILE
if [ -d "$FRONTEND_DIR" ]; then
  cd $FRONTEND_DIR
  if [ -f package.json ]; then
    if command -v npm > /dev/null; then
      npm install >> ../$LOGFILE 2>&1
      nohup npm start >> ../$LOGFILE 2>&1 &
    elif command -v yarn > /dev/null; then
      yarn install >> ../$LOGFILE 2>&1
      nohup yarn start >> ../$LOGFILE 2>&1 &
    else
      echo "[Startup] Neither npm nor yarn found. Skipping frontend start." | tee -a ../$LOGFILE
    fi
  else
    echo "[Startup] No package.json found in frontend. Skipping frontend start." | tee -a ../$LOGFILE
  fi
  cd ..
else
  echo "[Startup] Frontend directory not found. Skipping frontend setup." | tee -a $LOGFILE
fi

echo "[Startup] Startup script complete. Check $LOGFILE for details."
