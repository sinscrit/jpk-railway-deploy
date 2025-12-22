"""
Constants for J2J v327.

This module contains all hardcoded values extracted from the original
j2j_v325.py implementation for better maintainability.
"""

# Component type mappings from Jitterbit
COMPONENT_TYPES = {
    'CONNECTOR': 200,
    'PLUGIN': 400,
    'ENDPOINT': 500,
    'CONNECTION': 600,
    'TRANSFORMATION': 700,
    'SCHEMA': 900,
    'PROJECT_VARIABLE': 1000,
    'NOTIFICATION': 1200,
    'GLOBAL_VARIABLE': 1300
}

# Business component mappings from j2j_v325.py line 283-288
BUSINESS_COMPONENTS = {
    'SalesforceQuery': {
        'type': 500,
        'adapter_id': 'salesforce',
        'function_name': 'query',
        'polarity': 'source'
    },
    'NetSuiteUpsert': {
        'type': 500,
        'adapter_id': 'netsuite',
        'function_name': 'upsert',
        'polarity': 'neutral'
    },
    'SalesforceConnector': {
        'type': 600,
        'adapter_id': 'salesforce'
    },
    'NetSuiteEndpoint': {
        'type': 600,
        'adapter_id': 'netsuite'
    }
}

# Supported business adapters
BUSINESS_ADAPTERS = ['salesforce', 'netsuite', 'tempstorage']

# Default configuration paths
DEFAULT_CONFIG_PATH = "j2j_config.json"
DEFAULT_TEMPLATES_DIR = "j2j_templates"

# File extensions
FILE_EXTENSIONS = {
    'JPK': '.jpk',
    'JSON': '.json',
    'XML': '.xml',
    'XSD': '.xsd'
}

# Template filenames
TEMPLATE_FILES = {
    'SALESFORCE_TYPE_600': 'salesforce_type_600_template.json',
    'NETSUITE_TYPE_600': 'netsuite_type_600_template.json'
}

# Component ordering for final JSON output
COMPONENT_ORDER = [200, 400, 500, 600, 700, 900, 1000, 1200, 1300]

# Default property values for endpoints
DEFAULT_PROPERTIES = {
    'ENTITY_ID': 5,
    'SOURCE_TYPE_ID': 15,
    'TARGET_TYPE_ID': 16,
    'FILE_SHARE_ID': 1,
    'CHECKSUM': "1",
    'METADATA_VERSION': "3.0.1",
    'VALIDATION_STATE': 300
}

# XML Schema namespace
XML_SCHEMA_NAMESPACE = {'xs': 'http://www.w3.org/2001/XMLSchema'}

# Version constants
J2J_VERSION = "3.2.7"
SOURCE_VERSION = "v325"
TARGET_VERSION = "v327"
