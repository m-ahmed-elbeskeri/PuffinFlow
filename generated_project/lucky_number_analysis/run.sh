#!/bin/bash
# FlowForge Project Runner

set -e  # Exit on error

echo "Setting up FlowForge project: lucky_number_analysis"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "Error: Python is not installed or not in PATH"
        exit 1
    else
        PYTHON_CMD="python"
    fi
else
    PYTHON_CMD="python3"
fi

echo "Using Python: $PYTHON_CMD"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment"
        echo "Make sure python3-venv is installed (apt-get install python3-venv on Ubuntu/Debian)"
        exit 1
    fi
fi

# Activate virtual environment
echo "Activating virtual environment..."
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -e .
if [ $? -ne 0 ]; then
    echo "Failed to install dependencies"
    exit 1
fi

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Note: .env file found. Environment variables will be loaded by the flow."
fi

# Run the flow
echo "Running the flow..."
$PYTHON_CMD -m workflow.run

echo "Flow execution completed!"
