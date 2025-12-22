"""
Simple JPK Transformation Converter for J2J v327.

This module converts transformation data from JPK discovery format
to Jitterbit JSON format compatible with the transformation viewer.

PRINCIPLE FOR SCHEMA STORAGE:
- Connector schemas (Salesforce, NetSuite, etc.) → use origin reference (no embedded document)
- User/canonical schemas → embed document directly in transformation

Type ID to Adapter Mapping:
  14  → salesforce
  101 → netsuite (request)
  102 → netsuite (response)
  1,4 → user/canonical schema (no adapterId)
"""

import json
import re
import uuid
from typing import Dict, List, Any, Optional


class JPKTransformationConverter:
    """Converts JPK transformation data to Jitterbit JSON format."""
    
    def __init__(self):
        """Initialize the converter."""
        self.guid_cache = {}
        # Transformation context (set per-transformation for path translation decisions)
        self._current_source_root = None
        self._current_target_root = None
        self._current_salesforce_object_name = None
        # Import transformation rules
        from ..config.transformation_rules import (
            get_adapter_id, get_function_name, get_direction,
            is_flat_schema, get_schema_format, should_keep_numeric_segment,
            NAVIGATION_PREFIXES, COLLECTION_ROOTS, VARIABLE_REFERENCE_PATTERN,
            should_remove_source_origin, should_skip_precondition_generation,
            map_flat_schema_target_path, should_use_origin_reference,
            should_skip_root_translation, get_root_translation, SALESFORCE_ROOT_TRANSLATIONS,
            get_flat_schema_field_name, get_flat_schema_name, USE_JPK_FLAT_FIELD_NAMES
        )
        # Store rule functions as instance methods
        self._rule_get_adapter_id = get_adapter_id
        self._rule_get_function_name = get_function_name
        self._rule_get_direction = get_direction
        self._rule_is_flat_schema = is_flat_schema
        self._rule_get_schema_format = get_schema_format
        self._rule_should_keep_numeric_segment = should_keep_numeric_segment
        self._navigation_prefixes = NAVIGATION_PREFIXES
        self._collection_roots = COLLECTION_ROOTS
        self._variable_pattern = VARIABLE_REFERENCE_PATTERN
        self._rule_should_remove_source_origin = should_remove_source_origin
        self._rule_should_skip_precondition = should_skip_precondition_generation
        self._rule_map_flat_target_path = map_flat_schema_target_path
        self._rule_should_use_origin = should_use_origin_reference
        self._rule_should_skip_root_translation = should_skip_root_translation
        self._rule_get_root_translation = get_root_translation
        self._salesforce_root_translations = SALESFORCE_ROOT_TRANSLATIONS
        self._rule_get_flat_field_name = get_flat_schema_field_name
        self._rule_get_flat_schema_name = get_flat_schema_name
        self._use_jpk_flat_field_names = USE_JPK_FLAT_FIELD_NAMES

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

    def _get_adapter_id(self, type_id: str) -> Optional[str]:
        """
        Get adapterId from type_id if it's a connector schema.
        
        Args:
            type_id: The Jitterbit type ID from JPK
            
        Returns:
            adapterId if connector schema, None for user/canonical schemas
        """
        return self._rule_get_adapter_id(type_id)
    
    def convert_transformations_from_jpk_discovery(self, jpk_discovery_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert transformations from JPK discovery format to JSON format.
        
        Args:
            jpk_discovery_data: Data from jpk_discover_transformations.py
            
        Returns:
            List of transformation components in Jitterbit JSON format
        """
        transformations = []
        
        for jpk_transform in jpk_discovery_data.get('transformations', []):
            json_transform = self._convert_single_transformation(jpk_transform)
            transformations.append(json_transform)
        
        return transformations
    
    def _convert_single_transformation(self, jpk_transform: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a single transformation from JPK to JSON format."""

        name = jpk_transform['name']
        jpk_id = jpk_transform['id']

        # Set transformation context for path translation decisions
        # This context is used by _convert_path_notation to determine if root translation is needed
        source_info = jpk_transform.get('source', {})
        target_info = jpk_transform.get('target', {})
        self._current_source_root = source_info.get('root')  # e.g., "{namespace}Contacts" or "records"
        self._current_target_root = target_info.get('root')  # e.g., "{namespace}Contacts" or "upsertList"
        self._current_salesforce_object_name = source_info.get('salesforce_object_name')  # e.g., "Contact" or None

        # Generate new GUID (Jitterbit standard - IDs are regenerated)
        new_id = self._generate_guid(f"transform_{name}")

        # Convert source schema
        source = self._convert_schema(
            jpk_transform.get('source', {}),
            'source',
            transformation_name=name
        )

        # Convert target schema
        target = self._convert_schema(
            jpk_transform.get('target', {}),
            'target',
            transformation_name=name
        )

        # Convert mapping rules (pass target schema to detect flat schemas)
        # Extract flat_field_names from target schema for REQ-009
        target_jpk_schema = jpk_transform.get('target', {})
        flat_field_names = None
        if target_jpk_schema:
            field_structure = target_jpk_schema.get('field_structure', {})
            if field_structure.get('is_flat') and field_structure.get('flat_fields'):
                flat_field_names = field_structure.get('flat_fields')

        mapping_rules = self._convert_mapping_rules(
            jpk_transform.get('mappings', []),
            target_schema=target_jpk_schema,
            flat_field_names=flat_field_names
        )
        
        # Extract loop mapping rules from JPK mappings
        loop_mapping_rules = self._extract_loop_mapping_rules(
            jpk_transform.get('mappings', [])
        )
        
        return {
            'id': new_id,
            'name': name,
            'type': 700,
            'entityTypeId': '4',
            'checksum': '1',
            'requiresDeploy': True,
            'source': source,
            'target': target,
            'mappingRules': mapping_rules,
            'loopMappingRules': loop_mapping_rules,  # Integration Studio's getSourceMappedLoopPath expects this field
            'options': {},
            'description': None,
            'notes': [],
            'metadataVersion': '3.0.1',
            'chunks': 1,
            'partial': False,
            'encryptedAtRest': True,
            'duplicateNodesInfo': {
                'duplicatedNodes': {},
                'removedNodes': {}
            },
            'srcExtendedNodesInfo': {
                'extendedNodes': {},
                'removedNodes': {}
            },
            'tgtExtendedNodesInfo': {
                'extendedNodes': {},
                'removedNodes': {}
            },
            '_conversion_metadata': {
                'original_jpk_id': jpk_id,
                'source': 'jpk_discovery',
                'mapping_count': len(mapping_rules)
            }
        }
    
    def _convert_schema(self, jpk_schema: Dict[str, Any], schema_type: str, 
                       for_component: bool = False, transformation_name: str = None) -> Dict[str, Any]:
        """
        Convert JPK schema to JSON format.
        
        PRINCIPLE:
        - Connector schemas (type_id 14, 101, 102) → use origin, NO embedded document
        - User/canonical schemas (type_id 1, 4) → embed document, NO origin
        
        SCHEMA ID STRATEGY:
        - Use JPK native IDs when available (call_id for connectors, doc_id for user schemas)
        - Only generate deterministic IDs as fallback for canonical schemas
        
        Args:
            jpk_schema: Schema info from JPK discovery
            schema_type: 'source' or 'target'
            for_component: If True, creates a Type 900 schema component (includes id).
                          If False, creates inline transformation schema reference (no id for connectors)
            transformation_name: Name of the transformation (for reference file lookup)
            
        Returns:
            Schema dictionary in Jitterbit JSON format
        """
        if not jpk_schema:
            return None
        
        # Generate schema name
        schema_name = jpk_schema.get('schema', 'Unknown Schema')
        if not schema_name or schema_name == 'Unknown Schema':
            schema_name = f"{schema_type.capitalize()} Schema"
        
        # Get type_id and determine if connector schema
        type_id = jpk_schema.get('type_id')
        adapter_id = self._get_adapter_id(type_id)
        is_connector = adapter_id is not None
        
        # Generate schema ID using JPK native IDs when available
        # Priority: call_id (for connectors) > doc_id (for user schemas) > generated UUID (fallback)
        call_id = jpk_schema.get('call_id')
        doc_id = jpk_schema.get('doc_id')
        
        if call_id:
            # Connector schema - use call_id as the schema ID
            schema_id = call_id
        elif doc_id:
            # User/text schema - use doc_id from JPK
            schema_id = doc_id
        else:
            # Canonical schema without explicit ID - generate deterministic UUID
            schema_id = self._generate_guid(f"schema_{schema_name}")
        
        # Convert field structure to document format
        # PRINCIPLE: Only embed document for user/canonical schemas (NOT connectors)
        document = None
        nature = jpk_schema.get('nature', '')
        field_structure = jpk_schema.get('field_structure', {})
        
        # PRIORITY 0: Try transformation-specific reference files FIRST
        # These have complete structure with name, O, types - critical for validation
        jpk_root = jpk_schema.get('root', '')
        has_namespace_root = '}' in str(jpk_root)  # Namespace format: {http://...}ElementName

        # For canonical schemas (with namespace root), try to load canonical schema reference
        if has_namespace_root and not is_connector:
            from pathlib import Path
            schema_refs_dir = Path(__file__).parent.parent.parent / 'schema_references'
            if schema_refs_dir.exists():
                # Extract schema file name from JPK schema (e.g., 'jb-canonical-contact.xsd')
                target_xml = jpk_schema.get('schema', '')
                if target_xml:
                    # Try exact match first: jb-canonical-contact.json
                    schema_base = target_xml.replace('.xsd', '').replace('.xml', '')
                    ref_file = f"{schema_base}.json"
                    ref_path = schema_refs_dir / ref_file
                    if ref_path.exists():
                        try:
                            import json
                            with open(ref_path, 'r') as f:
                                ref_data = json.load(f)
                                if 'root' in ref_data:
                                    document = ref_data
                                    schema_name = ref_data.get('name', schema_base)
                                    print(f"         📋 Loaded canonical schema from reference: {ref_file}")
                        except Exception as e:
                            print(f"         ⚠️ Error loading canonical reference file {ref_path}: {e}")

        # For non-canonical schemas, try transformation-specific reference files
        if transformation_name and schema_type and not is_connector and not has_namespace_root and document is None:
            from pathlib import Path
            schema_refs_dir = Path(__file__).parent.parent.parent / 'schema_references'
            if schema_refs_dir.exists():
                trans_clean = transformation_name.replace(' ', '_').replace('-', '_')
                ref_file = f"{trans_clean}_{schema_type}_document.json"
                ref_path = schema_refs_dir / ref_file
                if ref_path.exists():
                    try:
                        import json
                        with open(ref_path, 'r') as f:
                            ref_data = json.load(f)
                            if 'root' in ref_data:
                                document = ref_data
                                # Update schema_name to match the reference file's name
                                if ref_data.get('name'):
                                    schema_name = ref_data['name']
                                print(f"         📋 Loaded inline document from reference: {ref_file}")
                    except Exception as e:
                        print(f"         ⚠️ Error loading reference file {ref_path}: {e}")
        
        # Only build document from JPK if not already loaded from reference file
        if not is_connector and document is None:
            # Check if this is a flat/text schema
            if nature == 'Flat':
                # Extract flat field names from JTR cache if available
                # JTR flat schemas have: field_structure = {'is_flat': True, 'flat_fields': ['response']}
                flat_field_names = None
                if field_structure and field_structure.get('is_flat'):
                    flat_field_names = field_structure.get('flat_fields', [])
                # Create special flat schema document structure with actual field names
                document = self._create_flat_schema_document(schema_name, flat_field_names)
            elif field_structure and field_structure.get('fields'):
                # Tree schema with fields
                root_fields = field_structure['fields']
                if root_fields:
                    # Find the root element
                    root_field = root_fields[0]
                    root_json = self._convert_field_to_json_notation(root_field, '')
                    
                    # Check if this is a Salesforce schema (has salesforce_object_name)
                    salesforce_object_name = jpk_schema.get('salesforce_object_name')
                    if salesforce_object_name:
                        # Salesforce embedded schema - add types, O, name
                        friendly_name = self._generate_salesforce_schema_name(salesforce_object_name, 'output')
                        document = {
                            'root': root_json,
                            'types': self._generate_salesforce_types(root_json, salesforce_object_name),
                            'O': self._generate_salesforce_document_options(),
                            'name': friendly_name
                        }
                        # Also update schema_name to use friendly name
                        schema_name = friendly_name
                    else:
                        # Standard embedded schema - just root
                        document = {
                            'root': root_json
                        }
        
        # PRINCIPLE: Connector schemas get origin, user schemas don't
        origin = None
        if is_connector:
            origin = self._create_origin(jpk_schema, adapter_id, schema_type)
            # For connector schemas, generate schema name following baseline pattern:
            # {adapter}_{Function}_{direction}_{origin_id} (function name is capitalized)
            if origin:
                function_name = origin.get('functionName', 'unknown')
                # CRITICAL: Capitalize function name to match baseline pattern (e.g., "Upsert" not "upsert")
                function_name_capitalized = function_name.capitalize() if function_name else 'unknown'
                direction = origin.get('direction', 'output')
                origin_id = origin.get('id', 'unknown')
                schema_name = f"{adapter_id}_{function_name_capitalized}_{direction}_{origin_id}"

        # RULE 26: Salesforce Request Transformation Document Embedding
        # For Salesforce Request transformations (type_id=12, direction='input'), the origin reference
        # cannot be resolved because there is no Type 500 Salesforce Update activity in the converted project.
        # Solution: Embed the document structure directly in the transformation target IN ADDITION to origin.
        # This allows the transformation to display its target schema without requiring a Type 500 activity.
        sf_request_embedded_document = None
        if type_id == '12' and schema_type == 'target':
            # Build document from JPK field_structure for Salesforce Request targets
            if field_structure and field_structure.get('fields'):
                root_fields = field_structure['fields']
                if root_fields:
                    root_field = root_fields[0]
                    root_json = self._convert_field_to_json_notation(root_field, '')
                    sf_request_embedded_document = {
                        'root': root_json
                    }
                    print(f"         📋 RULE 26: Embedded document in SF Request target (type_id=12)")

        # Build schema object following Schema Storage Rule:
        # CONNECTOR SCHEMAS (with origin):
        #   Schema Component (Type 900): id + name + origin (for_component=True)
        #   Transformation source: name + origin ONLY (for_component=False, no id for connectors)
        # USER/CANONICAL SCHEMAS (with document):
        #   Schema Component (Type 900): id + name + document (for_component=True)
        #   Transformation source: name + id (for_component=False)
        # SPECIAL CASE (Rule 26): Salesforce Request targets get BOTH origin AND document

        schema_dict = {
            'name': schema_name
        }

        # Only add 'id' if creating a Type 900 component, OR if it's a user schema
        # For connector schemas used in transformation source/target, NO id
        if for_component or origin is None:
            # Type 900 components always have id, user schemas always have id
            schema_dict['id'] = schema_id

        # Connector schemas: add origin (NOT document)
        if origin is not None:
            schema_dict['origin'] = origin
            # RULE 26: For Salesforce Request targets, also add document
            if sf_request_embedded_document is not None:
                sf_request_embedded_document = self._filter_prescript_nodes(sf_request_embedded_document)
                schema_dict['document'] = sf_request_embedded_document
        # User/canonical schemas: add document (NOT origin)
        elif document is not None:
            # Filter out PRESCRIPT nodes from embedded documents
            # /PRESCRIPT/ is a Design Studio marker that doesn't apply to Integration Studio
            document = self._filter_prescript_nodes(document)
            schema_dict['document'] = document

        return schema_dict
    
    def _create_flat_schema_document(self, schema_name: str, flat_field_names: List[str] = None) -> Dict[str, Any]:
        """
        Create document structure for flat/text schemas.

        Flat schemas have a special structure with a __flat__ root and minimal field structure.
        This matches how Jitterbit Integration Studio represents text/CSV/delimited schemas.

        Uses configurable rules from transformation_rules.py:
        - USE_JPK_FLAT_FIELD_NAMES: Whether to use actual JPK field names or defaults
        - get_flat_schema_field_name(): Returns field name based on rules
        - get_flat_schema_name(): Returns schema name based on rules

        Args:
            schema_name: Name of the schema (from JPK)
            flat_field_names: Optional list of field names extracted from JPK Document.

        Returns:
            Document structure for flat schema
        """
        # Use rule-based field name (either JPK field or default based on config)
        actual_field_name = self._rule_get_flat_field_name(flat_field_names)

        # Use rule-based schema name (either JPK name or default based on config)
        actual_schema_name = self._rule_get_flat_schema_name(schema_name)

        # Create single field structure (flat schemas typically have one field)
        children = [{
            'NIL': False,
            'MN': 0,
            'MX': 1,
            'N': actual_field_name,
            'T': 'string',
            'DV': '',
            'DT': '1',
            'BG': -1,
            'EN': -1,
            'I': 1,
            'L': 1
        }]

        return {
            'name': actual_schema_name,
            'root': {
                'N': '__flat__',
                'NS': '',
                'MN': 0,
                'MX': 'unbounded',
                'T': 'complex',
                'C': children,
                'I': 0,
                'L': 0
            },
            'O': {
                'customSchemaIsFlat': True,
                'isCustomSchema': True,
                'isFixedSchema': False,
                'delimiter': ',',
                'text_qualifier': '"',
                'qualifier_mode': 'WHEN_NEEDED',
                'use_end_of_line': True,
                'escape_sequences': True
            }
        }
    
    def _generate_salesforce_document_options(self) -> Dict[str, Any]:
        """
        Generate document options (O field) for Salesforce schemas.
        
        Returns:
            Document options dictionary matching baseline structure
        """
        return {
            'isCustomSchema': True,
            'customSchemaIsFlat': False,
            'customSchemaIsXml': True,
            'customSchemaIsFlatComplex': False
        }
    
    def _generate_salesforce_types(self, root: Dict[str, Any], object_name: str) -> List[Dict[str, Any]]:
        """
        Generate types array from root structure for Salesforce schemas.
        
        The types array mirrors the root structure with additional O metadata
        containing Salesforce object information.
        
        Args:
            root: The root schema structure (from document['root'])
            object_name: Salesforce object name (e.g., 'Contact')
            
        Returns:
            List of type definitions with O metadata
        """
        if not root or not object_name:
            return []
        
        # Generate type metadata for the main object
        type_entry = {
            'N': object_name,
            'O': {
                'label': object_name,
                'labelPlural': f"{object_name}s",
                'creatable': True,
                'custom': False,
                'deletable': True,
                'populated': True,
                'queryable': True,
                'updatable': True,
                'expandedName': f"{{urn:sobject.enterprise.soap.sforce.com}}{object_name}",
                'parents': [],
                'children': [],
                'relationships': []
            }
        }
        
        # Mirror children from root if present
        if 'C' in root:
            type_entry['C'] = root['C']
        
        return [type_entry]
    
    def _generate_salesforce_schema_name(self, object_name: str, direction: str = 'output') -> str:
        """
        Generate friendly schema name for Salesforce schemas.
        
        Args:
            object_name: Salesforce object name (e.g., 'Contact')
            direction: Schema direction ('input' or 'output')
            
        Returns:
            Friendly schema name (e.g., 'Salesforce Query Response Schema')
        """
        if direction == 'output':
            return "Salesforce Query Response Schema"
        else:
            return f"Salesforce {object_name} Schema"
    
    def _create_schema_document_from_fields(self, field_structure: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a schemaTypeDocument from a JPK field_structure.
        
        Used for creating Type 900 schemas from embedded connector field structures
        (e.g., Salesforce query responses) that don't have XSD files.
        
        Args:
            field_structure: JPK field_structure dict with 'fields' array
            
        Returns:
            Schema document with 'root' or None if conversion fails
        """
        fields = field_structure.get('fields', [])
        if not fields:
            return None
        
        # Get the root field (first field in the structure)
        root_field = fields[0]
        
        # Convert to JSON notation
        root_json = self._convert_field_to_json_notation(root_field, '')
        
        return {
            'root': root_json
        }
    
    def _convert_field_to_json_notation(self, jpk_field: Dict[str, Any], parent_path: str = '') -> Dict[str, Any]:
        """
        Convert JPK field structure to JSON document notation (N, MN, MX, C).
        
        Args:
            jpk_field: Field from JPK field_structure
            parent_path: Path of parent element (for context)
            
        Returns:
            Field in JSON document notation
        """
        # Extract field name
        name = jpk_field.get('name', '')
        # Build current path
        current_path = f"{parent_path}.{name}" if parent_path else name
        
        # CRITICAL: Use actual min_occurs/max_occurs from JTR XML if available
        # The JTR cache file contains the correct occurrence constraints in the XML attributes
        jtr_min_occurs = jpk_field.get('min_occurs')
        jtr_max_occurs = jpk_field.get('max_occurs')
        
        if jtr_min_occurs is not None or jtr_max_occurs is not None:
            # Use JTR values directly
            # JTR XML attributes are strings, so convert them
            # Convert None to appropriate defaults
            if jtr_min_occurs is not None:
                try:
                    # Handle both string and int (XML attributes are strings)
                    min_occurs = int(jtr_min_occurs) if isinstance(jtr_min_occurs, str) else int(jtr_min_occurs)
                except (ValueError, TypeError):
                    min_occurs = 0
            else:
                # Default min_occurs based on max_occurs
                # Check if max_occurs is unbounded (-1 or string "-1")
                if isinstance(jtr_max_occurs, str) and jtr_max_occurs == '-1':
                    max_val = -1
                else:
                    max_val = int(jtr_max_occurs) if isinstance(jtr_max_occurs, str) else jtr_max_occurs
                
                if max_val == -1:
                    # For unbounded arrays, check XSD pattern: typically minOccurs=1 for NetSuite operations
                    # But we can't access XSD here, so use 1 as default (matches baseline)
                    min_occurs = 1
                elif isinstance(max_val, int) and max_val > 1:
                    # For bounded arrays > 1, default to 0 (optional)
                    min_occurs = 0
                else:
                    # For single elements (max=1), default to 1 (required)
                    min_occurs = 1
            
            # Handle max_occurs: convert -1 to "unbounded" string to match baseline
            # JTR XML attributes are strings, so handle both string "-1" and int -1
            if isinstance(jtr_max_occurs, str) and jtr_max_occurs == '-1':
                max_occurs = 'unbounded'  # Baseline uses string "unbounded", not -1
            elif jtr_max_occurs == -1:
                max_occurs = 'unbounded'  # Baseline uses string "unbounded", not -1
            elif jtr_max_occurs is not None:
                try:
                    # Handle both string and int
                    max_occurs = int(jtr_max_occurs) if isinstance(jtr_max_occurs, str) else int(jtr_max_occurs)
                except (ValueError, TypeError):
                    max_occurs = 1
            else:
                max_occurs = 1
        else:
            # Fall back to type inference if JTR doesn't have occurrence info
            # HEURISTIC: For Salesforce query responses, elements under "records" are typically repeating
            # Check if this field is a direct child of "records" (Salesforce query response root)
            field_path = jpk_field.get('path', '') or current_path
            is_records_child = (
                (field_path.startswith('records.') and field_path.count('.') == 1) or
                (parent_path == 'records')
            )
            
            if is_records_child:
                # This is a direct child of "records" (e.g., "records.Contact")
                # Salesforce query responses return arrays, so these are typically repeating
                min_occurs = 1
                max_occurs = 'unbounded'
            else:
                # Use type inference for other cases
                type_code = jpk_field.get('type', '')
                min_occurs, max_occurs = self._infer_occurs_from_type(type_code)
        
        # Build JSON notation field
        json_field = {
            'N': name,
            'MN': min_occurs,
            'MX': max_occurs
        }
        
        # Add nullable flag if applicable
        if min_occurs == 0:
            json_field['NIL'] = True
        
        # Handle data type
        value_type = jpk_field.get('value_type')
        if value_type:
            json_field['T'] = self._map_value_type(value_type)
        
        # Recursively convert children
        children = jpk_field.get('children', [])
        if children:
            json_field['C'] = [
                self._convert_field_to_json_notation(child, current_path)
                for child in children
            ]
        
        # Add metadata options if available
        options = {}
        if name:
            options['label'] = self._generate_label(name)
        
        if options:
            json_field['O'] = options
        
        return json_field
    
    def _infer_occurs_from_type(self, type_code: str) -> tuple:
        """
        Infer min/max occurs from JPK type code.
        
        Args:
            type_code: JPK type code (e.g., '0x1', '0x9', '0x24')
            
        Returns:
            Tuple of (min_occurs, max_occurs)
        """
        type_mappings = {
            '0x1': (1, 1),           # Required single
            '0x9': (0, 'unbounded'), # Optional array
            '0x24': (0, 1),          # Optional single
            '0x21': (1, 1),          # Required single
        }
        
        return type_mappings.get(type_code, (0, 1))  # Default: optional single
    
    def _map_value_type(self, value_type: str) -> str:
        """Map JPK value type to JSON type."""
        type_map = {
            '8': 'string',
            '4': 'int',
            '5': 'double',
            '6': 'boolean',
            '7': 'date'
        }
        return type_map.get(str(value_type), 'string')
    
    def _generate_label(self, field_name: str) -> str:
        """Generate human-readable label from field name."""
        import re
        
        # Remove prefixes
        name = field_name.replace('typ', '').replace('xsi:', '')
        
        # CamelCase to spaces
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        
        # Underscores to spaces
        name = name.replace('_', ' ').replace('  ', ' ')
        name = name.replace('__c', '').strip()
        
        return name.title()
    
    def _create_origin(self, jpk_schema: Dict[str, Any], adapter_id: str, schema_type: str) -> Dict[str, Any]:
        """
        Create origin metadata for connector schemas.

        Args:
            jpk_schema: Schema info from JPK discovery
            adapter_id: The adapter ID (salesforce, netsuite, etc.)
            schema_type: 'source' or 'target'

        Returns:
            Origin metadata dict
        """
        schema_name = jpk_schema.get('schema', 'unknown')
        type_id = jpk_schema.get('type_id')

        # Determine function and direction based on adapter and type
        if adapter_id == 'salesforce':
            # Salesforce type handling:
            # - type_id=12: SOAP input (Request transformations) → direction='input'
            # - type_id=14: Query output (Response transformations) → direction='output'
            # CRITICAL: Use salesforce_function if available (set by discovery)
            # This distinguishes between query, update, insert, etc.
            function_name = jpk_schema.get('salesforce_function', 'query')

            # Use centralized direction from rules, which now includes type_id=12
            direction = self._rule_get_direction(type_id) or 'output'

            # For type_id=12 (Request), default function to 'update' if not set
            if type_id == '12' and function_name == 'query':
                function_name = 'update'  # Default for Request transformations
        elif adapter_id == 'netsuite':
            # NetSuite type 101 = request (input), type 102 = response (output)
            # CRITICAL FIX: Extract actual function from call_type, not just type_id
            # call_type examples: "NetSuiteQuery", "NetSuiteUpsert", etc.
            call_type = jpk_schema.get('call_type', '')

            # Extract function name from call_type (e.g., "NetSuiteQuery" → "query")
            if call_type:
                # Remove "NetSuite" prefix and lowercase
                function_name = call_type.replace('NetSuite', '').lower()
                if not function_name:
                    function_name = 'upsert'  # Default fallback
            else:
                # Fallback based on type_id when call_type not available
                function_name = 'upsert'

            # Direction based on type_id
            if type_id == '101':
                direction = 'input'
            else:  # type_id == '102'
                direction = 'output'
        else:
            function_name = 'unknown'
            direction = 'output'
        
        # Use call_id from JPK as the origin ID
        # This ensures consistency with the Type 500 business endpoint ID
        origin_id = jpk_schema.get('call_id', self._generate_guid(f"origin_{adapter_id}_{schema_name}"))
        
        origin_dict = {
            'adapterId': adapter_id,
            'functionName': function_name,
            'direction': direction,
            'id': origin_id
        }
        
        # CRITICAL: Add isConnectorFunction for NetSuite connector schemas (baseline pattern)
        # This field is present in baseline Response transformation source origin
        if adapter_id == 'netsuite' and function_name:
            origin_dict['isConnectorFunction'] = True
        
        return origin_dict
    
    def _infer_origin(self, jpk_schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """DEPRECATED: Use _create_origin instead."""
        # Keep for backwards compatibility but this should no longer be called
        return None

    def _is_complex_element(self, document: Dict[str, Any], target_path: str) -> bool:
        """
        Check if a target path refers to a complex element (has children).

        When mapping to canonical/XSD schemas, we need to skip mappings that target
        complex elements directly. Only leaf nodes (no children or empty C array)
        should have direct value mappings.

        Args:
            document: Target document structure with 'root' key
            target_path: Slash-separated path like 'Contacts/Contact/ID/typID'

        Returns:
            True if the path refers to a complex element with children
        """
        if not document or 'root' not in document:
            return False

        # Parse the path
        parts = target_path.split('/') if target_path else []
        if not parts:
            return False

        # Navigate through the document structure
        current = document.get('root', {})

        # First part should match the root element name
        if parts[0] != current.get('N'):
            return False

        # Navigate through remaining path parts
        for part in parts[1:]:
            children = current.get('C', [])
            found = False
            for child in children:
                if child.get('N') == part:
                    current = child
                    found = True
                    break
            if not found:
                # Path not found - return False (not complex, just doesn't exist)
                return False

        # Check if current node has non-empty children
        children = current.get('C', [])
        return len(children) > 0

    def _convert_mapping_rules(self, jpk_mappings: List[Dict[str, Any]], target_schema: Dict[str, Any] = None, flat_field_names: List[str] = None) -> List[Dict[str, Any]]:
        """
        Convert JPK mapping rules to JSON format with intermediate preconditions.

        This method:
        1. Converts all JPK mappings to JSON format
        2. Identifies existing preconditions from JPK
        3. Generates intermediate preconditions for parent paths
        4. Combines them in correct order (preconditions first, then field mappings)

        Args:
            jpk_mappings: List of mappings from JPK discovery
            target_schema: Target schema info (to detect flat schemas)
            flat_field_names: List of flat field names from JPK Document (for REQ-009)

        Returns:
            List of mapping rules in Jitterbit JSON format
        """
        # Step 1: Convert all JPK mappings to JSON rules
        converted_rules = []
        existing_precond_paths = set()

        # Check if target is a flat schema
        # Use rule-based flat schema detection
        is_flat_schema = self._rule_is_flat_schema(target_schema) if target_schema else False

        # Load target document for canonical schema validation
        # Canonical schemas use XSD files and may have complex elements that can't accept direct value mappings
        target_document = None
        if target_schema:
            target_root = target_schema.get('root', '')
            # Check if this is a canonical schema (namespace root)
            if target_root and target_root.startswith('{') and '}' in target_root:
                # Try to load canonical schema from reference file
                from pathlib import Path
                schema_refs_dir = Path(__file__).parent.parent.parent / 'schema_references'
                target_xml = target_schema.get('schema', '')
                if target_xml and schema_refs_dir.exists():
                    schema_base = target_xml.replace('.xsd', '').replace('.xml', '')
                    ref_file = f"{schema_base}.json"
                    ref_path = schema_refs_dir / ref_file
                    if ref_path.exists():
                        try:
                            import json as json_module
                            with open(ref_path, 'r') as f:
                                target_document = json_module.load(f)
                        except Exception:
                            pass

        for jpk_mapping in jpk_mappings:
            json_rule = self._convert_single_mapping(jpk_mapping, is_flat_schema=is_flat_schema, flat_field_names=flat_field_names)
            # Skip None rules (empty target_path "[]" mappings)
            if json_rule is None:
                continue

            # CRITICAL: Skip mappings that target complex elements (non-leaf nodes)
            # These mappings would fail in Integration Studio with "non-existent target field" error
            if target_document and not json_rule.get('isPreconditionScript'):
                target_path = json_rule.get('targetPath', '')
                if target_path and self._is_complex_element(target_document, target_path):
                    print(f"         ⚠️ Skipping mapping to complex element: {target_path}")
                    continue

            converted_rules.append(json_rule)
            
            # Track existing precondition paths to avoid duplicates
            if json_rule.get('isPreconditionScript'):
                existing_precond_paths.add(json_rule.get('targetPath', ''))
        
        # Step 2: Separate existing preconditions from field mappings
        existing_preconditions = [r for r in converted_rules if r.get('isPreconditionScript')]
        field_mappings = [r for r in converted_rules if not r.get('isPreconditionScript')]
        
        # Step 3: Generate intermediate preconditions from field mappings
        # These are the preconditions for parent paths that are NOT already covered
        # CRITICAL: Skip precondition generation for flat schemas (using rule)
        # Flat schemas don't need structure preconditions
        # Pass is_flat_schema flag to the rule function
        should_skip = self._rule_should_skip_precondition(field_mappings) if field_mappings else False
        if not should_skip:
            intermediate_preconditions = self._generate_intermediate_preconditions(
                field_mappings, 
                existing_precond_paths
            )
        else:
            intermediate_preconditions = []
        
        # Step 4: Combine all preconditions (existing + intermediate) and sort by depth
        all_preconditions = existing_preconditions + intermediate_preconditions
        all_preconditions.sort(key=lambda r: r.get('targetPath', '').count('/'))
        
        # Step 5: Final result: preconditions first (sorted by depth), then field mappings
        final_rules = all_preconditions + field_mappings
        
        return final_rules
    
    def _extract_loop_mapping_rules(self, jpk_mappings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract loop mapping rules from JPK mappings.
        
        Loop patterns are indicated by target_path ending with '.]' which signals
        a repeating/looping structure in the schema. This method detects such patterns
        and generates the loopMappingRules array that Integration Studio expects.
        
        The main loop is typically the one with the shortest path depth (highest in hierarchy),
        not the first one encountered.
        
        Args:
            jpk_mappings: List of mappings from JPK discovery
            
        Returns:
            List of loop mapping rules, or empty list if no loops detected
        """
        if not jpk_mappings:
            return []
        
        # Collect all loop patterns found in mappings
        loop_candidates = []
        
        # Scan through mappings to find loop patterns
        for jpk_mapping in jpk_mappings:
            target_path_raw = jpk_mapping.get('target_path', '')
            source_expression = jpk_mapping.get('source_expression', '')
            
            # Check if this mapping has a loop pattern (ends with '.]')
            if target_path_raw.endswith('.]'):
                # Extract the loop path by removing the brackets
                tgt_loop_path_candidate = target_path_raw.strip('[]')
                src_loop_path_candidate = source_expression.strip('[]')
                
                # Count depth by number of $ symbols to find the top-level loop
                tgt_depth = tgt_loop_path_candidate.count('$')
                
                loop_candidates.append({
                    'tgt_loop': tgt_loop_path_candidate,
                    'src_loop': src_loop_path_candidate,
                    'tgt_depth': tgt_depth
                })
        
        # No loop patterns found
        if not loop_candidates:
            return []
        
        # Find the shallowest target loop (top-level, not nested)
        # Sort by depth and take the first one (shallowest)
        main_loop = min(loop_candidates, key=lambda x: x['tgt_depth'])
        
        tgt_loop_path = main_loop['tgt_loop']
        src_loop_path = main_loop['src_loop']
        
        # Generate the path versions (replace $ with /)
        # Remove trailing dot for path version
        tgt_path = tgt_loop_path.rstrip('.').replace('$', '/')

        # CRITICAL FIX: Apply root translation to target loop paths
        # This ensures canonical schema roots (like "Contacts") are translated to runtime roots (like "records")
        # when the target schema is Salesforce-origin
        # Check if translation should be applied based on target schema root
        skip_translation = self._rule_should_skip_root_translation(
            self._current_target_root,
            self._current_salesforce_object_name
        )

        if not skip_translation:
            # Apply translation to tgtLoopPath and tgtPath
            for canonical, runtime in self._salesforce_root_translations.items():
                canonical_loop = f"{canonical}$"
                runtime_loop = f"{runtime}$"
                if tgt_loop_path.startswith(canonical_loop):
                    tgt_loop_path = runtime_loop + tgt_loop_path[len(canonical_loop):]

                if tgt_path.startswith(f"{canonical}/"):
                    tgt_path = f"{runtime}/" + tgt_path[len(canonical)+1:]

        # CRITICAL FIX: srcPath should be empty string to match baseline pattern
        # The source loop path is already in srcLoopPath; srcPath being empty is expected
        src_path = ''  # Baseline pattern: srcPath is always empty

        return [
            {
                'srcLoopPath': src_loop_path,
                'tgtLoopPath': tgt_loop_path,
                'srcPath': src_path,
                'tgtPath': tgt_path or ''
            }
        ]
    
    def _convert_single_mapping(self, jpk_mapping: Dict[str, Any], is_flat_schema: bool = False, flat_field_names: List[str] = None) -> Optional[Dict[str, Any]]:
        """
        Convert a single JPK mapping to JSON format.

        CRITICAL FIXES for Response transformation:
        1. Skip empty target_path "[]" (return None)
        2. Map "data" → "__flat__/{actual_field}" for flat schemas (using rules)
        3. Extract srcPaths from transformScript content (when has_script=True)
        4. Preserve full transformScript from JPK (not just field reference)

        Args:
            jpk_mapping: Single mapping from JPK discovery
            is_flat_schema: True if target is a flat schema (affects targetPath mapping)
            flat_field_names: List of flat field names from JPK Document (for REQ-009)

        Returns:
            Mapping rule dictionary, or None if mapping should be skipped
        """
        target_path_raw = jpk_mapping.get('target_path', '')
        source_expression = jpk_mapping.get('source_expression', '')
        has_script = jpk_mapping.get('has_transformation_script', False)
        
        # CRITICAL FIX 1: Skip empty target_path "[]" (loop mappings without target)
        cleaned_target = target_path_raw.strip().strip('[]').strip()
        if not cleaned_target:
            # Empty target_path indicates a loop mapping without explicit target
            # These should be handled by loopMappingRules, not mappingRules
            return None
        
        # CRITICAL FIX 2: Map "data" → "__flat__/{actual_field}" for flat schemas (using rule)
        # Pass flat_field_names to use actual JPK field names when USE_JPK_FLAT_FIELD_NAMES=True
        if is_flat_schema:
            mapped_target = self._rule_map_flat_target_path(cleaned_target, flat_field_names)
            if mapped_target != cleaned_target:
                target_path_raw = mapped_target
                cleaned_target = mapped_target
        
        # Detect if this is a precondition (structure setup)
        is_precondition = self._is_precondition(target_path_raw)
        
        # Convert target path from JPK format to JSON format
        # CRITICAL: Pass for_target=True to check TARGET schema root for namespace detection
        target_path = self._convert_path_notation(target_path_raw, for_target=True)

        # CRITICAL FIX: Handle /PRESCRIPT/ paths from Design Studio
        # /PRESCRIPT/ is a Design Studio marker for pre-transformation scripts
        # In Integration Studio, these become preconditions targeting the parent path
        # e.g., "invoices//PRESCRIPT/" → precondition for "invoices" root
        if '/PRESCRIPT/' in target_path or '/PRESCRIPT' in target_path:
            # Strip the PRESCRIPT part - target the parent element
            target_path = re.sub(r'//PRESCRIPT/?$', '', target_path)
            target_path = re.sub(r'/PRESCRIPT/?$', '', target_path)
            # If the script has actual content (not just structure), it becomes a precondition script
            if has_script and source_expression.strip():
                is_precondition = True

        # targetScript should NOT have brackets - strip them
        # Also translate canonical root to runtime root
        # CRITICAL FIX: For flat schemas, targetScript should be just the field name (e.g., "field")
        # not the full path (e.g., "__flat__/field"). This is how baseline handles flat schema scripts.
        if is_flat_schema and target_path.startswith('__flat__/'):
            # Extract just the field name after __flat__/
            target_script = target_path.replace('__flat__/', '')
        else:
            # CRITICAL: Pass for_target=True since this is for the target path
            # Also strip PRESCRIPT from targetScript
            script_raw = target_path_raw.strip('[]')
            script_raw = re.sub(r'\$?/PRESCRIPT/?$', '$', script_raw)
            target_script = self._translate_jpk_root(script_raw, for_target=True)
        
        # CRITICAL FIX 3 & 4: For mappings with scripts, preserve full script and extract srcPaths from it
        if has_script:
            # Preserve the full transformScript from JPK (source_expression contains the full script)
            # Remove <trans> tags if present (we'll add them back)
            script_content = source_expression.strip()
            if script_content.startswith('<trans>'):
                script_content = script_content[7:]  # Remove '<trans>'
            if script_content.endswith('</trans>'):
                script_content = script_content[:-8]  # Remove '</trans>'
            script_content = script_content.strip()
            
            # Format with <trans> tags
            transform_script = self._format_transform_script(script_content)
            
            # Extract srcPaths from the script content
            # First try jbroot$ patterns (for Response transformations)
            source_paths = self._extract_srcpaths_from_script(script_content)
            
            # If no jbroot$ patterns found, try extracting from the script as a regular expression
            # This handles cases like records$Contact.FirstName$ (Salesforce/NetSuite Request)
            if not source_paths:
                # Extract source paths from the script content using the regular extraction method
                # This will handle records$Contact... patterns
                source_paths = self._extract_source_paths(script_content)
            
            # If source_paths is empty (variable reference or unmapped), set to None
            if not source_paths:
                source_paths = None
        else:
            # No script - extract source paths from expression
            if is_precondition:
                source_paths = None  # Preconditions define structure, not field mappings
            else:
                source_paths = self._extract_source_paths(source_expression)
                # If source_paths is empty (variable reference or unmapped), set to None
                if not source_paths:
                    source_paths = None
            
            # No transformScript for non-script mappings
            transform_script = ''
        
        # Build mapping rule
        rule = {
            'customValuePaths': [],
            'globalVariables': [],
            'isPreconditionScript': is_precondition,
            'targetPath': target_path,
            'targetScript': target_script,
            'transformScript': transform_script,
            'validationErrors': [],
            'transformScriptCleansed': transform_script,  # Same as transformScript for now
            'srcPaths': source_paths
        }
        
        # CRITICAL: For script-based transformations, add cursor and transformScriptError fields
        # Baseline pattern: script-based mappings have cursor and transformScriptError fields
        if has_script:
            rule['cursor'] = {
                'line': 34,  # Default cursor position (baseline pattern)
                'ch': 9,
                'sticky': None
            }
            rule['transformScriptError'] = ''  # Empty string if no errors
        
        return rule
    
    def _is_precondition(self, target_path: str) -> bool:
        """Determine if a mapping rule is a precondition."""
        # Preconditions typically end with . instead of field name
        cleaned = target_path.strip().strip('[]')
        return cleaned.endswith('.')
    
    def _convert_path_notation(self, jpk_path: str, for_target: bool = False) -> str:
        """
        Convert JPK path notation to JSON notation.

        JPK uses canonical schema paths (e.g., Contacts/Contact/...) but Integration Studio
        uses runtime schema paths (e.g., records/Contact/...). This function handles the translation.

        JPK: [Contacts$Contact.FirstName$]
        JSON: records/Contact/FirstName (for Salesforce-origin schemas)
        JSON: Contacts/Contact/FirstName (for true canonical schemas with namespace)

        ROOT TRANSLATION RULES (JPK-driven):
        - For SOURCE paths: Check source schema root for namespace → SKIP if has namespace
        - For TARGET paths: Check target schema root for namespace → SKIP if has namespace
        - If salesforce_object_name is detected → APPLY translation (Salesforce-origin)
        - Default: No translation needed

        Args:
            jpk_path: The JPK path notation to convert
            for_target: If True, this is a target path (check target root for namespace)
                       If False, this is a source path (check source root for namespace)

        This mapping is determined by analyzing JPK properties (sourcedtd_root/targetdtd_root)
        to understand whether the schema is a true canonical schema or a Salesforce-origin schema.
        """
        # Remove brackets
        path = jpk_path.strip().strip('[]')

        # Remove trailing . or $
        path = path.rstrip('.$')

        # Replace $ with /
        path = path.replace('$', '/')

        # Replace . with /
        path = path.replace('.', '/')

        # NOTE: Double slashes can occur when:
        # - JPK has paths like "invoices$/PRESCRIPT/" where /PRESCRIPT/ starts with /
        # - After replacing $ with /, we get "invoices//PRESCRIPT/"
        # HOWEVER, we should NOT clean these slashes because /PRESCRIPT/ is a literal field name
        # containing slashes. Integration Studio expects the path to include these slashes.
        # Only clean truly redundant slashes (3+ consecutive slashes to 2)
        if '///' in path:
            path = re.sub(r'//{3,}', '//', path)

        # Apply canonical → runtime schema root translation ONLY for Salesforce-origin schemas
        # Use JPK-driven rule to determine if translation should be skipped
        # CRITICAL: For target paths, check the TARGET schema root, not the source
        schema_root = self._current_target_root if for_target else self._current_source_root
        skip_translation = self._rule_should_skip_root_translation(
            schema_root,
            self._current_salesforce_object_name
        )

        if not skip_translation:
            # Only apply translation for Salesforce-origin schemas
            segments = path.split('/')
            if segments and segments[0] in self._salesforce_root_translations:
                segments[0] = self._salesforce_root_translations[segments[0]]
                path = '/'.join(segments)

        return path
    
    def _translate_jpk_root(self, jpk_script: str, for_target: bool = False) -> str:
        """
        Translate canonical schema root in JPK notation to runtime schema root.

        Example (for Salesforce-origin schemas):
            Contacts$Contact.FirstName$ → records$Contact.FirstName$

        Example (for true canonical schemas with namespace):
            Contacts$Contact.FirstName$ → Contacts$Contact.FirstName$ (no translation)

        Args:
            jpk_script: The JPK script/path notation to translate
            for_target: If True, this is for a target path (check target root)
                       If False, this is for a source path (check source root)
        """
        # Check if translation should be skipped (for true canonical schemas with namespace)
        # CRITICAL: For target paths, check the TARGET schema root, not the source
        schema_root = self._current_target_root if for_target else self._current_source_root
        skip_translation = self._rule_should_skip_root_translation(
            schema_root,
            self._current_salesforce_object_name
        )

        if skip_translation:
            return jpk_script

        # Canonical → Runtime root mapping (only for Salesforce-origin schemas)
        CANONICAL_TO_RUNTIME = {
            'Contacts$': 'records$',
            'Contacts.': 'records.',
        }

        for canonical, runtime in CANONICAL_TO_RUNTIME.items():
            if jpk_script.startswith(canonical):
                return runtime + jpk_script[len(canonical):]

        return jpk_script
    
    def _extract_srcpaths_from_script(self, script_content: str) -> List[str]:
        """
        Extract srcPaths from transformScript content by finding all jbroot$... paths.
        
        For Response transformation, the script contains references like:
        - jbroot$jbresponse$upsertListResponse$writeResponseList$writeResponse#.status$isSuccess
        - jbroot$jbresponse$upsertListResponse$writeResponseList$writeResponse#.baseRef$1$RecordRef$externalId
        
        These need to be converted to schema-relative paths:
        - jbroot/jbresponse/upsertListResponse/writeResponseList/writeResponse/status/isSuccess
        - jbroot/jbresponse/upsertListResponse/writeResponseList/writeResponse/baseRef/1/RecordRef/externalId
        
        Args:
            script_content: The transformScript content (without <trans> tags)
            
        Returns:
            List of unique source schema field paths
        """
        import re
        
        if not script_content:
            return []
        
        # Find all jbroot$... paths in the script
        # Pattern: jbroot$ followed by field path segments separated by $ or .
        # Also handle #. for array access
        pattern = r'jbroot\$[^\s\)\;\+\=]+'
        matches = re.findall(pattern, script_content)
        
        if not matches:
            return []
        
        # Convert each match to schema-relative path
        src_paths = []
        for match in matches:
            # Remove jbroot$ prefix
            path = match.replace('jbroot$', '')
            
            # Replace $ and . with /
            path = path.replace('$', '/')
            path = path.replace('.', '/')
            
            # Handle #. array access notation (replace # with /)
            path = path.replace('#/', '/')
            path = path.replace('#', '/')
            
            # Remove trailing / if present
            path = path.rstrip('/')
            
            # CRITICAL FIX: Filter out numeric segments that are array indices
            # CRITICAL FIX: Filter out numeric segments that are array indices
            # Rule-based heuristic: Keep numeric segments when they appear between field names that form
            # a compound schema structure (e.g., baseRef/1/RecordRef where 1 is part of schema path).
            # Remove numeric segments when they appear as standalone array indices (e.g., statusDetail/1/message).
            # Heuristic: If numeric segment is followed by a capitalized field name, it's likely part of schema structure.
            # If numeric segment is followed by a lowercase field name or end of path, it's likely an array index.
            path_segments = path.split('/')
            filtered_segments = []
            for i, seg in enumerate(path_segments):
                if not seg:
                    continue
                if seg.isdigit():
                    # Use rule-based heuristic to determine if numeric segment should be kept
                    next_seg = path_segments[i + 1] if i + 1 < len(path_segments) else None
                    if self._rule_should_keep_numeric_segment(seg, next_seg):
                        filtered_segments.append(seg)
                    # Otherwise, it's an array index - skip it
                else:
                    filtered_segments.append(seg)
            path = '/'.join(filtered_segments)
            
            if path:
                # Convert to proper path format (jbroot/...)
                full_path = f'jbroot/{path}'
                if full_path not in src_paths:
                    src_paths.append(full_path)
        
        return src_paths if src_paths else None
    
    def _extract_source_paths(self, expression: str) -> List[str]:
        """
        Extract source schema field paths from transformation expression.
        
        CRITICAL: The srcPaths format depends on the expression structure:
        - WITH navigation prefix (root$transaction...): strip navigation INCLUDING 'records'
        - WITHOUT navigation prefix (records$Contact...): keep 'records' as schema root
        
        CRITICAL: Variable references (e.g., $VariableName$) should return empty list
        so that srcPaths can be set to None for unmapped fields that use variables.
        
        Examples:
        - Input: [root$transaction.response$body$queryResponse$result$records.Contact$Id$]
          Output: ['Contact/Id'] (NetSuite source - 'records' is navigation)
        
        - Input: [records$Contact.Id$]
          Output: ['records/Contact/Id'] (Salesforce source - 'records' is schema root)
        
        - Input: [$NetSuite_Subsidiary_Id$]
          Output: [] (variable reference - no source path)
        
        Args:
            expression: Source expression from JPK mapping
            
        Returns:
            List of source schema field paths (empty list for variable references)
        """
        import re
        
        if not expression:
            return []
        
        # Remove surrounding brackets
        expr = expression.strip().strip('[]').strip()
        
        # CRITICAL FIX: Detect variable references FIRST, before any processing
        # Use centralized variable pattern from rules
        # Check the full expression first
        if re.match(self._variable_pattern, expr):
            return []

        # CRITICAL FIX: Detect literal string constants (quoted strings)
        # Expressions like "Id" or "Email" are constant values, not source field references
        # These should return empty list so srcPaths is set to None
        if expr.startswith('"') and expr.endswith('"'):
            return []

        # CRITICAL FIX: Detect boolean/constant literals
        # Salesforce wizard mappings often use "true" or "false" as constant values
        # These should NOT be treated as source field paths
        # For multi-line scripts, check if the last non-empty line is a constant value
        lines = [line.strip() for line in expr.split('\n') if line.strip() and not line.strip().startswith('//')]
        if lines:
            last_line = lines[-1].lower()
            # Boolean literals
            if last_line in ('true', 'false', 'null'):
                return []
            # Numeric literals (integer or decimal)
            if re.match(r'^-?\d+\.?\d*$', last_line):
                return []
            # CRITICAL FIX: Detect local variable references
            # Patterns like "sfId;" or "varName;" are local variable references, not source paths
            # Local vars: simple identifier followed by optional semicolon
            if re.match(r'^[a-z][a-zA-Z0-9_]*;?$', last_line):
                return []

        # CRITICAL FIX: If expression starts with // it's a comment, not a path
        # This handles cases like "//searchResponse$searchResult$..." which is commented out
        if expr.strip().startswith('//'):
            return []

        # Split on spaces to separate navigation prefix from source reference
        parts = expr.split()
        
        if not parts:
            return []
        
        # The last part (or only part) should be the source schema reference
        source_part = parts[-1] if len(parts) > 1 else parts[0]
        source_part = source_part.strip()
        
        # Check if source_part is a variable reference (starts and ends with $)
        # Also check if it's just a variable name without $ delimiters but matches variable pattern
        if re.match(self._variable_pattern, source_part):
            return []
        
        # Additional check: if source_part starts and ends with $ and has no field separators
        if source_part.startswith('$') and source_part.endswith('$') and '$' not in source_part[1:-1]:
            # This is a simple variable reference like $VariableName$
            return []
        
        # Remove trailing . or $
        source_part = source_part.rstrip('.$')
        
        # CRITICAL FIX: Split on $, ., and # (array index marker)
        # This handles patterns like statusDetail#1.message where #1 is an array index
        segments = re.split(r'[\$\.#]', source_part)
        
        # Filter out empty segments
        segments = [s for s in segments if s]
        
        if not segments:
            return []
        
        # Determine if expression has full navigation path
        # Navigation flow: root → transaction → response → body → queryResponse → result
        has_navigation = segments[0].lower() == 'root'
        
        if has_navigation:
            # WITH navigation prefix: strip all navigation INCLUDING 'records'
            # Use centralized navigation prefixes and collection roots from rules
            full_nav_prefixes = self._navigation_prefixes + self._collection_roots
            
            schema_start_idx = 0
            for i, seg in enumerate(segments):
                if seg.lower() not in full_nav_prefixes:
                    schema_start_idx = i
                    break
                schema_start_idx = i + 1
        else:
            # WITHOUT navigation prefix: keep everything (schema root like 'records' preserved)
            # Only strip true navigation prefixes (rarely present without 'root')
            minimal_nav_prefixes = ['root', 'transaction', 'response', 'body', 'queryresponse', 'result']
            
            schema_start_idx = 0
            for i, seg in enumerate(segments):
                if seg.lower() not in minimal_nav_prefixes:
                    schema_start_idx = i
                    break
                schema_start_idx = i + 1
        
        # Get the schema portion
        schema_segments = segments[schema_start_idx:]
        
        if not schema_segments:
            return []
        
        # CRITICAL FIX: If we only have one segment and it looks like a variable name
        # (starts with capital letter, contains underscores, no slashes), it's likely a variable
        if len(schema_segments) == 1:
            single_segment = schema_segments[0]
            # Variable names typically: start with capital, have underscores, match pattern like NetSuite_Subsidiary_Id
            if (single_segment and 
                single_segment[0].isupper() and 
                '_' in single_segment and
                re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', single_segment)):
                # This looks like a variable name, not a source field path
                return []
        
        # CRITICAL FIX: Filter out numeric-only segments (array indices like '1' in statusDetail#1.message)
        # These should not appear in srcPaths (reference pattern: /status/statusDetail/message, not /status/statusDetail/1/message)
        # Array indices appear as standalone numeric segments between field names
        filtered_segments = []
        for i, seg in enumerate(schema_segments):
            # Skip pure numeric segments that are array indices
            # These are typically single-digit numbers (0-9) or short numbers (10-999) between field names
            if seg.isdigit():
                # Check if this looks like an array index (not part of a field name)
                # Array indices are typically: single digits, or appear between field names
                # Keep it only if it's part of a compound field name (unlikely for pure digits)
                continue  # Skip all numeric segments - they're array indices
            else:
                filtered_segments.append(seg)
        
        # Convert to path format
        schema_path = '/'.join(filtered_segments)
        
        return [schema_path] if schema_path else []
    
    def _extract_field_reference(self, expression: str) -> str:
        """
        Extract the field reference from a source expression for use in transformScript.
        
        The transformScript should contain only the field reference (e.g., 'records$Contact.Id$'),
        NOT the full expression including function calls like WriteToOperationLog().
        
        Examples:
        - Input: [WriteToOperationLog(records$Contact.Id$); records$Contact.Id$]
          Output: 'records$Contact.Id$'
        
        - Input: [root$transaction.response$body$queryResponse$result$records.Contact$Id$]
          Output: 'root$transaction.response$body$queryResponse$result$records.Contact$Id$'
        
        Args:
            expression: Full source expression from JPK mapping
            
        Returns:
            Just the field reference portion for transformScript
        """
        import re
        
        if not expression:
            return ''
        
        # Remove surrounding brackets
        expr = expression.strip().strip('[]')
        
        # Check if expression contains function calls
        # Pattern: function_name(...)
        if '(' in expr and ')' in expr:
            # Expression contains function calls
            # The field reference is typically at the end after the last semicolon
            # Or it's the argument to the last function
            
            # Try to find a simple field reference after a semicolon
            if ';' in expr:
                parts = expr.split(';')
                # Get the last non-empty part
                for part in reversed(parts):
                    part = part.strip()
                    if part and '(' not in part:
                        return part.rstrip('.$') + '$'
            
            # If no semicolon, extract the field reference from the function argument
            # Pattern: function_name(field_reference)
            match = re.search(r'\(([^()]+)\)\s*$', expr)
            if match:
                return match.group(1).strip().rstrip('.$') + '$'
        
        # No function calls, return the expression as-is (after cleaning)
        return expr.rstrip('.$') + '$' if expr else ''
    
    def _format_transform_script(self, expression: str) -> str:
        """
        Format transform script with <trans> tags.
        
        Jitterbit transformScript format requires <trans>...</trans> wrapper.
        The expression inside uses JPK notation (e.g., Contacts$Contact.Description$).
        
        Args:
            expression: Source expression from JPK
            
        Returns:
            Formatted script with <trans> tags
        """
        if not expression:
            return ''
        return f"<trans>\n{expression}\n</trans>"
    
    def _generate_guid(self, seed: str) -> str:
        """Generate deterministic GUID from seed value."""
        if seed in self.guid_cache:
            return self.guid_cache[seed]
        
        # Use UUID5 for deterministic generation
        namespace = uuid.UUID('a3bb189e-8bf9-3888-9912-ace4e6543002')
        guid = str(uuid.uuid5(namespace, seed))
        self.guid_cache[seed] = guid
        return guid
    
    # =========================================================================
    # PRECONDITION GENERATION FUNCTIONS (Request #008)
    # =========================================================================
    
    def _get_parent_paths(self, target_path: str) -> List[str]:
        """
        Extract all parent paths from a target path.
        
        Args:
            target_path: Full target path (e.g., "upsertList/record/Contact/externalId")
        
        Returns:
            List of parent paths sorted by depth (shortest first)
            e.g., ["upsertList", "upsertList/record", "upsertList/record/Contact"]
        """
        if not target_path:
            return []
        
        segments = target_path.split('/')
        parent_paths = []
        
        # Build all parent paths (exclude the final element which is the field)
        for i in range(1, len(segments)):
            parent_path = '/'.join(segments[:i])
            parent_paths.append(parent_path)
        
        return parent_paths
    
    def _convert_path_to_jpk_notation(self, target_path: str, is_loop_element: bool = False) -> str:
        """
        Convert JSON path notation to JPK notation for targetScript.
        
        Pattern (from baseline analysis):
        - First segment: add '$' suffix
        - Subsequent segments: add '$' suffix (or '.' for loop elements)
        - Preconditions typically end with '$', loop elements end with '.'
        
        Args:
            target_path: Target path in JSON notation (e.g., "upsertList/record/Contact")
            is_loop_element: If True, ends with '.' (for looping/repeating elements)
        
        Returns:
            JPK notation (e.g., "upsertList$record.Contact$")
        """
        if not target_path:
            return ''
        
        segments = target_path.split('/')
        
        if len(segments) == 1:
            # Single segment: just add '$'
            return f"{segments[0]}$"
        
        # Build JPK notation:
        # Pattern: segment1$segment2.segment3$segment4$...
        # First segment gets '$', second segment starts with that, then '.' prefix for next, then '$' suffix
        
        # Based on baseline: upsertList$record.Contact$
        # segment1 = upsertList -> upsertList$
        # segment2 = record -> record. (loop element, but we use $ for intermediate)
        # segment3 = Contact -> Contact$
        
        # Simpler approach based on observed patterns:
        # Join with '$' and add appropriate suffix
        result_parts = []
        
        for i, seg in enumerate(segments):
            if i == 0:
                result_parts.append(f"{seg}$")
            elif i == 1:
                # Second segment typically followed by '.'
                result_parts.append(f"{seg}.")
            else:
                result_parts.append(f"{seg}$")
        
        result = ''.join(result_parts)
        
        # Adjust ending based on whether it's a loop element
        if is_loop_element:
            # Loop elements end with '.'
            if result.endswith('$'):
                result = result[:-1] + '.'
        
        return result
    
    def _create_precondition_rule(self, target_path: str, is_loop_element: bool = False) -> Dict[str, Any]:
        """
        Create a precondition mapping rule for a target path.
        
        Args:
            target_path: Target path in JSON notation (e.g., "upsertList/record/Contact")
            is_loop_element: If True, this is a loop/repeating element
        
        Returns:
            Precondition rule dictionary
        """
        # Convert JSON path to JPK notation for targetScript
        target_script = self._convert_path_to_jpk_notation(target_path, is_loop_element)
        
        return {
            'customValuePaths': [],
            'globalVariables': [],
            'isPreconditionScript': True,
            'targetPath': target_path,
            'targetScript': target_script,
            'transformScript': '',
            'validationErrors': [],
            'transformScriptCleansed': '',
            'srcPaths': None  # Preconditions must have null srcPaths, not empty array
        }
    
    def _generate_intermediate_preconditions(self, field_mappings: List[Dict[str, Any]], 
                                             existing_precond_paths: set = None) -> List[Dict[str, Any]]:
        """
        Generate intermediate precondition rules from field mappings.
        
        Analyzes all field mapping target paths and creates precondition rules
        for every unique parent path that needs loop context.
        
        Args:
            field_mappings: List of converted field mapping rules
            existing_precond_paths: Set of paths that already have preconditions (to avoid duplicates)
        
        Returns:
            List of precondition rules sorted by depth (shortest first)
        """
        if existing_precond_paths is None:
            existing_precond_paths = set()
        
        # Collect all unique parent paths
        parent_paths = set()
        
        for mapping in field_mappings:
            target_path = mapping.get('targetPath', '')
            if not target_path:
                continue
            
            # Skip if this is already a precondition
            if mapping.get('isPreconditionScript'):
                continue
            
            # Get all parent paths for this mapping
            parents = self._get_parent_paths(target_path)
            parent_paths.update(parents)
        
        # Remove paths that already have preconditions
        parent_paths = parent_paths - existing_precond_paths
        
        # Sort by depth (number of "/" characters)
        sorted_paths = sorted(parent_paths, key=lambda p: p.count('/'))
        
        # Generate precondition rules
        preconditions = []
        for path in sorted_paths:
            # Determine if this is a loop element based on depth
            # Depth 1 (like upsertList/record) is typically the main loop
            depth = path.count('/')
            is_loop = (depth == 1)  # Simple heuristic: depth 1 is the main loop
            
            precondition = self._create_precondition_rule(path, is_loop)
            preconditions.append(precondition)
        
        return preconditions

