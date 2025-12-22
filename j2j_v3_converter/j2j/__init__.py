"""
J2J v327 - Modular JPK to JSON Converter
========================================

This is the modular version of the JPK to JSON converter, refactored from the
monolithic j2j_v325.py into a maintainable, testable architecture.

Key improvements in v327:
- Modular design with single-responsibility components
- Custom exception hierarchy for better error handling
- Configuration management with validation
- Template system with factory patterns
- Comprehensive error handling and logging
"""

__version__ = "3.2.7"

# Main components
from .config.loader import ConfigLoader
from .config.models import J2JConfig
from .converters.jpk_to_json import JPKConverter

__all__ = [
    "__version__",
    "ConfigLoader",
    "J2JConfig",
    "JPKConverter",
]
