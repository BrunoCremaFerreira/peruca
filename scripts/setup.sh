#!/bin/bash

# Virtual Environment
VENV_DIR="venv"

# Dependency install
API_REQUIREMENTS_FILE="../src/api/requirements.txt"

_create_venv()
{
    # Check if the virtual environment exist
    if [ ! -d "$VENV_DIR" ]; then
        echo "Creating Virtual Environment..."
        python3 -m venv $VENV_DIR
    else
        echo "Virtual Environment already exist."
    fi

    # Activate Virtual Environment
    source $VENV_DIR/bin/activate
}

_install_dependency()
{
    if [ -f "$1" ]; then
        echo "Installing Dependencies..."
        pip install -r "$1"
    else
        echo "The file "$1" was not found!"
        exit 1
    fi
}

_main()
{
    _create_venv
    _install_dependency "$API_REQUIREMENTS_FILE"
    echo "Virtual Environment configured!"
}

_main