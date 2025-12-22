"""
Schema generator for J2J v327.

This module handles generation of Schema Document Components (Type 900) and XSD assets
from JPK files, providing the functionality that was present in v321.
"""

import zipfile
import xml.etree.ElementTree as ET
import base64
import zlib
import uuid
import re
import json
import gzip
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..parsers.xml_parser import XMLParser
from ..utils.exceptions import JPKParsingError
from ..utils.constants import COMPONENT_TYPES
from ..utils.trace_logger import TraceLogger, VerbosityLevel


class SchemaGenerator:
    """
    Generator for Schema Document Components and XSD assets.

    This class provides methods to:
    - Extract XSD files from JPK archives
    - Generate compressed XSD assets
    - Create Schema Document Components (Type 900)
    - Generate human-readable schema names
    """

    # Type ID to Adapter mapping (matching jpk_transformation_converter.py)
    TYPE_ID_TO_ADAPTER = {
        '14': 'salesforce',
        '101': 'netsuite',
        '102': 'netsuite',
    }

    @staticmethod
    def _filter_prescript_nodes(schema_doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter out /PRESCRIPT/ nodes from schema documents.

        /PRESCRIPT/ is a Jitterbit Design Studio marker for pre-transformation scripts.
        It should not appear as a field in Integration Studio schemas.

        Args:
            schema_doc: Schema document with 'root' key

        Returns:
            Filtered schema document
        """
        if not schema_doc or not isinstance(schema_doc, dict):
            return schema_doc

        def filter_children(node: Dict[str, Any]) -> Dict[str, Any]:
            """Recursively filter PRESCRIPT nodes from children."""
            if not isinstance(node, dict):
                return node

            # Filter children if present
            if 'C' in node and isinstance(node['C'], list):
                filtered_children = []
                for child in node['C']:
                    # Skip PRESCRIPT nodes
                    child_name = child.get('N', '') if isinstance(child, dict) else ''
                    if 'PRESCRIPT' in child_name:
                        continue
                    # Recursively filter nested children
                    filtered_children.append(filter_children(child))
                node = dict(node)  # Make a copy
                node['C'] = filtered_children

            return node

        result = dict(schema_doc)  # Make a copy
        if 'root' in result:
            result['root'] = filter_children(result['root'])
        return result

    def __init__(self):
        """Initialize schema generator."""
        self.xml_parser = XMLParser()
        self.schema_references_cache = {}  # Cache loaded reference schemas
        self.guid_cache = {}  # Cache for deterministic GUIDs
    
    def _generate_guid(self, seed: str) -> str:
        """
        Generate deterministic GUID from seed value.
        
        CRITICAL: This uses the SAME namespace and method as jpk_transformation_converter.py
        to ensure Type 700 and Type 900 generate matching IDs for the same schema.
        
        Args:
            seed: Seed string (typically schema filename)
            
        Returns:
            Deterministic UUID string
        """
        if seed in self.guid_cache:
            return self.guid_cache[seed]
        
        # Use UUID5 for deterministic generation (SAME namespace as transformation converter!)
        namespace = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')
        guid = str(uuid.uuid5(namespace, seed))
        self.guid_cache[seed] = guid
        return guid

    def generate_assets_from_jpk(self, jpk_path: str) -> List[Dict[str, Any]]:
        """
        Generate XSD assets from JPK using generic rules.

        Includes external connector schemas (any non-Jitterbit schemas)
        Excludes Jitterbit canonical/internal schemas based on v321 logic.

        Args:
            jpk_path: Path to JPK file

        Returns:
            List of asset dictionaries with compressed XSD content
        """
        print("   🔧 Generating XSD assets from JPK using generic rules...")

        assets = []

        try:
            with zipfile.ZipFile(jpk_path, 'r') as jpk:
                files = jpk.namelist()

                # Find all XSD files
                xsd_files = [f for f in files if f.endswith('.xsd')]
                print(f"     Found {len(xsd_files)} XSD files in JPK")

                for xsd_file in xsd_files:
                    try:
                        # Read XSD content
                        content = jpk.read(xsd_file).decode('utf-8')
                        filename = xsd_file.split('/')[-1]

                        # Parse XML to get namespace
                        root = ET.fromstring(content)
                        namespace = root.attrib.get('targetNamespace', '')

                        # Apply generic inclusion rules from v321
                        if self._should_include_xsd_as_asset(filename, namespace):
                            # Compress content using v321 approach
                            compressed_content = base64.b64encode(
                                zlib.compress(content.encode('utf-8'))
                            ).decode('utf-8')

                            # Generate asset structure
                            asset = {
                                "path": filename,  # Keep original JPK filename
                                "type": "xml",
                                "properties": self._generate_xsd_properties(namespace, len(content)),
                                "compressedContent": compressed_content
                            }

                            assets.append(asset)
                            print(f"       ✅ Included: {filename} ({len(content)} bytes)")
                        else:
                            print(f"       ❌ Excluded: {filename} (canonical/internal)")

                    except Exception as e:
                        print(f"       Error processing {xsd_file}: {e}")

        except Exception as e:
            print(f"     Error reading JPK file: {e}")

        print(f"   📊 Generated {len(assets)} XSD assets using generic rules")
        return assets

    def _load_schema_from_transformations(self, schema_filename: str, transformations: List[Dict]) -> Optional[Dict[str, Any]]:
        """
        Load schema structure from Type 700 transformations that have it embedded.

        This extracts schema structures that were already successfully parsed and embedded
        in transformation components by jpk_transformation_converter.py.

        IMPORTANT: For canonical/XSD schemas, returns the full document including 'types', 'O',
        and 'name' fields at the same level as 'root'. These are required for Type 900 schema
        components to be valid.

        Args:
            schema_filename: Schema filename (e.g., 'jb-canonical-contact.xsd')
            transformations: List of Type 700 transformation components

        Returns:
            Full schema document (with root, types, O, name) or just root for simple schemas,
            or None if not found
        """
        try:
            # Search through all transformations for matching embedded schema
            for trans in transformations:
                # Check source
                if trans.get('source', {}).get('name') == schema_filename:
                    source_doc = trans.get('source', {}).get('document')
                    if source_doc and 'root' in source_doc:
                        print(f"         📋 Extracted structure from transformation source: {trans.get('name')}")
                        # Return full document if it has 'types' or 'O' (canonical schema)
                        # Otherwise return just the root for backward compatibility
                        if 'types' in source_doc or 'O' in source_doc:
                            return source_doc  # Full document with root, types, O, name
                        return source_doc['root']

                # Check target
                if trans.get('target', {}).get('name') == schema_filename:
                    target_doc = trans.get('target', {}).get('document')
                    if target_doc and 'root' in target_doc:
                        print(f"         📋 Extracted structure from transformation target: {trans.get('name')}")
                        # Return full document if it has 'types' or 'O' (canonical schema)
                        # Otherwise return just the root for backward compatibility
                        if 'types' in target_doc or 'O' in target_doc:
                            return target_doc  # Full document with root, types, O, name
                        return target_doc['root']

        except Exception as e:
            print(f"       Error extracting from transformations: {e}")

        return None
    
    def _extract_schema_id_from_transformations(self, schema_filename: str, transformations: List[Dict]) -> Optional[str]:
        """
        Extract schema ID from Type 700 transformations.
        
        Uses JPK native IDs (call_id, doc_id) that were preserved in Type 700 components.
        
        Args:
            schema_filename: Schema filename to look for
            transformations: List of Type 700 transformation components
            
        Returns:
            Schema ID or None if not found
        """
        if not transformations:
            return None
        
        try:
            for trans in transformations:
                # Check source schema
                source = trans.get('source', {})
                if source.get('name') == schema_filename:
                    schema_id = source.get('id')
                    if schema_id:
                        print(f"         🔑 Using schema ID from transformation source: {schema_id[:8]}...")
                        return schema_id
                
                # Check target schema
                target = trans.get('target', {})
                if target.get('name') == schema_filename:
                    schema_id = target.get('id')
                    if schema_id:
                        print(f"         🔑 Using schema ID from transformation target: {schema_id[:8]}...")
                        return schema_id
        except Exception as e:
            print(f"       Error extracting schema ID: {e}")
        
        return None
    
    def _parse_jtr_to_json_notation(self, jtr_content: str, doc_root: str = None) -> Optional[Dict[str, Any]]:
        """
        Parse JTR XML and convert to field structure format.
        
        Args:
            jtr_content: JTR XML content
            doc_root: Document root element name
            
        Returns:
            Field structure dictionary
        """
        try:
            root = ET.fromstring(jtr_content)
            
            # Build type library
            type_library = {}
            for elem_type in root.findall('.//ElementType'):
                type_name = elem_type.get('Name')
                if type_name:
                    fields = []
                    for crom in elem_type.findall('.//CROM'):
                        field_data = {
                            'name': crom.get('Name'),
                            'type': crom.get('Type', '0x1'),
                            'nature': crom.get('Nature', 'element'),
                            'children': []
                        }
                        fields.append(field_data)
                    type_library[type_name] = fields
            
            # Find document root CROM
            if doc_root:
                for crom in root.findall('.//CROM[@Name]'):
                    if crom.get('Name') == doc_root:
                        # Resolve type references recursively
                        fields = self._resolve_jtr_type(crom, type_library)
                        return {
                            'fields': fields,
                            'field_count': len(fields)
                        }
            
            return None
            
        except Exception as e:
            return None
    
    def _resolve_jtr_type(self, crom_elem, type_library: Dict) -> List[Dict]:
        """
        Recursively resolve JTR type references.
        
        Args:
            crom_elem: CROM XML element
            type_library: Dictionary of type definitions
            
        Returns:
            List of field dictionaries
        """
        fields = []
        type_ref = crom_elem.get('Type')
        
        if type_ref and type_ref in type_library:
            for field_data in type_library[type_ref]:
                field = {
                    'name': field_data['name'],
                    'type': field_data['type'],
                    'nature': field_data['nature'],
                    'children': []
                }
                
                # Recursively resolve child types
                if field_data.get('type') in type_library:
                    child_crom = ET.Element('CROM')
                    child_crom.set('Type', field_data['type'])
                    field['children'] = self._resolve_jtr_type(child_crom, type_library)
                
                fields.append(field)
        
        return fields
    
    def _jtr_field_to_json_notation(self, field: Dict) -> Dict[str, Any]:
        """
        Convert JTR field structure to Jitterbit JSON notation.
        
        Args:
            field: Field dictionary from JTR
            
        Returns:
            JSON notation structure
        """
        # Map JTR type codes to min/max occurs
        type_code = field.get('type', '0x1')
        type_map = {
            '0x1': (1, 1),           # Required single
            '0x9': (0, 'unbounded'), # Optional array
            '0x24': (0, 1),          # Optional single
            '0x21': (1, 1),          # Required single
        }
        min_occurs, max_occurs = type_map.get(type_code, (0, 1))
        
        result = {
            'N': field['name'],
            'MN': min_occurs,
            'MX': max_occurs,
        }
        
        # Add children if any
        if field.get('children'):
            result['C'] = [self._jtr_field_to_json_notation(child) for child in field['children']]
        
        return result

    def _load_schema_structure(self, schema_name: str, adapter_id: str = None, function_name: str = None, direction: str = None) -> Optional[Dict[str, Any]]:
        """
        Load schema structure from schema_references/ folder.
        
        Args:
            schema_name: Name or filename of the schema (e.g., "jb-canonical-contact.xsd")
            adapter_id: Optional adapter ID for connector schemas (e.g., 'netsuite', 'salesforce')
            function_name: Optional function name for connector schemas (e.g., 'upsert', 'query')
            direction: Optional direction for connector schemas (e.g., 'input', 'output')
            
        Returns:
            Schema root structure or None if not found
        """
        # Check cache first
        cache_key = f"{schema_name}_{adapter_id}_{function_name}_{direction}"
        if cache_key in self.schema_references_cache:
            return self.schema_references_cache[cache_key]
        
        # Try to find matching reference file
        schema_refs_dir = Path(__file__).parent.parent.parent / 'schema_references'
        
        if not schema_refs_dir.exists():
            return None
        
        # For connector schemas, try to match by adapter + function + direction
        if adapter_id and direction:
            # Build pattern like "netsuite_Upsert_output" or "salesforce_Query_output"
            pattern = f"{adapter_id}_{function_name.capitalize() if function_name else '*'}_{direction}_*.json"
            matching_files = list(schema_refs_dir.glob(pattern))
            
            if matching_files:
                # Use the first matching file
                ref_path = matching_files[0]
                try:
                    with open(ref_path, 'r') as f:
                        schema_component = json.load(f)
                        if 'schemaTypeDocument' in schema_component and 'root' in schema_component['schemaTypeDocument']:
                            schema_root = schema_component['schemaTypeDocument']['root']
                            self.schema_references_cache[cache_key] = schema_root
                            print(f"         ✅ Matched connector schema by pattern: {ref_path.name}")
                            return schema_root
                except Exception as e:
                    print(f"       Warning: Error loading {ref_path}: {e}")
        
        # Clean schema name to match file
        clean_name = schema_name.replace('.xsd', '').replace('.json', '')
        
        # Try exact match for non-connector schemas
        possible_files = [
            f"{clean_name}.json",
            schema_name.replace('.xsd', '.json'),
        ]
        
        # Try to load matching file
        for possible_file in possible_files:
            if isinstance(possible_file, Path):
                ref_path = possible_file
            else:
                ref_path = schema_refs_dir / possible_file
                
            if ref_path.exists():
                try:
                    with open(ref_path, 'r') as f:
                        schema_component = json.load(f)
                        # Extract schemaTypeDocument.root from the component
                        if 'schemaTypeDocument' in schema_component and 'root' in schema_component['schemaTypeDocument']:
                            schema_root = schema_component['schemaTypeDocument']['root']
                            # Cache it
                            self.schema_references_cache[cache_key] = schema_root
                            return schema_root
                        else:
                            print(f"       Warning: {ref_path} missing schemaTypeDocument.root")
                except Exception as e:
                    print(f"       Warning: Error loading {ref_path}: {e}")
                    continue
        
        return None
    
    def _type_id_to_direction(self, type_id: int) -> str:
        """
        Map JPK type_id to schema direction for connector schemas.
        
        This is the authoritative mapping based on JPK semantics:
        - Input type_ids: These are schemas for data coming INTO the transformation
        - Output type_ids: These are schemas for data going OUT of the transformation
        
        Args:
            type_id: JPK type ID
            
        Returns:
            'input' or 'output'
        """
        # NetSuite type IDs
        if type_id == 101:  # NetSuite Request (sending TO NetSuite)
            return 'input'  # Schema for INPUT to transformation (becomes request)
        elif type_id == 102:  # NetSuite Response (receiving FROM NetSuite)
            return 'output'  # Schema for OUTPUT from transformation (becomes target)
        
        # Salesforce type IDs
        elif type_id == 14:  # Salesforce Query Response
            return 'output'  # Schema for OUTPUT from transformation
        
        # Default fallback
        return 'output'
    
    def _get_direction_from_transformations(self, schema_filename: str, transformations: List[Dict]) -> Optional[str]:
        """
        Get the correct direction for a schema by looking it up in transformations
        and mapping the JPK type_id to direction.
        
        Args:
            schema_filename: Schema filename to look up
            transformations: List of transformations from JPK
            
        Returns:
            'input' or 'output' or None if not found
        """
        if not transformations:
            return None
        
        for trans in transformations:
            # Check source
            source = trans.get('source', {})
            if source.get('schema') == schema_filename:
                type_id = source.get('type_id')
                if type_id:
                    direction = self._type_id_to_direction(type_id)
                    print(f"         🎯 Found schema in transformation source: type_id={type_id} → direction={direction}")
                    return direction
            
            # Check target
            target = trans.get('target', {})
            if target.get('schema') == schema_filename:
                type_id = target.get('type_id')
                if type_id:
                    direction = self._type_id_to_direction(type_id)
                    print(f"         🎯 Found schema in transformation target: type_id={type_id} → direction={direction}")
                    return direction
        
        return None
    
    def _is_connector_schema(self, schema_name: str) -> tuple:
        """
        Determine if schema is a connector schema and return adapter info.
        
        NOTE: Direction CAN be inferred from filename for NetSuite:
        - .request.xsd → input (type_id 101)
        - response or other → output (type_id 102)
        
        Args:
            schema_name: Schema name or filename
            
        Returns:
            Tuple of (is_connector, adapter_id, function_name, direction, operation_id)
        """
        import re
        name_lower = schema_name.lower()
        
        # Salesforce patterns
        if 'salesforce' in name_lower or name_lower.startswith('sf_'):
            return (True, 'salesforce', 'query', None, None)  # direction=None, will lookup from JPK
        
        # NetSuite patterns - extract operation ID from filename
        # Pattern: jitterbit.netsuite.{operation_id}.{function}_{object}.{suffix}.xsd
        netsuite_match = re.match(r'jitterbit\.netsuite\.([a-f0-9-]+)\.(\w+)_(\w+)\.([\w\.]+)\.xsd', name_lower)
        if netsuite_match:
            operation_id = netsuite_match.group(1)
            function_name = netsuite_match.group(2)
            suffix = netsuite_match.group(4)
            
            # Infer direction from filename suffix for NetSuite
            # request.xsd = input (type_id 101), response or other = output (type_id 102)
            direction = 'input' if 'request' in suffix.lower() else 'output'
            
            return (True, 'netsuite', function_name, direction, operation_id)
        
        # Not a connector schema
        return (False, None, None, None, None)
    
    def _extract_schema_name_from_transformations(self, schema_filename: str, transformations: List[Dict]) -> Optional[str]:
        """
        Extract the expected schema name from transformations that reference this schema.
        This ensures Type 900 schema names match what transformations are looking for.
        
        Args:
            schema_filename: The XSD filename to match
            transformations: List of Type 700 transformations
            
        Returns:
            The schema name as expected by transformations, or None if not found
        """
        if not transformations:
            return None
        
        for trans in transformations:
            # Check source
            source = trans.get('source', {})
            if source.get('schema') == schema_filename and 'name' in source:
                return source.get('name')
            
            # Check target
            target = trans.get('target', {})
            if target.get('schema') == schema_filename and 'name' in target:
                return target.get('name')
        
        return None
    
    def generate_schema_components(self, assets: List[Dict[str, Any]], jpk_path: str, transformations: List[Dict] = None, trace_logger: Optional[TraceLogger] = None) -> tuple:
        """
        Generate Schema Document Components (Type 900) for XSD assets.

        These components are required for XSD assets to be visible in Jitterbit interface.
        Each XSD asset needs a corresponding schema component that references it.

        Args:
            assets: List of XSD asset dictionaries
            jpk_path: Path to JPK file for reading XSD content
            transformations: Optional list of Type 700 transformations to extract embedded schemas from
            trace_logger: Optional trace logger for debugging

        Returns:
            Tuple of (schema_components list, origin_to_schema_map dict)
            - schema_components: List of schema component dictionaries (Type 900)
            - origin_to_schema_map: Dict mapping (origin_id, direction) to schema component for duplicate detection
        """
        print("   🔧 Generating Schema Document Components (Type 900) for XSD assets...")
        
        # Log schema generation start
        if trace_logger:
            trace_logger.log_decision("Generating schema components from XSD assets", {"asset_count": len(assets)})

        schema_components = []
        origin_to_schema_map: Dict[tuple, Dict[str, Any]] = {}  # Track origins for duplicate detection

        try:
            with zipfile.ZipFile(jpk_path, 'r') as jpk:
                for asset in assets:
                    asset_path = asset.get('path', '')
                    if not asset_path:
                        continue

                    # Find corresponding XSD file in JPK
                    xsd_filename = None
                    xsd_content = None

                    for file_info in jpk.filelist:
                        if file_info.filename.endswith('.xsd'):
                            # Match by filename (last part of path)
                            if asset_path.split('/')[-1] in file_info.filename:
                                xsd_filename = file_info.filename
                                try:
                                    xsd_content = jpk.read(file_info.filename).decode('utf-8')
                                except:
                                    xsd_content = None
                                break

                    # Extract schema filename
                    schema_filename = asset_path.split('/')[-1]
                    
                    # CRITICAL: Use the schema filename directly as the component name!
                    # This ensures Type 900 schema names EXACTLY match what transformations reference.
                    # For example: "jb-canonical-contact.xsd" not "Canonical Contact Schema"
                    component_name = schema_filename
                    
                    # Extract schema ID from transformations (uses JPK native IDs)
                    # Falls back to deterministic generation if not found
                    component_id = None
                    if transformations:
                        component_id = self._extract_schema_id_from_transformations(schema_filename, transformations)
                    
                    if not component_id:
                        # Fallback: generate deterministic ID for schemas not in transformations
                        component_id = self._generate_guid(f"schema_{schema_filename}")
                        print(f"         ⚙️ Generated fallback ID for {schema_filename}: {component_id[:8]}...")
                    
                    # Load schema structure - priority order:
                    # 1. From Type 700 transformations (most accurate - already parsed from JPK)
                    # 2. From schema_references/ (fallback for connectors or if not in transformations)
                    schema_structure = None
                    
                    # Determine if this is a connector schema first (needed for loading)
                    is_connector, adapter_id, function_name, direction, operation_id = self._is_connector_schema(schema_filename)
                    
                    # For connector schemas, get the CORRECT direction from JPK type_id
                    if is_connector and transformations:
                        jpk_direction = self._get_direction_from_transformations(schema_filename, transformations)
                        if jpk_direction:
                            direction = jpk_direction  # Use JPK type_id-based direction
                    
                    # Try extracting from transformations first
                    if transformations:
                        schema_structure = self._load_schema_from_transformations(schema_filename, transformations)
                    
                    # Fall back to schema_references/ if not found in transformations
                    if not schema_structure:
                        schema_structure = self._load_schema_structure(
                            schema_filename, 
                            adapter_id=adapter_id if is_connector else None,
                            function_name=function_name if is_connector else None,
                            direction=direction if is_connector else None
                        )
                        if schema_structure:
                            print(f"         ✅ Loaded schema structure from references for {schema_filename}")
                        else:
                            print(f"         ⚠️ No structure found for {schema_filename}")
                    
                    # Build schemaTypeDocument with root if structure available
                    schema_type_document = None
                    if schema_structure:
                        # Check if schema_structure is already a full document (has 'root' key)
                        # This happens for canonical/XSD schemas that include 'types' and 'O'
                        if isinstance(schema_structure, dict) and 'root' in schema_structure:
                            schema_type_document = schema_structure  # Already a full document
                        else:
                            schema_type_document = {
                                "root": schema_structure  # Wrap simple root structure
                            }
                    
                    # Build origin for connector schemas
                    origin = None
                    if is_connector:
                        # For connector schemas, extract origin info from Type 700 transformations
                        # This preserves JPK native call_id and direction from the transformation
                        origin_id = None
                        origin_direction = direction  # Default from filename parsing
                        
                        if transformations:
                            # Try to extract origin from transformations (has the real JPK call_id)
                            for trans in transformations:
                                source = trans.get('source', {})
                                target = trans.get('target', {})
                                
                                # Check if this transformation uses this schema
                                if (source.get('name') == schema_filename and source.get('origin')) or \
                                   (target.get('name') == schema_filename and target.get('origin')):
                                    # Found it - use the origin from Type 700
                                    schema_origin = source.get('origin') if source.get('name') == schema_filename else target.get('origin')
                                    origin_id = schema_origin.get('id')
                                    origin_direction = schema_origin.get('direction', direction)
                                    print(f"         🔗 Using origin from transformation: {origin_id[:8]}... (direction: {origin_direction})")
                                    break
                        
                        if not origin_id:
                            # Fallback: use operation_id from filename or generate UUID
                            origin_id = operation_id if operation_id else str(uuid.uuid4())
                            print(f"         🔗 Generated fallback origin ID: {origin_id[:8]}... (direction: {origin_direction})")
                        
                        origin = {
                            "adapterId": adapter_id,
                            "functionName": function_name,
                            "direction": origin_direction,
                            "id": origin_id
                        }

                    # Create schema component structure for user/XSD schemas
                    # Uses Jitterbit's standard format with filename, isCustom, format, etc.
                    # This format is required for Jitterbit to properly validate field paths
                    schema_component = {
                        "checksum": "1",
                        "type": COMPONENT_TYPES['SCHEMA'],  # Type 900
                        "name": component_name,
                        "id": component_id,
                        "filename": component_id,  # Use component ID as filename
                        "isCustom": True,  # XSD schemas are custom schemas
                        "format": "xml",  # XSD schemas are XML format
                        "metadataVersion": "3.0.1",
                        "validationState": 100,  # Valid state
                        "requiresDeploy": True,
                        "encryptedAtRest": True,
                        "chunks": 1,
                        "partial": False,
                        "displayName": component_name,  # Display name matches component name
                        "hidden": False
                    }
                    
                    # Add schemaTypeDocument if available (MUST have for viewer)
                    if schema_type_document:
                        # Filter out PRESCRIPT nodes from user/canonical schemas
                        schema_type_document = self._filter_prescript_nodes(schema_type_document)
                        schema_component["schemaTypeDocument"] = schema_type_document
                    
                    # Add origin for connector schemas
                    if origin:
                        schema_component["origin"] = origin
                        # Track origin for duplicate detection
                        origin_id_val = origin.get('id')
                        origin_direction_val = origin.get('direction')
                        if origin_id_val and origin_direction_val:
                            origin_to_schema_map[(origin_id_val, origin_direction_val)] = schema_component
                            # Log origin mapping
                            if trace_logger:
                                trace_logger.log_decision(f"Created schema component: {schema_component.get('name')}", {"origin_id": origin_id_val, "direction": origin_direction_val}, VerbosityLevel.DETAILED)
                                trace_logger.log_reasoning(f"Registered origin mapping: ({origin_id_val[:8]}..., {origin_direction_val})", {"schema_name": schema_component.get('name')}, VerbosityLevel.DEBUG)

                    schema_components.append(schema_component)

        except Exception as e:
            print(f"     Error generating schema components: {e}")

        print(f"   📊 Generated {len(schema_components)} Schema Document Components (Type 900)")
        print(f"   📊 Origin mapping contains {len(origin_to_schema_map)} entries for duplicate detection")
        return schema_components, origin_to_schema_map

    def _should_include_xsd_as_asset(self, filename: str, namespace: str) -> bool:
        """
        Generic rule for XSD inclusion - works for any JPK (from v321).

        Args:
            filename: XSD filename
            namespace: XML namespace from XSD

        Returns:
            True if XSD should be included as asset
        """
        filename_lower = filename.lower()
        namespace_lower = namespace.lower()

        # Include canonical schemas (needed for transformation field mappings)
        if filename_lower.startswith('jb-canonical'):
            return True

        # Include Jitterbit canonical schemas by namespace
        if 'jitterbit.com' in namespace_lower and 'canonical' in namespace_lower:
            return True

        # Include external connector schemas (any non-Jitterbit schema)
        if any(domain in namespace_lower for domain in ['.com', '.net', '.org']) and 'jitterbit' not in namespace_lower:
            return True

        # Include if filename suggests external connector
        external_indicators = ['connector', 'api', 'service', 'webservice']
        if any(indicator in filename_lower for indicator in external_indicators):
            return True

        return False

    def _generate_xsd_properties(self, namespace: str, file_size: int) -> List[Dict[str, str]]:
        """
        Generate properties for XSD asset based on namespace analysis (from v321).

        Args:
            namespace: XML namespace
            file_size: Size of XSD content in bytes

        Returns:
            List of property dictionaries
        """
        properties = [
            {"key": "IsTopLevel", "value": "0"},  # Default to 0
            {"key": "TargetNamespace", "value": namespace},
            {"key": "FileSize", "value": str(file_size)},
        ]

        # Add SchemaType based on namespace analysis (generic approach from v321)
        namespace_lower = namespace.lower()
        connectors = ['netsuite', 'salesforce', 'sap', 'oracle', 'workday', 'dynamics', 'servicenow']

        for connector in connectors:
            if connector in namespace_lower:
                properties.append({"key": "SchemaType", "value": connector})
                break
        else:
            properties.append({"key": "SchemaType", "value": "external"})

        return properties

    def _extract_human_readable_schema_name(self, jpk_path: str, xsd_filename: str, xsd_content: str) -> str:
        """
        Extract human-readable schema name from XSD content and filename.
        Simplified version that focuses on NetSuite and canonical schemas.
        """
        # Extract base filename
        base_filename = xsd_filename.split('/')[-1].replace('.xsd', '')
        
        # Handle canonical schemas first
        if 'jb-canonical' in base_filename:
            canonical_type = base_filename.replace('jb-canonical-', '').replace('jb-canonical', 'core')
            return f"Canonical {self._format_schema_name(canonical_type)} Schema"
        
        # Handle NetSuite schemas
        if 'jitterbit.' in base_filename and 'netsuite' in base_filename.lower():
            parts = base_filename.split('.')

            # Find operation part (e.g., upsert_Contact)
            operation_part = None
            for part in parts:
                if '_' in part and any(c.isupper() for c in part):
                    operation_part = part.replace('_', ' ').title()
                    break

            # Determine schema type
            schema_type = ""
            if 'request' in base_filename.lower():
                schema_type = " Request"
            elif 'response' in base_filename.lower():
                schema_type = " Response"
            else:
                # Use hash suffix for uniqueness (first 8 chars)
                hash_part = parts[-1][:8] if len(parts) > 4 else "Generic"
                schema_type = f" ({hash_part})"

            # Generate name
            if operation_part:
                return f"NetSuite {operation_part}{schema_type} Schema"
            else:
                return f"NetSuite{schema_type} Schema"
        
        # Handle Salesforce schemas
        if 'salesforce' in base_filename.lower():
            return "Salesforce Schema"
        
        # Generic fallback
        clean_name = base_filename.replace('jitterbit.', '').replace('.', ' ')
        return f"{self._format_schema_name(clean_name)} Schema"

    def _extract_connector_from_namespace(self, namespace: str) -> Optional[str]:
        """
        Extract connector name from namespace in a generic way (from v321).

        Args:
            namespace: XML namespace

        Returns:
            Connector name or None
        """
        if not namespace:
            return None

        namespace_lower = namespace.lower()

        # Common connector patterns from v321
        connectors = {
            'netsuite': 'NetSuite',
            'salesforce': 'Salesforce',
            'sap': 'SAP',
            'oracle': 'Oracle',
            'workday': 'Workday',
            'dynamics': 'Dynamics',
            'servicenow': 'ServiceNow',
            'hubspot': 'HubSpot',
            'zendesk': 'Zendesk'
        }

        for key, name in connectors.items():
            if key in namespace_lower:
                return name

        # Try to extract from domain
        domain_match = re.search(r'([a-zA-Z]+)\.(?:com|net|org)', namespace_lower)
        if domain_match:
            domain = domain_match.group(1)
            if domain not in ['www', 'api', 'webservices', 'platform']:
                return domain.title()

        return None

    def _format_schema_name(self, name: str) -> str:
        """Format a name for better readability (from v321)."""
        if not name:
            return "Unknown"

        # Convert various naming conventions to title case
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)  # camelCase
        name = re.sub(r'[_.-]', ' ', name)  # snake_case, kebab-case, dots
        name = ' '.join(word.capitalize() for word in name.split())

        # Remove common prefixes/suffixes
        name = re.sub(r'^Jitterbit\s+', '', name)
        name = re.sub(r'\s+Schema$', '', name)

        return name.strip()

    def validate_schema_component(self, component: Dict[str, Any]) -> bool:
        """
        Validate schema component structure.

        Args:
            component: Schema component dictionary to validate

        Returns:
            True if component is valid, False otherwise
        """
        if not isinstance(component, dict):
            return False

        # Check required fields
        required_fields = ['id', 'name', 'type', 'properties']
        for field in required_fields:
            if field not in component:
                return False

        # Check type is correct
        if component.get('type') != COMPONENT_TYPES['SCHEMA']:
            return False

        # Check properties structure
        properties = component.get('properties', {})
        required_props = ['SchemaPath', 'SchemaType', 'FileName']
        for prop in required_props:
            if prop not in properties:
                return False

        return True
