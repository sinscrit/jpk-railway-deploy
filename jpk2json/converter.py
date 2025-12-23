#!/usr/bin/env python3
"""
JPK to JSON Converter - Wrapper for v327 (j2j_v3_converter)

This wrapper provides backwards compatibility with the Flask application
by exposing the same `main(args)` interface as the previous converter.

The actual conversion is performed by j2j_v3_converter with the modular architecture.
"""

import os
import sys

# Add the j2j_v3_converter directory to path for imports
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_current_dir)
_j2j_v3_path = os.path.join(_project_root, 'j2j_v3_converter')

if _j2j_v3_path not in sys.path:
    sys.path.insert(0, _j2j_v3_path)

# Import the new converter
from j2j import JPKConverter, ConfigLoader
from j2j.utils import ConfigurationError, JPKParsingError


def detect_environment():
    """Detect if running in Railway (production) or local environment."""
    if os.environ.get('RAILWAY_ENVIRONMENT'):
        return 'production'
    return 'development'


def get_lib_file_path(filename: str) -> str:
    """Get the full path to a library file."""
    return os.path.join(_current_dir, 'lib', filename)


def main(args=None) -> int:
    """
    Main entry point for the converter.

    Provides backwards compatibility with the Flask application.

    Args:
        args: Object with jpk_path, output_path, and optional verbose attributes
              Can also be a list of command line arguments

    Returns:
        0 on success, 1 on failure
    """
    try:
        # Handle different argument formats
        if args is None:
            print("Error: No arguments provided")
            return 1

        # If args is a list (command line style), parse it
        if isinstance(args, list):
            if len(args) < 1:
                print("Usage: converter.py <input.jpk> [output.json]")
                return 1
            jpk_path = args[0]
            output_path = args[1] if len(args) > 1 else None
        else:
            # Assume args is an object with attributes
            jpk_path = getattr(args, 'jpk_path', None)
            output_path = getattr(args, 'output_path', None)

        if not jpk_path:
            print("Error: No JPK path provided")
            return 1

        if not os.path.exists(jpk_path):
            print(f"Error: JPK file not found: {jpk_path}")
            return 1

        # Make paths absolute before we change directories
        jpk_path = os.path.abspath(jpk_path)
        if output_path:
            output_path = os.path.abspath(output_path)

        # Determine config path - look in j2j_v3_converter directory
        config_path = os.path.join(_j2j_v3_path, 'j2j_config.json')

        if not os.path.exists(config_path):
            print(f"Error: Config file not found: {config_path}")
            return 1

        print(f"Using converter v327 (j2j_v3_converter)")
        print(f"  JPK input: {jpk_path}")
        print(f"  Output: {output_path or 'auto-generated'}")
        print(f"  Config: {config_path}")

        # Change to j2j_v3_converter directory so relative paths in config work
        original_cwd = os.getcwd()
        os.chdir(_j2j_v3_path)
        print(f"  Working dir: {os.getcwd()}")

        try:
            # Load config to get trace_log settings
            config_loader = ConfigLoader()
            config = config_loader.load(config_path)

            # Create converter with trace logging config
            converter = JPKConverter(trace_log_config=config.trace_log)

            # Perform conversion
            result_path = converter.convert(
                jpk_path=jpk_path,
                output_path=output_path,
                config_path=config_path
            )

            print(f"Conversion completed successfully!")
            print(f"  Output: {result_path}")
            return 0

        finally:
            # Restore original working directory
            os.chdir(original_cwd)

    except FileNotFoundError as e:
        print(f"File not found error: {e}")
        return 1
    except ConfigurationError as e:
        print(f"Configuration error: {e}")
        return 1
    except JPKParsingError as e:
        print(f"JPK parsing error: {e}")
        return 1
    except Exception as e:
        print(f"Conversion error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
