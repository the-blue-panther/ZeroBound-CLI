#!/bin/bash

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing requirements..."
pip install -r requirements.txt -q

echo "Playwright installation (if needed)..."
playwright install chromium --with-deps

echo "Starting ZeroBound CLI..."
python cli.py
