"""
Template manager for J2J v327.

This module handles loading and caching of business endpoint templates
for Salesforce, NetSuite, and other adapter types.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

from ..utils.exceptions import TemplateError
from ..utils.constants import DEFAULT_TEMPLATES_DIR, TEMPLATE_FILES


class TemplateManager:
    """
    Template manager for loading and caching business endpoint templates.

    This class provides centralized template loading with caching and
    fallback handling for missing templates.
    """

    def __init__(self):
        """Initialize template manager with empty cache."""
        self._template_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._cache_loaded = False

    def load_templates(self, templates_dir: str = DEFAULT_TEMPLATES_DIR) -> Dict[str, Dict[str, Any]]:
        """
        Load business endpoint templates from specified directory.

        Returns templates for Salesforce and NetSuite Type 600 endpoints
        with fallback handling for missing templates.

        Args:
            templates_dir: Directory containing template files

        Returns:
            Dictionary mapping adapter_id to template data (or None for fallbacks)
        """
        # Return cached templates if already loaded
        if self._cache_loaded and templates_dir == DEFAULT_TEMPLATES_DIR:
            return self._template_cache.copy()

        templates = {}
        templates_path = Path(templates_dir)

        # Load Salesforce template
        salesforce_path = templates_path / TEMPLATE_FILES['SALESFORCE_TYPE_600']
        try:
            with open(salesforce_path, 'r') as f:
                salesforce_template = json.load(f)
                templates['salesforce'] = salesforce_template
                print(f"   ✅ Loaded Salesforce Type 600 template")
        except FileNotFoundError:
            print(f"   ⚠️  Salesforce template not found, using fallback")
            templates['salesforce'] = None
        except json.JSONDecodeError as e:
            print(f"   ⚠️  Invalid Salesforce template JSON: {e}, using fallback")
            templates['salesforce'] = None
        except Exception as e:
            print(f"   ⚠️  Error loading Salesforce template: {e}, using fallback")
            templates['salesforce'] = None

        # Load NetSuite template
        netsuite_path = templates_path / TEMPLATE_FILES['NETSUITE_TYPE_600']
        try:
            with open(netsuite_path, 'r') as f:
                netsuite_template = json.load(f)
                templates['netsuite'] = netsuite_template
                print(f"   ✅ Loaded NetSuite Type 600 template")
        except FileNotFoundError:
            print(f"   ⚠️  NetSuite template not found, using fallback")
            templates['netsuite'] = None
        except json.JSONDecodeError as e:
            print(f"   ⚠️  Invalid NetSuite template JSON: {e}, using fallback")
            templates['netsuite'] = None
        except Exception as e:
            print(f"   ⚠️  Error loading NetSuite template: {e}, using fallback")
            templates['netsuite'] = None

        # Cache templates if using default directory
        if templates_dir == DEFAULT_TEMPLATES_DIR:
            self._template_cache = templates.copy()
            self._cache_loaded = True

        return templates

    def get_template(self, adapter_id: str, templates_dir: str = DEFAULT_TEMPLATES_DIR) -> Optional[Dict[str, Any]]:
        """
        Get template for specific adapter.

        Args:
            adapter_id: Adapter identifier (e.g., 'salesforce', 'netsuite')
            templates_dir: Directory containing template files

        Returns:
            Template dictionary or None if not found/using fallback
        """
        templates = self.load_templates(templates_dir)
        return templates.get(adapter_id)

    def validate_template(self, template: Dict[str, Any]) -> bool:
        """
        Validate template structure for required fields.

        Args:
            template: Template dictionary to validate

        Returns:
            True if template is valid, False otherwise
        """
        if not isinstance(template, dict):
            return False

        # Check for required template fields
        required_fields = ['name', 'type', 'properties']
        for field in required_fields:
            if field not in template:
                return False

        # Validate type is numeric
        if not isinstance(template.get('type'), int):
            return False

        # Validate properties is a list
        if not isinstance(template.get('properties'), list):
            return False

        return True

    def clear_cache(self) -> None:
        """Clear template cache to force reload on next access."""
        self._template_cache.clear()
        self._cache_loaded = False

    def is_template_available(self, adapter_id: str, templates_dir: str = DEFAULT_TEMPLATES_DIR) -> bool:
        """
        Check if template is available for given adapter.

        Args:
            adapter_id: Adapter identifier
            templates_dir: Directory containing template files

        Returns:
            True if template is available and valid, False otherwise
        """
        template = self.get_template(adapter_id, templates_dir)
        return template is not None and self.validate_template(template)
