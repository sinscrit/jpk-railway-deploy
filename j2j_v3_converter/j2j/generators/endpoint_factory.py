"""
Endpoint factory for J2J v327.

This module provides factory methods for creating Type 500 and Type 600
endpoint components with proper templates and configuration.
"""

import uuid
from typing import Dict, Any, List, Optional

from .template_manager import TemplateManager
from ..utils.constants import (
    COMPONENT_TYPES, DEFAULT_PROPERTIES, BUSINESS_ADAPTERS
)
from ..config.endpoint_rules import (
    create_endpoint_metadata,
    get_adapter_display_name
)


class EndpointFactory:
    """
    Factory class for creating endpoint components.

    This class provides methods to create Type 500 and Type 600 endpoints
    with proper configuration, using templates when available and fallbacks
    when templates are missing.
    """

    def __init__(self, template_manager: TemplateManager = None):
        """
        Initialize endpoint factory.

        Args:
            template_manager: TemplateManager instance for loading templates.
                            If None, creates a new instance.
        """
        self.template_manager = template_manager or TemplateManager()

    def create_type_600(self, endpoint_id: str, adapter_id: str,
                       templates_dir: str = None) -> Dict[str, Any]:
        """
        Create a Type 600 endpoint component with proper configuration.

        Uses correct templates for business adapters (Salesforce, NetSuite)
        and falls back to default structure when templates are not available.

        Args:
            endpoint_id: Unique identifier for the endpoint
            adapter_id: Adapter identifier (e.g., 'salesforce', 'netsuite', 'tempstorage')
            templates_dir: Directory containing template files (optional)

        Returns:
            Dictionary representing Type 600 endpoint component
        """
        # Try to get template for business adapters
        template = None
        if templates_dir:
            template = self.template_manager.get_template(adapter_id, templates_dir)
        else:
            template = self.template_manager.get_template(adapter_id)

        if template and adapter_id in BUSINESS_ADAPTERS:
            # Use the correct template for business adapters
            endpoint = template.copy()

            # Update with our specific values
            endpoint['id'] = endpoint_id
            endpoint['checksum'] = DEFAULT_PROPERTIES['CHECKSUM']
            endpoint['metadataVersion'] = DEFAULT_PROPERTIES['METADATA_VERSION']
            endpoint['encryptedAtRest'] = True
            endpoint['passwordEncAtAppLevel'] = True
            endpoint['validationState'] = DEFAULT_PROPERTIES['VALIDATION_STATE']
            endpoint['hidden'] = False
            endpoint['requiresDeploy'] = True

            return endpoint

        else:
            # Fallback for tempstorage or when templates not available
            # Use proper capitalization mapping instead of .title()
            endpoint_name = f"{get_adapter_display_name(adapter_id)} Endpoint"

            return {
                "name": endpoint_name,
                "isFileBased": True,
                "properties": self._create_default_properties(),
                "type": COMPONENT_TYPES['CONNECTION'],
                "adapterId": adapter_id,
                "id": endpoint_id,
                "checksum": DEFAULT_PROPERTIES['CHECKSUM'],
                "metadataVersion": DEFAULT_PROPERTIES['METADATA_VERSION'],
                "encryptedAtRest": True,
                "passwordEncAtAppLevel": True,
                "validationState": DEFAULT_PROPERTIES['VALIDATION_STATE'],
                "hidden": False,
                "requiresDeploy": True
            }

    def create_type_500(self, name: str, polarity: str, adapter_id: str,
                       function_name: str, endpoint_id: str,
                       component_id: str, object_name: str = None) -> Dict[str, Any]:
        """
        Create a Type 500 endpoint component template.

        Args:
            name: Name of the endpoint
            polarity: Polarity ('source', 'target', 'neutral')
            adapter_id: Adapter identifier
            function_name: Function name for the endpoint
            endpoint_id: Associated Type 600 endpoint ID
            component_id: Unique component identifier
            object_name: Object name for connector activities (e.g., 'Contact' for NetSuite)

        Returns:
            Dictionary representing Type 500 endpoint component
        """
        # Use v321-compatible structure for tempstorage
        if adapter_id == "tempstorage":
            return {
                "name": name,
                "kind": "outbound" if polarity == "source" else "inbound",
                "discoveryType": "FileBasedDiscovery",
                "polarity": polarity,
                "inputRequired": False,
                "properties": self._create_tempstorage_properties(polarity),
                "pageStatus": [{"configured": True, "visited": True}, {"configured": True}],
                "partial": False,
                "functionName": function_name,
                "type": COMPONENT_TYPES['ENDPOINT'],
                "adapterId": adapter_id,
                "endpoint": {"id": endpoint_id, "type": COMPONENT_TYPES['CONNECTION']},
                "id": component_id,
                "checksum": DEFAULT_PROPERTIES['CHECKSUM'],
                "metadataVersion": DEFAULT_PROPERTIES['METADATA_VERSION'],
                "encryptedAtRest": True,
                "passwordEncAtAppLevel": True,
                "validationState": DEFAULT_PROPERTIES['VALIDATION_STATE'],
                "hidden": False,
                "isSchemaDiscovered": True,
                "isConfigurationComplete": True,
                "requiresDeploy": True,
                "plugins": [],
                "chunks": 1
            }

        # NetSuite connector function - requires special structure
        if adapter_id == "netsuite":
            return self._create_netsuite_type_500(
                name=name,
                polarity=polarity,
                function_name=function_name,
                endpoint_id=endpoint_id,
                component_id=component_id,
                object_name=object_name or "Contact"  # Default to Contact
            )

        # For other non-tempstorage adapters, use standard structure
        return {
            "name": name,
            "kind": "inbound" if polarity == "source" else "outbound",
            "discoveryType": "FileBasedDiscovery",
            "polarity": polarity,
            "properties": self._create_default_properties(),
            "pageStatus": [
                {
                    "configured": True,
                    "visited": True
                },
                {
                    "configured": True
                }
            ],
            "functionName": function_name,
            "type": COMPONENT_TYPES['ENDPOINT'],
            "adapterId": adapter_id,
            "endpoint": {
                "id": endpoint_id,
                "type": COMPONENT_TYPES['CONNECTION']
            },
            "id": component_id,
            "checksum": DEFAULT_PROPERTIES['CHECKSUM'],
            "metadataVersion": DEFAULT_PROPERTIES['METADATA_VERSION'],
            "encryptedAtRest": True,
            "passwordEncAtAppLevel": True,
            "validationState": DEFAULT_PROPERTIES['VALIDATION_STATE'],
            "hidden": False,
            "isSchemaDiscovered": True,
            "isConfigurationComplete": True,
            "requiresDeploy": True,
            "plugins": [],
            "chunks": 1,
            "partial": False
        }

    def _create_netsuite_type_500(self, name: str, polarity: str,
                                   function_name: str, endpoint_id: str,
                                   component_id: str, object_name: str) -> Dict[str, Any]:
        """
        Create a NetSuite Type 500 connector activity with proper structure.

        NetSuite activities require ServerBasedDiscovery, metadata, operationTypePatterns,
        and proper list-object-page properties structure for deployment to succeed.

        Args:
            name: Activity name
            polarity: Polarity ('source', 'target', 'neutral')
            function_name: Function name (e.g., 'upsert', 'query')
            endpoint_id: Associated Type 600 endpoint ID
            component_id: Unique component identifier
            object_name: NetSuite object name (e.g., 'Contact', 'Customer')

        Returns:
            Dictionary representing NetSuite Type 500 endpoint component
        """
        # Get metadata for NetSuite Type 500
        metadata = create_endpoint_metadata("netsuite", 500)

        return {
            "kind": "outbound",
            "discoveryType": "ServerBasedDiscovery",
            "polarity": polarity if polarity else "neutral",
            "inputRequired": False,
            "name": name,
            "operationTypePatterns": [
                {
                    "pattern": "^s*Ss*xA(xs*T?)?s*$",
                    "type": 6
                },
                {
                    "pattern": "^s*S?s*xAx?s*T?s*$",
                    "type": 6
                }
            ],
            "metadata": metadata,
            "properties": self._create_netsuite_properties(object_name),
            "functionName": function_name,
            "type": COMPONENT_TYPES['ENDPOINT'],
            "adapterId": "netsuite",
            "endpoint": {
                "id": endpoint_id,
                "type": COMPONENT_TYPES['CONNECTION']
            },
            "id": component_id,
            "checksum": DEFAULT_PROPERTIES['CHECKSUM'],
            "requiresDeploy": True,
            "metadataVersion": DEFAULT_PROPERTIES['METADATA_VERSION'],
            "encryptedAtRest": True,
            "validationState": DEFAULT_PROPERTIES['VALIDATION_STATE'],
            "hidden": False,
            "isSchemaDiscovered": True,
            "pageStatus": [
                {"configured": True, "visited": True},
                {"configured": True}
            ],
            "isConfigurationComplete": True,
            "errorMessage": ""
        }

    def _create_netsuite_properties(self, object_name: str) -> List[Dict[str, Any]]:
        """
        Create NetSuite list-object-page properties structure.

        Args:
            object_name: NetSuite object name (e.g., 'Contact')

        Returns:
            List of properties with proper pagination structure
        """
        return [
            {
                "name": "list-object-page",
                "type": "pagination",
                "children": [
                    {
                        "type": "number",
                        "multiple": False,
                        "name": "entityId",
                        "hidden": True,
                        "defaultValue": 232  # Standard NetSuite entity ID
                    },
                    {
                        "type": "list-object",
                        "multiple": False,
                        "name": "list-object",
                        "displayName": "Select an Object",
                        "use": {
                            "ui": {
                                "selectObjectLabel": "Selected NetSuite Object: ",
                                "tableHeaders": ["Name", "Type", "Object Description"],
                                "tableItems": ["objectName", "objectType", "objecDescription"]
                            },
                            "discoveryType": "provided",
                            "orientation": "inputoutput",
                            "documentIdPath": "this"
                        },
                        "value": {
                            "N": object_name,
                            "T": "standard",
                            "D": "urn:relationships_2018_2.lists.webservices.netsuite.com",
                            "selectedIndex": 40
                        }
                    }
                ]
            }
        ]

    def _create_default_properties(self) -> List[Dict[str, Any]]:
        """
        Create default properties array for endpoints.

        Returns:
            List of property dictionaries with default values
        """
        return [
            {
                "type": "string",
                "multiple": False,
                "name": "entityId",
                "hidden": True,
                "defaultValue": DEFAULT_PROPERTIES['ENTITY_ID']
            },
            {
                "type": "string",
                "multiple": False,
                "name": "source_type_id",
                "hidden": True,
                "defaultValue": DEFAULT_PROPERTIES['SOURCE_TYPE_ID']
            },
            {
                "type": "string",
                "multiple": False,
                "name": "target_type_id",
                "hidden": True,
                "defaultValue": DEFAULT_PROPERTIES['TARGET_TYPE_ID']
            },
            {
                "type": "string",
                "multiple": False,
                "name": "file_share_id",
                "hidden": True,
                "defaultValue": DEFAULT_PROPERTIES['FILE_SHARE_ID']
            }
        ]

    def validate_endpoint(self, endpoint: Dict[str, Any], expected_type: int) -> bool:
        """
        Validate endpoint structure for required fields.

        Args:
            endpoint: Endpoint dictionary to validate
            expected_type: Expected endpoint type (500 or 600)

        Returns:
            True if endpoint is valid, False otherwise
        """
        if not isinstance(endpoint, dict):
            return False

        # Check required fields
        required_fields = ['id', 'type', 'name']
        for field in required_fields:
            if field not in endpoint:
                return False

        # Check type matches expected
        if endpoint.get('type') != expected_type:
            return False

        # Type-specific validation
        if expected_type == COMPONENT_TYPES['ENDPOINT']:  # Type 500
            if 'polarity' not in endpoint or 'functionName' not in endpoint:
                return False

        return True
    def _create_tempstorage_properties(self, polarity):
        """Create v321-style tempstorage properties with exact pagination structure."""
        return [
            {
                "type": "string",
                "multiple": False,
                "name": "entityId",
                "hidden": True,
                "defaultValue": 3
            },
            {
                "name": "page1",
                "displayName": "File configuration", 
                "type": "pagination",
                "children": [
                    {
                        "type": "string",
                        "multiple": False,
                        "name": "locator",
                        "displayName": "Path (Optional)",
                        "validators": [{"name": "pattern", "args": ["[^~%$\"<>:?]*"]}],
                        "value": "[DataPath]"
                    },
                    {
                        "type": "string",
                        "multiple": False,
                        "name": "file_name", 
                        "displayName": "Filename(s)",
                        "validators": [
                            {"name": "required"},
                            {"name": "pattern", "args": ["[^*?\",:<>|]*"]}
                        ],
                        "variables": {"fileVars": True},
                        "value": "[DataFilename]"
                    }
                ]
            }
        ]
