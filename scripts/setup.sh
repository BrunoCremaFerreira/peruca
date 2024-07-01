#!/bin/bash

# Virtual Environment
VENV_DIR="venv"

# Check if the virtual environment exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Virtual Environment..."
    python3 -m venv $VENV_DIR
else
    echo "Virtual Environment already exist."
fi

# Activate Virtual Environment
source $VENV_DIR/bin/activate

# Dependency install
if [ -f "requirements.txt" ]; then
    echo "Installing Dependencies..."
    pip install -r requirements.txt
else
    echo "The file requirements.txt was not found!"
    exit 1
fi

echo "Virtual Environment configured!"
