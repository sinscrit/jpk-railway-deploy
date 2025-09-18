#!/usr/bin/env python3
"""
Generate Type 500 components directly from JPK entities and connectors.

This replaces the target-specific tmp/type500_components.json dependency
with a generic solution that works for any JPK file.
"""

import json
import uuid
from typing import Dict, List, Any
import zipfile
import xml.etree.ElementTree as ET
import tempfile
import os


def generate_type500_from_jpk(jpk_path: str) -> List[Dict[str, Any]]:
    """
    Generate Type 500 activity components directly from JPK entities and connectors.
    
    This function extracts information from the JPK file itself rather than relying
    on target-specific intermediate files, making the converter truly generic.
    
    Args:
        jpk_path: Path to the JPK file
        
    Returns:
        List of Type 500 component dictionaries
    """
    type500_components = []
    
    try:
        with zipfile.ZipFile(jpk_path, 'r') as zip_file:
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_file.extractall(temp_dir)
                
                # Find project file
                project_file = None
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file == 'project.xml':
                            project_file = os.path.join(root, file)
                            break
                    if project_file:
                        break
                
                if not project_file:
                    print("Warning: No project.xml file found in JPK")
                    return []
                
                # Parse project structure
                tree = ET.parse(project_file)
                root = tree.getroot()
                project_name = root.attrib.get('name', 'Unknown Project')
                
                print(f"   Generating Type 500 components from JPK: {project_name}")
                
                # Extract connectors from JPK structure
                connectors = extract_connectors_from_jpk(temp_dir)
                print(f"   Found {len(connectors)} connectors in JPK")
                
                # Extract entities that could be activities
                entities = extract_activity_entities_from_jpk(root)
                print(f"   Found {len(entities)} potential activity entities in JPK")
                
                # Generate Type 500 components based on connectors and entities
                component_id = 1
                
                # Generate components for each connector type
                for connector in connectors:
                    connector_type = connector.get('type', 'unknown')
                    connector_name = connector.get('name', f'Unknown {connector_type}')
                    
                    # Determine adapter ID based on connector type
                    adapter_id = map_connector_to_adapter(connector_type)
                    
                    # Create read/write components for each connector
                    for polarity in ['source', 'target']:
                        component_name = f"{polarity.title()} {connector_name}"
                        
                        component = create_generic_type500_component(
                            name=component_name,
                            component_id=str(uuid.uuid4()),
                            adapter_id=adapter_id,
                            polarity=polarity,
                            connector_info=connector
                        )
                        
                        type500_components.append(component)
                        component_id += 1
                
                # Generate logging/monitoring components (generic for all projects)
                logging_components = generate_generic_logging_components()
                type500_components.extend(logging_components)
                
                print(f"   Generated {len(type500_components)} Type 500 components from JPK")
                
    except Exception as e:
        print(f"Warning: Error generating Type 500 components from JPK: {e}")
        return []
    
    return type500_components


def extract_connectors_from_jpk(temp_dir: str) -> List[Dict[str, Any]]:
    """Extract connector information from JPK directory structure."""
    connectors = []
    
    # Find project subdirectory
    project_dirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
    if not project_dirs:
        return connectors
    
    project_dir = os.path.join(temp_dir, project_dirs[0])
    data_dir = os.path.join(project_dir, "Data")
    
    if not os.path.exists(data_dir):
        return connectors
    
    # Map directory names to connector types
    connector_mappings = {
        'SalesforceConnector': 'salesforce',
        'NetSuiteEndpoint': 'netsuite',
        'NetSuiteUpsert': 'netsuite',
        'FileConnector': 'file',
        'DatabaseConnector': 'database',
        'HTTPConnector': 'http',
        'FTPConnector': 'ftp'
    }
    
    # Scan for connector directories
    for dir_name in os.listdir(data_dir):
        dir_path = os.path.join(data_dir, dir_name)
        if os.path.isdir(dir_path) and dir_name in connector_mappings:
            connector_type = connector_mappings[dir_name]
            
            # Count XML files in directory
            xml_files = [f for f in os.listdir(dir_path) if f.endswith('.xml')]
            
            if xml_files:
                connectors.append({
                    'type': connector_type,
                    'name': dir_name.replace('Connector', '').replace('Endpoint', ''),
                    'directory': dir_path,
                    'file_count': len(xml_files)
                })
    
    return connectors


def extract_activity_entities_from_jpk(project_root) -> List[Dict[str, Any]]:
    """Extract entities that represent activities from JPK project structure."""
    entities = []
    
    # Look for entity types that typically represent activities
    activity_entity_types = [
        'Operation',
        'Transformation', 
        'Script',
        'WebServiceCall',
        'DatabaseQuery',
        'FileOperation'
    ]
    
    for et in project_root.findall('EntityType'):
        et_name = et.attrib.get('name', '')
        
        # Check if this entity type represents activities
        if any(activity_type.lower() in et_name.lower() for activity_type in activity_entity_types):
            # Extract entities from this type
            for entity in et.findall('Entity'):
                entities.append({
                    'name': entity.attrib.get('name', ''),
                    'type': et_name,
                    'entityId': entity.attrib.get('entityId', ''),
                    'label': entity.attrib.get('label', '')
                })
            
            # Extract entities from folders
            for folder in et.findall('Folder'):
                for entity in folder.findall('Entity'):
                    entities.append({
                        'name': entity.attrib.get('name', ''),
                        'type': et_name,
                        'entityId': entity.attrib.get('entityId', ''),
                        'label': entity.attrib.get('label', '')
                    })
    
    return entities


