"""
Custom exception hierarchy for J2J v327.

This module provides structured exception handling with proper context
for different types of errors that can occur during JPK to JSON conversion.
"""


class J2JError(Exception):
    """
    Base exception class for all J2J v327 errors.

    All custom exceptions in the J2J system inherit from this base class
    to provide consistent error handling and identification.
    """
    pass


class ConfigurationError(J2JError):
    """
    Exception raised for configuration-related errors.

    This includes:
    - Missing configuration files
    - Invalid JSON in configuration files
    - Missing required configuration sections
    - Invalid baseline file paths
    - Template directory validation failures
    """
    pass


class JPKParsingError(J2JError):
    """
    Exception raised for JPK file parsing errors.

    This includes:
    - Invalid or corrupted JPK files
    - Missing expected components in JPK
    - XML parsing errors within JPK files
    - Header extraction failures
    """
    pass


class TemplateError(J2JError):
    """
    Exception raised for template-related errors.

    This includes:
    - Missing template files
    - Invalid template structure
    - Template loading failures
    - Template validation errors
    """
    pass


class ValidationError(J2JError):
    """
    Exception raised for validation failures.

    This includes:
    - Data structure validation failures
    - Component validation errors
    - Schema validation failures
    - Output validation errors
    """
    pass
