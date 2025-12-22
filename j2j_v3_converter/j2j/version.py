"""
Version information for J2J Converter.

This module provides version tracking for the standalone converter.
"""

from datetime import datetime

# Semantic versioning: MAJOR.MINOR.PATCH
VERSION_MAJOR = 1
VERSION_MINOR = 0
VERSION_PATCH = 0

# Version string
VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"

# Build identifier (date-based)
BUILD_DATE = "2024-12-22"

# Converter identifier
CONVERTER_ID = "j2j-standalone"


def get_version_info() -> dict:
    """
    Get complete version information for embedding in output JSON.

    Returns:
        Dictionary with version metadata
    """
    return {
        "converter": CONVERTER_ID,
        "version": VERSION,
        "buildDate": BUILD_DATE,
        "generatedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }


def get_version_string() -> str:
    """
    Get formatted version string for display.

    Returns:
        Formatted version string
    """
    return f"{CONVERTER_ID} v{VERSION} ({BUILD_DATE})"