def map_connector_to_adapter(connector_type: str) -> str:
    """Map connector type to adapter ID."""
    mapping = {
        'salesforce': 'salesforce',
        'netsuite': 'netsuite', 
        'file': 'tempstorage',
        'database': 'database',
        'http': 'http',
        'ftp': 'ftp'
    }
    return mapping.get(connector_type.lower(), 'tempstorage')


def create_generic_type500_component(name: str, component_id: str, adapter_id: str, 
                                    polarity: str, connector_info: Dict[str, Any]) -> Dict[str, Any]:
    """Create a generic Type 500 component structure."""
    
    # Determine discovery type based on adapter
    discovery_type = "FileBasedDiscovery" if adapter_id == "tempstorage" else "ConnectorBasedDiscovery"
    
    # Determine kind based on polarity
    kind = "outbound"  # Most Jitterbit activities are outbound
    
    component = {
        "kind": kind,
        "discoveryType": discovery_type,
        "polarity": polarity,
        "inputRequired": polarity == "target",
        "name": name,
        "properties": create_generic_properties(adapter_id, polarity, connector_info),
        "endpoint": {
            "id": str(uuid.uuid4()),
            "type": 600
        },
        "adapterId": adapter_id,
        "checksum": "1",
        "chunks": 1,
        "encryptedAtRest": True,
        "functionName": name.lower().replace(" ", "_"),  # Required by interface
        "hidden": False,
        "id": component_id,
        "isConfigurationComplete": True,
        "isSchemaDiscovered": False,
        "metadataVersion": "3.0.1",
        "pageStatus": {},
        "partial": False,
        "passwordEncAtAppLevel": False,
        "plugins": [],
        "requiresDeploy": True,
        "type": 500,
        "validationState": 100
    }
    
    return component


def create_generic_properties(adapter_id: str, polarity: str, connector_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create generic properties array for Type 500 component."""
    
    if adapter_id == "salesforce":
        return create_salesforce_properties(polarity)
    elif adapter_id == "netsuite":
        return create_netsuite_properties(polarity)
    else:
        return create_file_properties(polarity)


def create_salesforce_properties(polarity: str) -> List[Dict[str, Any]]:
    """Create Salesforce-specific properties."""
    return [{
        "type": "string",
        "multiple": False,
        "name": "entityId", 
        "hidden": True,
        "defaultValue": "1"
    }]


def create_netsuite_properties(polarity: str) -> List[Dict[str, Any]]:
    """Create NetSuite-specific properties."""
    return [{
        "name": "list-object-page",
        "type": "pagination",
        "children": [{
            "type": "number",
            "multiple": False,
            "name": "entityId",
            "hidden": True,
            "defaultValue": 232
        }, {
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
                "N": "Generic Object",
                "T": "standard", 
                "D": "urn:generic.webservices.netsuite.com",
                "selectedIndex": 1
            }
        }]
    }]


def create_file_properties(polarity: str) -> List[Dict[str, Any]]:
    """Create file/tempstorage properties."""
    return [{
        "type": "string",
        "multiple": False,
        "name": "entityId",
        "hidden": True,
        "defaultValue": 3
    }, {
        "name": "page1",
        "displayName": "File configuration", 
        "type": "pagination",
        "children": [{
            "type": "string",
            "multiple": False,
            "name": "locator",
            "displayName": "Path (Optional)",
            "validators": [{
                "name": "pattern",
                "args": ["[^~%$\"<>:?]*"]
            }],
            "defaultValue": f"/tmp/{polarity}_file.txt"
        }]
    }]


def generate_generic_logging_components() -> List[Dict[str, Any]]:
    """Generate generic logging and monitoring components."""
    logging_components = []
    
    # Common logging component types
    log_types = [
        ("Success Count", "source"),
        ("Success Count", "target"), 
        ("Failure Count", "source"),
        ("Failure Count", "target"),
        ("Data Error", "source"),
        ("Data Error", "target"),
        ("Summary Log", "source"),
        ("Summary Log", "target")
    ]
    
    for log_type, polarity in log_types:
        component = create_generic_type500_component(
            name=f"{polarity.title()} {log_type}",
            component_id=str(uuid.uuid4()),
            adapter_id="tempstorage",
            polarity=polarity,
            connector_info={"type": "logging"}
        )
        logging_components.append(component)
    
    return logging_components


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python generate_type500_from_jpk.py <jpk_file>")
        sys.exit(1)
    
    jpk_file = sys.argv[1]
    components = generate_type500_from_jpk(jpk_file)
    
    print(f"\n=== GENERATED {len(components)} TYPE 500 COMPONENTS ===")
    for i, comp in enumerate(components, 1):
        print(f"{i}. {comp['name']} (Adapter: {comp['adapterId']}, Polarity: {comp['polarity']})")
    
    # Save to file
    with open('tmp/type500_components_from_jpk.json', 'w') as f:
        json.dump(components, f, indent=2)
    
    print(f"\nSaved components to tmp/type500_components_from_jpk.json")
