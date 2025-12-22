#!/usr/bin/env python3
"""
Clean Python Cache Files
========================

Removes all __pycache__ directories and .pyc/.pyo files from the converter package.
Run this script if you experience stale behavior after copying the converter.

Usage:
    python clean_cache.py
"""

import os
import shutil
from pathlib import Path


def clean_cache():
    """Remove all Python cache files from the current directory tree."""
    script_dir = Path(__file__).parent.resolve()

    print("🧹 Cleaning Python cache files...")
    print(f"   Directory: {script_dir}")
    print()

    # Count removals
    pycache_count = 0
    pyc_count = 0

    # Remove __pycache__ directories
    for pycache_dir in script_dir.rglob("__pycache__"):
        if pycache_dir.is_dir():
            shutil.rmtree(pycache_dir)
            pycache_count += 1
            print(f"   Removed: {pycache_dir.relative_to(script_dir)}")

    # Remove .pyc and .pyo files
    for pattern in ["*.pyc", "*.pyo"]:
        for pyc_file in script_dir.rglob(pattern):
            pyc_file.unlink()
            pyc_count += 1
            print(f"   Removed: {pyc_file.relative_to(script_dir)}")

    print()
    print(f"✅ Cleanup complete!")
    print(f"   Removed {pycache_count} __pycache__ directories")
    print(f"   Removed {pyc_count} .pyc/.pyo files")
    print()
    print("You can now run the converter with fresh bytecode.")


if __name__ == "__main__":
    clean_cache()
