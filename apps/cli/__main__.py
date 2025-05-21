#!/usr/bin/env python3
"""FlowForge CLI entry point."""

import sys
import os

# Get the absolute path to the project root directory (parent of apps)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Add the project root to the Python path
sys.path.insert(0, project_root)

# Now import directly from the path-adjusted location
from apps.cli.flowforge import cli

if __name__ == "__main__":
    cli()