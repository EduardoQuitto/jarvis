#!/usr/bin/env python3
"""Convenience runner script for JARVIS Node."""

import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.cli import main

if __name__ == "__main__":
    main()
