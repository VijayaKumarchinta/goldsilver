#!/bin/bash
set -e

# Install Python dependencies
pip install -r requirements.txt

# Build frontend if Node.js is available
if command -v npm &> /dev/null; then
    cd ../frontend
    npm ci
    npm run build
    cd ../backend
else
    echo "WARNING: npm not found, frontend will not be built"
    echo "Frontend dist must be committed to the repository for production use"
fi
