"""
JPK parser for J2J v327.

This module handles extraction of components from JPK files,
including business endpoints, tempstorage endpoints, and variables.
"""

import zipfile
import uuid
import re
import xml.etree.ElementTree as ET
from typing import Tuple, List, Dict, Any

from .xml_parser import XMLParser
from ..generators.endpoint_factory import EndpointFactory
from ..generators.script_factory import ScriptFactory
from ..utils.constants import BUSINESS_COMPONENTS, BUSINESS_ADAPTERS, COMPONENT_TYPES
from ..utils.exceptions import JPKParsingError
from ..config.endpoint_rules import get_adapter_display_name


class JPKExtractor:
    """
    JPK extractor for parsing components from JPK files.

    This class provides methods to extract various component types
    from JPK archives, including endpoints and variables.
    """

    def __init__(self, endpoint_factory: EndpointFactory = None, script_factory: ScriptFactory = None):
        """
        Initialize JPK extractor.

        Args:
            endpoint_factory: EndpointFactory instance for creating endpoints.
                            If None, creates a new instance.
            script_factory: ScriptFactory instance for creating script components.
                            If None, creates a new instance.
        """
        self.xml_parser = XMLParser()
        self.endpoint_factory = endpoint_factory or EndpointFactory()
        self.script_factory = script_factory or ScriptFactory()

    def extract_business_endpoints(self, jpk_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extract business endpoints (Salesforce, NetSuite) from JPK components.

        Args:
            jpk_path: Path to JPK file

        Returns:
            Tuple of (Type 500 endpoints, Type 600 endpoints)
        """
        type_500_endpoints = []
        type_600_endpoints = []

        try:
            with self.xml_parser.open_jpk(jpk_path) as jpk:
                # Find business component files
                for component_type, config in BUSINESS_COMPONENTS.items():
                    component_files = [f for f in jpk.namelist()
                                     if f'Data/{component_type}/' in f and f.endswith('.xml')]

                    for component_file in component_files:
                        try:
                            root = self.xml_parser.parse_xml_from_jpk(jpk, component_file)
                            if root is None:
                                continue

                            # Extract header information
                            header_info = self.xml_parser.extract_header_info(root)
                            if not header_info['id']:
                                continue

                            component_id = header_info['id']
                            name = header_info['name'] or component_type

                            if config['type'] == 500:
                                # Create Type 500 endpoint
                                type_600_id = str(uuid.uuid4())

                                endpoint_500 = self.endpoint_factory.create_type_500(
                                    name=name,
                                    polarity=config['polarity'],
                                    adapter_id=config['adapter_id'],
                                    function_name=config['function_name'],
                                    endpoint_id=type_600_id,
                                    component_id=component_id
                                )

                                type_500_endpoints.append(endpoint_500)

                                # Create corresponding Type 600 endpoint
                                endpoint_600 = self.endpoint_factory.create_type_600(type_600_id, config['adapter_id'])
                                endpoint_600['name'] = f"{get_adapter_display_name(config['adapter_id'])} Endpoint"
                                type_600_endpoints.append(endpoint_600)

                                print(f"   ✅ Created {component_type} → Type 500: {name} (ID: {component_id})")
                                print(f"   ✅ Created corresponding Type 600: {endpoint_600['name']} (ID: {type_600_id})")

                            elif config['type'] == 600:
                                # Create Type 600 endpoint directly
                                endpoint_600 = self.endpoint_factory.create_type_600(component_id, config['adapter_id'])
                                endpoint_600['name'] = name
                                type_600_endpoints.append(endpoint_600)

                                print(f"   ✅ Created {component_type} → Type 600: {name} (ID: {component_id})")

                        except Exception as e:
                            print(f"   ❌ Error processing {component_file}: {e}")

                print(f"   📊 Extracted {len(type_500_endpoints)} business Type 500 endpoints")
                print(f"   📊 Extracted {len(type_600_endpoints)} business Type 600 endpoints")

                return type_500_endpoints, type_600_endpoints

        except JPKParsingError:
            # Re-raise parsing errors
            raise
        except Exception as e:
            raise JPKParsingError(f"Error extracting business endpoints from JPK: {e}")

    def extract_tempstorage_endpoints(self, jpk_path: str) -> Tuple[List[Dict[str, Any]], str]:
        """
        Extract tempstorage endpoints from JPK Source and Target entities.

        Args:
            jpk_path: Path to JPK file

        Returns:
            Tuple of (Type 500 endpoints, Type 600 endpoint ID for tempstorage)
        """
        type_500_endpoints = []
        tempstorage_type_600_id = str(uuid.uuid4())  # Single tempstorage endpoint for all

        try:
            with self.xml_parser.open_jpk(jpk_path) as jpk:
                # Process sources (polarity='source')
                source_files = self.xml_parser.find_component_files(jpk, 'Source')
                for source_file in source_files:
                    endpoint = self._create_tempstorage_endpoint(jpk, source_file, 'source',
                                                               tempstorage_type_600_id, 'tempstorage_read')
                    if endpoint:
                        type_500_endpoints.append(endpoint)

                # Process targets (polarity='target')
                target_files = self.xml_parser.find_component_files(jpk, 'Target')
                for target_file in target_files:
                    endpoint = self._create_tempstorage_endpoint(jpk, target_file, 'target',
                                                               tempstorage_type_600_id, 'tempstorage_write')
                    if endpoint:
                        type_500_endpoints.append(endpoint)

                print(f"   📊 Extracted {len(type_500_endpoints)} tempstorage Type 500 endpoints")

                return type_500_endpoints, tempstorage_type_600_id

        except JPKParsingError:
            # Re-raise parsing errors
            raise
        except Exception as e:
            raise JPKParsingError(f"Error extracting tempstorage endpoints from JPK: {e}")

    def extract_project_variables(self, jpk_path: str) -> List[Dict[str, Any]]:
        """
        Extract project variables from JPK source.

        Args:
            jpk_path: Path to JPK file

        Returns:
            List of project variable components
        """
        project_variables = []

        try:
            with self.xml_parser.open_jpk(jpk_path) as jpk:
                project_var_files = self.xml_parser.find_component_files(jpk, 'ProjectVariable')

                for var_file in project_var_files:
                    try:
                        root = self.xml_parser.parse_xml_from_jpk(jpk, var_file)
                        if root is None:
                            continue

                        header_info = self.xml_parser.extract_header_info(root)
                        if not header_info['id']:
                            continue

                        var_id = header_info['id']
                        name = header_info['name'] or 'Unknown Variable'

                        # Create project variable component
                        project_variable = {
                            "name": name,
                            "type": 1000,
                            "id": var_id,
                            "checksum": "1",
                            "metadataVersion": "3.0.1",
                            "encryptedAtRest": True,
                            "passwordEncAtAppLevel": True,
                            "validationState": 300,
                            "hidden": False,
                            "usages": []
                        }

                        project_variables.append(project_variable)
                        print(f"   ✅ Created project variable: {name} (ID: {var_id})")

                    except Exception as e:
                        print(f"   ❌ Error processing project variable {var_file}: {e}")

        except JPKParsingError:
            # Re-raise parsing errors
            raise
        except Exception as e:
            raise JPKParsingError(f"Error extracting project variables from JPK: {e}")

        return project_variables

    def extract_global_variables(self, jpk_path: str) -> List[Dict[str, Any]]:
        """
        Extract global variables from JPK source using both XML files and script content analysis.
        Enhanced with v321 script-based detection for variables declared in scripts.

        Args:
            jpk_path: Path to JPK file

        Returns:
            List of global variable components
        """
        global_variables = []
        global_var_names = set()

        try:
            with self.xml_parser.open_jpk(jpk_path) as jpk:
                # First, extract from traditional GlobalVariable XML files
                global_var_files = self.xml_parser.find_component_files(jpk, 'GlobalVariable')

                for var_file in global_var_files:
                    try:
                        root = self.xml_parser.parse_xml_from_jpk(jpk, var_file)
                        if root is None:
                            continue

                        header_info = self.xml_parser.extract_header_info(root)
                        if not header_info['id']:
                            continue

                        var_id = header_info['id']
                        name = header_info['name'] or 'Unknown Variable'

                        # Track this variable name
                        global_var_names.add(name)

                        # Create global variable component
                        global_variable = {
                            "name": name,
                            "type": COMPONENT_TYPES['GLOBAL_VARIABLE'],
                            "id": var_id,
                            "checksum": "1",
                            "metadataVersion": "3.0.1",
                            "encryptedAtRest": True,
                            "passwordEncAtAppLevel": True,
                            "validationState": 300,
                            "hidden": False,
                            "usages": [],
                            "endpoints": [],
                            "value": "",
                            "requiresDeploy": True,
                            "deployDirty": True,
                            "deployed": False,
                            "chunks": 1,
                            "partial": False
                        }

                        global_variables.append(global_variable)
                        print(f"   ✅ Created global variable: {name} (ID: {var_id})")

                    except Exception as e:
                        print(f"   ❌ Error processing global variable {var_file}: {e}")

                # Enhanced v321 feature: Extract global variables from script content
                print("   🔧 Scanning script files for additional global variable declarations...")
                file_list = jpk.namelist()

                # Look for Script files that may contain global variable declarations
                script_files = [f for f in file_list if '/Data/Script/' in f and f.endswith('.xml')]

                if script_files:
                    print(f"     Scanning {len(script_files)} script files...")

                    import re
                    # Pattern to match global variable declarations: $variableName =
                    global_var_pattern = re.compile(r'\$([a-zA-Z_][a-zA-Z0-9_.]*)\s*=')

                    for script_file in script_files:
                        try:
                            xml_content = jpk.read(script_file).decode('utf-8')
                            root = ET.fromstring(xml_content)

                            # Find script content
                            script_element = root.find('.//konga.string[@name="script"]')
                            if script_element is not None and script_element.text:
                                script_content = script_element.text

                                # Find all global variable declarations
                                matches = global_var_pattern.findall(script_content)
                                for var_name in matches:
                                    # Only add if not already found in XML files
                                    if var_name not in global_var_names:
                                        global_var_names.add(var_name)

                                        # Generate unique ID
                                        import uuid
                                        var_id = str(uuid.uuid4())

                                        # Create global variable component (v321 format)
                                        global_variable = {
                                            "name": var_name,
                                            "type": 1300,  # GLOBAL_VARIABLE type
                                            "endpoints": [],
                                            "usages": [],
                                            "value": "",
                                            "id": var_id,
                                            "checksum": "1",
                                            "requiresDeploy": True,
                                            "deployDirty": True,
                                            "deployed": False,
                                            "chunks": 1,
                                            "partial": False
                                        }

                                        global_variables.append(global_variable)
                                        print(f"   ✅ Found script-declared global variable: {var_name} (ID: {var_id})")

                        except Exception as e:
                            print(f"       ❌ Error processing script file {script_file}: {e}")
                            continue

        except JPKParsingError:
            # Re-raise parsing errors
            raise
        except Exception as e:
            raise JPKParsingError(f"Error extracting global variables from JPK: {e}")

        print(f"   📊 Generated {len(global_variables)} global variables total")
        if global_var_names:
            print(f"       Variable names found: {sorted(global_var_names)}")

        return global_variables

    def _create_tempstorage_endpoint(self, jpk: zipfile.ZipFile, file_path: str,
                                   polarity: str, endpoint_id: str,
                                   function_name: str) -> Dict[str, Any]:
        """
        Create a tempstorage endpoint from source/target file.

        Args:
            jpk: Open ZipFile object
            file_path: Path to component file
            polarity: Endpoint polarity ('source' or 'target')
            endpoint_id: Associated Type 600 endpoint ID
            function_name: Function name for the endpoint

        Returns:
            Type 500 endpoint dictionary or None if creation fails
        """
        try:
            root = self.xml_parser.parse_xml_from_jpk(jpk, file_path)
            if root is None:
                return None

            header_info = self.xml_parser.extract_header_info(root)
            if not header_info['id']:
                return None

            component_id = header_info['id']
            name = header_info['name'] or 'Unknown'

            # Create appropriate endpoint name
            endpoint_name = f"Read {name}" if polarity == 'source' else f"Write {name}"

            endpoint = self.endpoint_factory.create_type_500(
                name=endpoint_name,
                polarity=polarity,
                adapter_id="tempstorage",
                function_name=function_name,
                endpoint_id=endpoint_id,
                component_id=component_id
            )

            print(f"   ✅ Created tempstorage {polarity}: {endpoint_name} (ID: {component_id})")
            return endpoint

        except Exception as e:
            print(f"   ❌ Error processing {polarity} {file_path}: {e}")
            return None

    def extract_operations(self, jpk_path: str) -> List[Dict[str, Any]]:
        """
        Extract operations from JPK file.

        Args:
            jpk_path: Path to JPK file

        Returns:
            List of operation dictionaries with ID, name, activities, and failure_operation_id
        """
        operations = []

        try:
            with self.xml_parser.open_jpk(jpk_path) as jpk:
                # Find operation files
                operation_files = self.xml_parser.find_component_files(jpk, 'Operation')

                for op_file in operation_files:
                    try:
                        root = self.xml_parser.parse_xml_from_jpk(jpk, op_file)
                        if root is None:
                            continue

                        header_info = self.xml_parser.extract_header_info(root)
                        if not header_info['id']:
                            continue

                        # Extract failure_operation_id from Properties section
                        # This creates the visual red lines linking to failure handler operations
                        failure_operation_id = None
                        properties_elem = root.find('Properties')
                        if properties_elem is not None:
                            for item in properties_elem.findall('Item'):
                                if item.get('key') == 'failure_operation_id':
                                    failure_operation_id = item.get('value')
                                    if failure_operation_id:
                                        print(f"   🔗 Found failure link: {header_info['name']} → operation {failure_operation_id[:8]}...")
                                    break

                        # Extract activities from Pipeline
                        activities = []
                        pipeline = root.find('Pipeline')
                        if pipeline is not None:
                            activities_section = pipeline.find('Activities')
                            if activities_section is not None:
                                for activity in activities_section:
                                    # XML attributes are camelCase: activityId, contentId, role, type
                                    # Use .get() on attrib dict directly for camelCase attributes
                                    activity_data = {
                                        'activity_id': activity.attrib.get('activityId', ''),
                                        'type': activity.attrib.get('type', ''),
                                        'role': activity.attrib.get('role', ''),
                                        'name': activity.attrib.get('name', ''),
                                        'content_id': activity.attrib.get('contentId', '')
                                    }
                                    activities.append(activity_data)

                        operation = {
                            'id': header_info['id'],
                            'name': header_info['name'] or 'Unknown Operation',
                            'activities': activities,
                            'failure_operation_id': failure_operation_id
                        }
                        operations.append(operation)

                    except Exception as e:
                        print(f"   ❌ Error processing operation {op_file}: {e}")
                        
        except JPKParsingError:
            raise
        except Exception as e:
            raise JPKParsingError(f"Error extracting operations from JPK: {e}")
        
        return operations

    def extract_scripts_from_operations(self, jpk_path: str, jpk_operations: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Extract ALL scripts from JPK /Data/Script/ directory and create Type 400 script components.
        
        CRITICAL: Extracts ALL scripts from the JPK, not just those referenced in operations.
        This ensures scripts referenced via RunScript() calls are included.
        
        Args:
            jpk_path: Path to JPK file
            jpk_operations: List of operation dictionaries from extract_operations (used for activity_id mapping)
            
        Returns:
            Tuple of (list of script components, dict mapping activity_id to content_id)
        """
        scripts = []
        activity_id_to_content_id = {}
        created_script_ids = set()  # Track which scripts we've already created to avoid duplicates
        
        try:
            with self.xml_parser.open_jpk(jpk_path) as jpk:
                # Find ALL script files from /Data/Script/ directory
                script_files = self.xml_parser.find_component_files(jpk, 'Script')
                
                # Build a map of content_id to script data
                script_by_content_id = {}
                for script_file in script_files:
                    try:
                        root = self.xml_parser.parse_xml_from_jpk(jpk, script_file)
                        if root is None:
                            continue
                        
                        header_info = self.xml_parser.extract_header_info(root)
                        if not header_info['id']:
                            continue
                        
                        content_id = header_info['id']
                        
                        # Extract script content
                        script_content = ""
                        script_elem = root.find('.//konga.string[@name="script"]')
                        if script_elem is not None and script_elem.text:
                            script_content = script_elem.text
                        
                        # Extract script body (without <trans> tags) using ScriptFactory
                        script_body = self.script_factory.extract_script_body_from_xml(script_content) if script_content else ""
                        
                        script_by_content_id[content_id] = {
                            'id': content_id,
                            'name': header_info['name'] or 'Unknown Script',
                            'body': script_body,
                            'content': script_content  # Keep full content for reference
                        }
                    except Exception as e:
                        print(f"   ❌ Error processing script {script_file}: {e}")
                
                # CRITICAL FIX: Extract ALL scripts from script_by_content_id, not just operation-referenced ones
                # This ensures scripts referenced via RunScript() calls are included
                # Track script names to detect and rename duplicates
                script_name_count = {}  # Track how many times each name has been used
                for content_id, script_data in script_by_content_id.items():
                    if content_id not in created_script_ids:
                        # Handle duplicate script names: append _2, _3, etc. to duplicates
                        original_name = script_data['name']
                        script_name = original_name
                        
                        if original_name in script_name_count:
                            # This is a duplicate - increment counter and append suffix
                            script_name_count[original_name] += 1
                            suffix = script_name_count[original_name]
                            script_name = f"{original_name}_{suffix}"
                        else:
                            # First occurrence - initialize counter to 1 (so next duplicate gets _2)
                            script_name_count[original_name] = 1
                        
                        # Create Type 400 script component using ScriptFactory
                        # Scripts use content_id as component ID for consistency with:
                        # - RunScript() calls which use sc.<content_id> format
                        # - JPK script file names which are content_id
                        # - Type 700 transformations which use content_id
                        script_component = self.script_factory.create_script(
                            script_id=content_id,  # Use content_id as component ID
                            script_name=script_name,  # Use potentially renamed script name
                            script_body=script_data['body'],
                            script_content_id=content_id
                        )
                        scripts.append(script_component)
                        created_script_ids.add(content_id)
                        
                        # Log if name was changed
                        if script_name != original_name:
                            print(f"   🔄 Renamed duplicate script: '{original_name}' → '{script_name}'")
                
                # Build activity_id → content_id mapping for operation step references
                # Operation steps use activity_id, but script components use content_id
                for operation in jpk_operations:
                    for activity in operation.get('activities', []):
                        activity_id = activity.get('activity_id', '')  # Fixed: use 'activity_id' instead of 'id'
                        content_id = activity.get('content_id', '')
                        
                        # Map activity_id to content_id for script step references
                        if content_id and content_id in script_by_content_id:
                            activity_id_to_content_id[activity_id] = content_id

        except JPKParsingError:
            raise
        except Exception as e:
            raise JPKParsingError(f"Error extracting scripts from operations: {e}")

        return scripts, activity_id_to_content_id

    def extract_reference_maps(self, jpk_path: str) -> Dict[str, Dict[str, str]]:
        """
        Extract ID → Name mappings for operations and scripts from JPK.

        These mappings are used to transform RunOperation("op.UUID") and
        RunScript("sc.UUID") references to <TAG>operation:Name</TAG> format.

        Args:
            jpk_path: Path to JPK file

        Returns:
            Dictionary with 'operations' and 'scripts' mappings:
            {
                'operations': {uuid: name, ...},
                'scripts': {uuid: name, ...}
            }
        """
        reference_maps = {
            'operations': {},
            'scripts': {}
        }

        try:
            with self.xml_parser.open_jpk(jpk_path) as jpk:
                # Extract operation ID → Name mappings
                operation_files = self.xml_parser.find_component_files(jpk, 'Operation')
                for op_file in operation_files:
                    try:
                        root = self.xml_parser.parse_xml_from_jpk(jpk, op_file)
                        if root is None:
                            continue

                        header_info = self.xml_parser.extract_header_info(root)
                        if header_info['id'] and header_info['name']:
                            reference_maps['operations'][header_info['id']] = header_info['name']
                    except Exception as e:
                        print(f"   ⚠️  Error extracting operation reference from {op_file}: {e}")

                # Extract script ID → Name mappings
                script_files = self.xml_parser.find_component_files(jpk, 'Script')
                for script_file in script_files:
                    try:
                        root = self.xml_parser.parse_xml_from_jpk(jpk, script_file)
                        if root is None:
                            continue

                        header_info = self.xml_parser.extract_header_info(root)
                        if header_info['id'] and header_info['name']:
                            reference_maps['scripts'][header_info['id']] = header_info['name']
                    except Exception as e:
                        print(f"   ⚠️  Error extracting script reference from {script_file}: {e}")

                print(f"   📊 Extracted reference maps: {len(reference_maps['operations'])} operations, {len(reference_maps['scripts'])} scripts")

        except JPKParsingError:
            raise
        except Exception as e:
            raise JPKParsingError(f"Error extracting reference maps from JPK: {e}")

        return reference_maps
