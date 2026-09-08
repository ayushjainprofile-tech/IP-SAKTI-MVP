#!/bin/bash
echo "Starting IP-SAKTI MVP..."

# Cleanup function to kill background processes when you press Ctrl+C
cleanup() {
    echo -e "\nStopping backend and frontend servers..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}

# Catch Ctrl+C and run cleanup
trap cleanup SIGINT SIGTERM

# 1. Start Backend
echo "Starting Backend..."
cd backend
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001 &
BACKEND_PID=$!

# 2. Start Frontend
echo "Starting Frontend..."
cd ../frontend
npm install
# Fix broken git permissions by forcing rebuild of node_modules if needed
rm -rf node_modules/.vite node_modules/.bin
npm install
npm run dev &
FRONTEND_PID=$!

echo "Both servers are running! (Press Ctrl+C to stop both)"
# Wait for background processes to keep the script running
wait $BACKEND_PID $FRONTEND_PID
