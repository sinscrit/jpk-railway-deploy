"""
Data models for J2J v327 configuration management.

This module provides structured data classes for handling configuration
with validation and type safety.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional
from ..utils.exceptions import ConfigurationError


@dataclass
class BaselineConfig:
    """Configuration for baseline JSON file."""
    path: Path

    def validate(self) -> None:
        """
        Validate that the baseline file exists and is readable.

        Raises:
            ConfigurationError: If baseline file doesn't exist or isn't readable
        """
        if not self.path.exists():
            raise ConfigurationError(f"Baseline file not found: {self.path}")

        if not self.path.is_file():
            raise ConfigurationError(f"Baseline path is not a file: {self.path}")

        try:
            self.path.read_text()
        except (IOError, OSError) as e:
            raise ConfigurationError(f"Cannot read baseline file {self.path}: {e}")


@dataclass
class TemplatesConfig:
    """Configuration for template directory and files."""
    directory: Path

    def validate(self) -> None:
        """
        Validate that the templates directory exists.

        Raises:
            ConfigurationError: If templates directory doesn't exist
        """
        if not self.directory.exists():
            raise ConfigurationError(f"Templates directory not found: {self.directory}")

        if not self.directory.is_dir():
            raise ConfigurationError(f"Templates path is not a directory: {self.directory}")


@dataclass
class SchemaReferencesConfig:
    """Configuration for schema references directory."""
    directory: Path

    def validate(self) -> None:
        """
        Validate that the schema references directory exists.

        Raises:
            ConfigurationError: If schema references directory doesn't exist
        """
        if not self.directory.exists():
            raise ConfigurationError(f"Schema references directory not found: {self.directory}")

        if not self.directory.is_dir():
            raise ConfigurationError(f"Schema references path is not a directory: {self.directory}")


@dataclass
class ValidationConfig:
    """Configuration for validation settings."""
    enabled: bool = True
    check_baseline_exists: bool = True
    check_templates_exist: bool = True
    check_schema_references_exist: bool = True
    strict_mode: bool = True


@dataclass
class OutputConfig:
    """Configuration for output file settings."""
    default_prefix: str = "output_v327_config_based"
    include_timestamp: bool = False


@dataclass
class ConverterConfig:
    """Configuration for converter version info."""
    version: str = "327"


@dataclass
class TraceLogConfig:
    """Configuration for trace logging settings."""
    enabled: bool = False
    verbosity: str = "normal"  # minimal, normal, detailed, debug
    output_directory: str = "trace_logs"
    
    def validate(self) -> None:
        """
        Validate trace log configuration.
        
        Raises:
            ConfigurationError: If verbosity level is invalid
        """
        valid_levels = ["minimal", "normal", "detailed", "debug"]
        if self.verbosity.lower() not in valid_levels:
            raise ConfigurationError(f"Invalid verbosity level: {self.verbosity}. Must be one of {valid_levels}")


@dataclass
class J2JConfig:
    """Main configuration class containing all config sections."""
    baseline: BaselineConfig
    templates: TemplatesConfig
    schema_references: SchemaReferencesConfig
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    converter: ConverterConfig = field(default_factory=ConverterConfig)
    trace_log: TraceLogConfig = field(default_factory=TraceLogConfig)
    version: str = "v327"

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'J2JConfig':
        """
        Create J2JConfig from dictionary (parsed from JSON).

        Args:
            config_dict: Dictionary containing configuration data

        Returns:
            J2JConfig instance

        Raises:
            ConfigurationError: If required configuration is missing or invalid
        """
        # Validate required sections
        if 'baseline' not in config_dict:
            raise ConfigurationError("Configuration missing required 'baseline' section")

        baseline_section = config_dict['baseline']
        if 'path' not in baseline_section:
            raise ConfigurationError("Configuration missing required 'baseline.path'")

        # Create baseline config
        baseline = BaselineConfig(
            path=Path(baseline_section['path'])
        )

        # Create templates config
        templates_section = config_dict.get('templates', {})
        templates_dir = templates_section.get('directory', 'j2j_templates')
        templates = TemplatesConfig(
            directory=Path(templates_dir)
        )

        # Create schema references config
        schema_refs_section = config_dict.get('schema_references', {})
        schema_refs_dir = schema_refs_section.get('directory', 'schema_references')
        schema_references = SchemaReferencesConfig(
            directory=Path(schema_refs_dir)
        )

        # Create validation config
        validation_section = config_dict.get('validation', {})
        validation = ValidationConfig(
            enabled=validation_section.get('enabled', True),
            check_baseline_exists=validation_section.get('check_baseline_exists', True),
            check_templates_exist=validation_section.get('check_templates_exist', True),
            check_schema_references_exist=validation_section.get('check_schema_references_exist', True),
            strict_mode=validation_section.get('strict_mode', True)
        )

        # Create output config
        output_section = config_dict.get('output', {})
        output = OutputConfig(
            default_prefix=output_section.get('default_prefix', 'output_v327_config_based'),
            include_timestamp=output_section.get('include_timestamp', False)
        )

        # Create converter config
        converter_section = config_dict.get('converter', {})
        converter = ConverterConfig(
            version=converter_section.get('version', '327')
        )

        # Create trace log config
        trace_log_section = config_dict.get('trace_log', {})
        trace_log = TraceLogConfig(
            enabled=trace_log_section.get('enabled', False),
            verbosity=trace_log_section.get('verbosity', 'normal'),
            output_directory=trace_log_section.get('output_directory', 'trace_logs')
        )
        trace_log.validate()

        return cls(
            baseline=baseline,
            templates=templates,
            schema_references=schema_references,
            validation=validation,
            output=output,
            converter=converter,
            trace_log=trace_log,
            version=config_dict.get('version', 'v327')
        )
