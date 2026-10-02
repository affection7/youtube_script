#!/bin/bash
# Linux launcher for the AI Agent GUI (equivalent of start_gui.bat on Windows).
cd "$(dirname "$0")"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

python3 app_gui.py
