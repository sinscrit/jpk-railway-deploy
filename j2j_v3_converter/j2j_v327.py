#!/usr/bin/env python3
"""
JPK to JSON Converter - Version 327: Modular Architecture
=========================================================

This is the modular entry point for the JPK to JSON converter, utilizing
the refactored architecture from j2j v327 package.

Key improvements in v327:
- Modular design with single-responsibility components
- Custom exception hierarchy for better error handling
- Configuration management with validation
- Template system with factory patterns
- Comprehensive error handling and logging
- Enhanced maintainability and testability

Usage:
    python j2j_v327.py <jpk_file> <output_file> [config_file]
    python j2j_v327.py --analyze <jpk_file>

Arguments:
    jpk_file: Path to JPK file to convert
    output_file: Path for output JSON file
    config_file: Path to configuration file (default: j2j_config.json)

Examples:
    # Basic conversion
    python j2j_v327.py original_source_vb.jpk output.json

    # Convert with custom config
    python j2j_v327.py my_project.jpk output.json my_config.json

    # Analyze JPK without conversion
    python j2j_v327.py --analyze my_project.jpk
"""

import sys
import argparse
from pathlib import Path

# Import from modular architecture
from j2j import JPKConverter, ConfigLoader, J2JConfig
from j2j.utils import ConfigurationError, JPKParsingError
from j2j.config.models import TraceLogConfig


def create_argument_parser():
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="JPK to JSON Converter v327 - Modular Architecture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s original_source_vb.jpk output.json         # Basic conversion
  %(prog)s my_project.jpk output.json my_config.json  # Custom config
  %(prog)s --analyze my_project.jpk                   # Analyze JPK only
        """
    )

    parser.add_argument(
        'jpk_file',
        help='Path to JPK file to convert or analyze'
    )

    parser.add_argument(
        'config_file',
        nargs='?',
        default='j2j_config.json',
        help='Path to configuration file (default: j2j_config.json)'
    )

    parser.add_argument(
        'output_file',
        nargs='?',
        default=None,
        help='Path for output JSON file (not needed with --analyze)'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='J2J v327 - Modular Architecture'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    parser.add_argument(
        '-a', '--analyze',
        action='store_true',
        help='Analyze JPK file and show metadata without conversion'
    )

    parser.add_argument(
        '--json',
        action='store_true',
        help='Output analysis results as JSON (use with --analyze)'
    )

    return parser


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def print_analysis(analysis: dict) -> None:
    """Print JPK analysis in a formatted way."""
    print()
    print("=" * 60)
    print("  JPK FILE ANALYSIS")
    print("=" * 60)
    print()

    # File info
    print(f"  Filename:      {analysis['filename']}")
    print(f"  File Size:     {format_file_size(analysis['file_size'])}")
    print(f"  Project Name:  {analysis['project_name'] or '(not found)'}")
    print()

    # Component counts
    counts = analysis['counts']
    print("  COMPONENT COUNTS:")
    print(f"    Operations:        {counts['operations']}")
    print(f"    Transformations:   {counts['transformations']}")
    print(f"    Scripts:           {counts['scripts']}")
    print(f"    Project Variables: {counts['project_variables']}")
    print(f"    Global Variables:  {counts['global_variables']}")
    print(f"    Endpoints:         {counts['endpoints']}")
    print(f"    XSD Files:         {counts['xsd_files']}")
    print()

    # Total
    total = sum(counts.values())
    print(f"    TOTAL COMPONENTS:  {total}")
    print()

    # Operations list
    if analysis['operations']:
        print("  OPERATIONS:")
        for op in analysis['operations']:
            print(f"    - {op['name']}")
        print()

    # Transformations list
    if analysis['transformations']:
        print("  TRANSFORMATIONS:")
        for tf in analysis['transformations']:
            print(f"    - {tf['name']}")
        print()

    print("=" * 60)


def validate_input_files(jpk_file: str, config_file: str) -> None:
    """
    Validate that input files exist.

    Args:
        jpk_file: Path to JPK file
        config_file: Path to configuration file

    Raises:
        FileNotFoundError: If required files don't exist
    """
    jpk_path = Path(jpk_file)
    if not jpk_path.exists():
        raise FileNotFoundError(f"JPK file not found: {jpk_file}")

    config_path = Path(config_file)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")


def main():
    """Main entry point for j2j_v327 converter."""
    import json as json_module

    # Parse command line arguments
    parser = create_argument_parser()
    args = parser.parse_args()

    try:
        # Validate JPK file exists
        jpk_path = Path(args.jpk_file)
        if not jpk_path.exists():
            raise FileNotFoundError(f"JPK file not found: {args.jpk_file}")

        # Handle analyze mode
        if args.analyze:
            converter = JPKConverter()
            analysis = converter.analyze(args.jpk_file)

            if args.json:
                # Output as JSON
                print(json_module.dumps(analysis, indent=2))
            else:
                # Output formatted text
                print_analysis(analysis)

            return 0

        # For conversion mode, output_file is required
        if not args.output_file:
            print("❌ Error: output_file is required for conversion")
            print("   Use --analyze flag to analyze JPK without conversion")
            parser.print_usage()
            return 1

        # Validate config file for conversion
        validate_input_files(args.jpk_file, args.config_file)

        if args.verbose:
            print(f"🔧 J2J v327 - Modular Architecture")
            print(f"   JPK File: {args.jpk_file}")
            print(f"   Output File: {args.output_file}")
            print(f"   Config File: {args.config_file}")
            print()

        # Pre-load config to get trace_log settings
        config_loader = ConfigLoader()
        config = config_loader.load(args.config_file)

        # Create converter and perform conversion with trace logging config
        converter = JPKConverter(trace_log_config=config.trace_log)

        output_path = converter.convert(
            jpk_path=args.jpk_file,
            output_path=args.output_file,
            config_path=args.config_file
        )

        print(f"🎉 Conversion successful!")
        print(f"   Generated: {output_path}")

        return 0

    except FileNotFoundError as e:
        print(f"❌ File Error: {e}")
        return 1

    except ConfigurationError as e:
        print(f"❌ Configuration Error: {e}")
        return 1

    except JPKParsingError as e:
        print(f"❌ JPK Parsing Error: {e}")
        return 1

    except KeyboardInterrupt:
        print(f"\n⚠️  Conversion interrupted by user")
        return 130

    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
