"""
Configuration loader for J2J v327.

This module handles loading and parsing of j2j_config.json files,
providing structured configuration objects with validation.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any

from .models import J2JConfig
from ..utils.exceptions import ConfigurationError
from ..utils.constants import DEFAULT_CONFIG_PATH


class ConfigLoader:
    """
    Configuration loader class for handling j2j_config.json files.

    This class is responsible for loading, parsing, and validating
    configuration files, converting them to structured J2JConfig objects.
    """

    @classmethod
    def load(cls, config_path: str = DEFAULT_CONFIG_PATH) -> J2JConfig:
        """
        Load configuration from j2j_config.json file.

        Args:
            config_path: Path to the configuration file

        Returns:
            J2JConfig object with validated configuration

        Raises:
            ConfigurationError: If config file doesn't exist, is invalid JSON,
                               or missing required configuration
        """
        print(f"📋 Loading configuration from {config_path}...")

        # Check if config file exists
        if not os.path.exists(config_path):
            raise ConfigurationError(f"Configuration file not found: {config_path}")

        # Load and parse config file
        try:
            with open(config_path, 'r') as f:
                config_dict = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except (IOError, OSError) as e:
            raise ConfigurationError(f"Cannot read configuration file {config_path}: {e}")

        # Convert to structured config object
        try:
            config = J2JConfig.from_dict(config_dict)
        except ConfigurationError:
            # Re-raise configuration errors as-is
            raise
        except Exception as e:
            raise ConfigurationError(f"Error parsing configuration: {e}")

        # Perform validation if enabled
        if config.validation.enabled:
            cls._validate_config(config)

        # Log successful loading
        print(f"   📊 Configuration loaded successfully:")
        print(f"      Version: {config.version}")
        print(f"      Converter: v{config.converter.version}")
        print(f"      Baseline: {config.baseline.path}")

        return config

    @classmethod
    def _validate_config(cls, config: J2JConfig) -> None:
        """
        Validate configuration settings.

        In strict_mode (default), all validation failures raise errors.
        This ensures no silent failures or incomplete conversions.

        Args:
            config: J2JConfig object to validate

        Raises:
            ConfigurationError: If validation fails
        """
        strict = config.validation.strict_mode

        # Validate baseline file if required
        if config.validation.check_baseline_exists:
            try:
                config.baseline.validate()
                print(f"   ✅ Baseline file validated: {config.baseline.path}")
            except ConfigurationError as e:
                raise ConfigurationError(f"Baseline validation failed: {e}")

        # Validate templates directory if required
        if config.validation.check_templates_exist:
            try:
                config.templates.validate()
                print(f"   ✅ Templates directory validated: {config.templates.directory}")
            except ConfigurationError as e:
                if strict:
                    raise ConfigurationError(f"Templates directory validation failed: {e}")
                else:
                    print(f"   ⚠️  Templates directory not found: {config.templates.directory} (will use fallbacks)")

        # Validate schema references directory if required
        if config.validation.check_schema_references_exist:
            try:
                config.schema_references.validate()
                print(f"   ✅ Schema references directory validated: {config.schema_references.directory}")
            except ConfigurationError as e:
                if strict:
                    raise ConfigurationError(f"Schema references directory validation failed: {e}")
                else:
                    print(f"   ⚠️  Schema references directory not found: {config.schema_references.directory}")

    @classmethod
    def load_raw(cls, config_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
        """
        Load configuration as raw dictionary without validation.

        This method is useful for debugging or when you need the raw
        configuration data without structured objects.

        Args:
            config_path: Path to the configuration file

        Returns:
            Raw configuration dictionary

        Raises:
            ConfigurationError: If config file doesn't exist or is invalid JSON
        """
        if not os.path.exists(config_path):
            raise ConfigurationError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file: {e}")
        except (IOError, OSError) as e:
            raise ConfigurationError(f"Cannot read configuration file {config_path}: {e}")
