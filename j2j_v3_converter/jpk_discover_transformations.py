#!/usr/bin/env python
"""
JPK Transformation Discovery Utility

Parses a Jitterbit JPK file to discover all transformations and extract:
- Transformation ID
- Transformation name
- Source schema/structure
- Target schema/structure

Output: JSON list of discovered transformations

================================================================================
JITTERBIT JPK FILE STRUCTURE
================================================================================

A JPK (Jitterbit Project Keeper) file is a ZIP archive containing:

ProjectFolder/
  ├── Data/                         # Core Jitterbit objects
  │   ├── Transformation/           # Transformation definitions (.xml)
  │   │   └── {guid}.xml           # Contains mappings, source/target references
  │   ├── Operation/                # Operation definitions (.xml)
  │   │   └── {guid}.xml           # Links operations to queries/calls
  │   ├── WebServiceCall/           # Web service call definitions (.xml)
  │   │   └── {guid}.xml           # SOAP/REST web service configurations
  │   ├── SalesforceQuery/          # Salesforce SOQL queries (.xml)
  │   │   └── {guid}.xml           # Contains SOQL query strings
  │   ├── Schema/                   # XML/JSON schemas (.xsd, .json)
  │   │   └── {guid}.xsd           # Schema definitions for validation
  │   └── [Other types...]          # Database, File, Script, etc.
  │
  └── Cache/                        # Parsed/cached representations
      └── JTR/                      # Jitterbit Tree Representation (.jtr.gz)
          ├── input_{guid}.jtr.gz  # Cached source field structures
          └── output_{guid}.jtr.gz # Cached target field structures

================================================================================
JITTERBIT TYPE IDS (source_type_id / target_type_id)
================================================================================

Common type IDs found in transformation properties:
  '1'  - XML Schema (XSD)
  '2'  - Flat File (CSV, Fixed Width)
  '3'  - Database (SQL Server, Oracle, PostgreSQL, etc.)
  '4'  - Variable/Script
  '6'  - HTTP/REST endpoint
  '9'  - NetSuite
  '14' - Salesforce (SOAP/REST)
  '15' - JSON Schema
  [Other IDs exist for additional connectors]

================================================================================
JTR (JITTERBIT TREE REPRESENTATION) FILES
================================================================================

JTR files are gzipped XML files in the Cache/JTR/ folder that contain:

1. TYPE LIBRARY: Reusable type definitions
   <CROM Type="typContact">
     <CROM Name="FirstName" Type="string" />
     <CROM Name="LastName" Type="string" />
   </CROM>

2. DOCUMENT ROOT: The actual root element of the document
   <CROM Name="Contact" Type="typContact" />

KEY CONCEPT: Simply parsing JTR shows the type library (typContact, typAddress),
NOT the actual document structure. To get the correct hierarchy, we must:
  1. Find the document root element (e.g., "Contact")
  2. Resolve its type reference (e.g., "typContact")
  3. Recursively resolve child type references to build the full tree

This is why functions like build_document_tree() exist.

================================================================================
SALESFORCE SPECIAL CASE - WHY IT'S DIFFERENT
================================================================================

Unlike other sources (NetSuite, HTTP, Database) where field structures are
stored in JTR cache files, Salesforce field lists are stored in SOQL queries.

REFERENCE CHAIN:
  Transformation.InputStructure.wsCallId (in Transformation XML)
    ↓
  WebServiceCall.{guid} (in Data/WebServiceCall/)
    ↓ (referenced by Operation XML as text match)
  Operation.{guid} (in Data/Operation/)
    ↓
  Operation.salesforce_wizard_guid property
    ↓
  SalesforceQuery.{guid} (in Data/SalesforceQuery/)
    ↓
  SOQL query string: "SELECT Id, AccountId, FirstName FROM Contact"

WHY THIS CHAIN EXISTS:
1. The Transformation only stores a reference to the WebServiceCall (wsCallId)
2. The WebServiceCall is a generic SOAP/REST call definition (doesn't store fields)
3. The Operation links the WebServiceCall to the SalesforceQuery
4. The SalesforceQuery contains the actual field list in the SOQL SELECT clause

WHY WE USE TWO-PHASE PROCESSING:
The main discovery loop uses a two-phase approach for Salesforce:

Phase 1 (extract_source_info): Set _needs_salesforce_fields flag
Phase 2 (main loop, after dependencies): Follow the reference chain

This is necessary because we need dependencies extracted first to get the
WebServiceCall ID, which is the starting point of the chain.

================================================================================
"""

import zipfile
import xml.etree.ElementTree as ET
import json
import sys
import gzip
import re
from pathlib import Path


def discover_transformations(jpk_path):
    """
    Discover all transformations in a JPK file.

    Args:
        jpk_path: Path to the JPK file

    Returns:
        List of transformation metadata dictionaries
    """
    transformations = []

    with zipfile.ZipFile(jpk_path, 'r') as jpk:
        # Extract project folder name for file paths
        all_files = jpk.namelist()
        project_folder = None
        for f in all_files:
            if '/Data/Transformation/' in f:
                project_folder = f.split('/')[0]
                break

        # Find all transformation XML files
        transformation_files = [
            f for f in jpk.namelist()
            if '/Data/Transformation/' in f and f.endswith('.xml')
        ]

        print(f"📂 Found {len(transformation_files)} transformation files in JPK")

        for tf in transformation_files:
            try:
                # Read and parse transformation XML
                xml_content = jpk.read(tf).decode('utf-8')
                root = ET.fromstring(xml_content)

                # Extract basic metadata from Header
                header = root.find('Header')
                if header is None:
                    print(f"⚠️  Skipping {tf}: No Header found")
                    continue

                transform_id = header.get('ID')
                transform_name = header.get('Name')
                is_deleted = header.get('Deleted', 'false').lower() == 'true'

                if is_deleted:
                    print(f"⚠️  Skipping {transform_name}: Marked as deleted")
                    continue

                # Extract properties
                properties = {}
                props_elem = root.find('Properties')
                if props_elem is not None:
                    for item in props_elem.findall('Item'):
                        key = item.get('key')
                        value = item.get('value')
                        properties[key] = value

                # Determine source information
                source_info = extract_source_info(properties, root, jpk, project_folder, transform_id)
                target_info = extract_target_info(properties, root, jpk, project_folder, transform_id)

                # Extract mappings
                mappings = extract_mappings(root)

                # Extract dependencies
                dependencies = extract_dependencies(root, properties, mappings, jpk, project_folder)

                # ============================================================
                # SALESFORCE TWO-PHASE PROCESSING
                # ============================================================
                # Phase 2: Now that dependencies are extracted, we can follow
                # the reference chain for Salesforce sources (type_id='14').
                #
                # WHY TWO PHASES?
                # - Phase 1 (in extract_source_info): Set flag when type_id='14'
                # - Phase 2 (here): Use dependencies to follow the chain
                #
                # CRITICAL: Different handling for Request vs Response transformations!
                # - Request: Source is usually canonical/user schema (NOT from WebServiceCall)
                # - Response: Source IS the WebServiceCall output (SOAP response schema)
                # ============================================================
                if source_info.get('_needs_salesforce_fields'):
                    # Remove the flag
                    del source_info['_needs_salesforce_fields']

                    # Check if this is a Response transformation
                    wizard_role = properties.get('saleforce_wizard_role', '')
                    is_response_transformation = 'RESPONSE' in wizard_role.upper()

                    # Get the operation type (QUERY, UPDATE, etc.)
                    operation_type = wizard_role.split('|')[0].lower() if '|' in wizard_role else 'query'

                    # Get WebServiceCall ID from source_info (set in extract_source_info from wsCallId attr)
                    ws_call_id = source_info.get('ws_call_id')

                    # If not found in source_info, try dependencies
                    if not ws_call_id:
                        for ws_call in dependencies.get('web_service_calls', []):
                            ws_call_id = ws_call.get('id')
                            break

                    if is_response_transformation and ws_call_id:
                        # ============================================================
                        # RESPONSE TRANSFORMATION: Source is WebServiceCall output
                        # ============================================================
                        # For Response transformations, the source schema is the SOAP response
                        # from the WebServiceCall, NOT from SalesforceQuery.
                        #
                        # Set call_id to the WebServiceCall ID so the origin is correct.
                        # The origin.functionName should be the operation type (update, query, etc.)
                        # ============================================================
                        source_info['call_id'] = ws_call_id
                        source_info['salesforce_function'] = operation_type  # 'update', 'query', etc.
                        print(f"  📊 Response transformation: Source linked to WebServiceCall({ws_call_id[:8]}...) for {operation_type}")

                    elif ws_call_id:
                        # ============================================================
                        # REQUEST TRANSFORMATION: Load fields from SalesforceQuery
                        # ============================================================
                        # Follow the input-driven chain: WebServiceCall → Operation → SalesforceQuery
                        # 1. Get WebServiceCall ID from dependencies
                        # 2. Find which Operation references this WebServiceCall
                        operation_id = find_operation_by_webservice_call(jpk, project_folder, ws_call_id)

                        if operation_id:
                            # 3. Get SalesforceQuery ID from the Operation
                            sf_query_id = load_salesforce_query_from_operation(jpk, project_folder, operation_id)

                            if sf_query_id:
                                # 4. Load Salesforce fields from the query
                                sf_query_data = load_salesforce_query_fields(jpk, project_folder, sf_query_id)
                                if sf_query_data:
                                    sf_structure = build_salesforce_field_structure(
                                        sf_query_data,
                                        sf_query_data.get('object_name', 'Contact')
                                    )
                                    if sf_structure:
                                        source_info['field_structure'] = sf_structure
                                        source_info['salesforce_query_id'] = sf_query_id
                                        source_info['salesforce_object_name'] = sf_query_data.get('object_name', 'Contact')
                                        print(f"  📊 Loaded {sf_structure['field_count']} Salesforce fields from SOQL query")
                                        print(f"     Chain: WebServiceCall({ws_call_id[:8]}...) → Operation({operation_id[:8]}...) → SalesforceQuery({sf_query_id[:8]}...)")

                transformation_data = {
                    "id": transform_id,
                    "name": transform_name,
                    "source": source_info,
                    "target": target_info,
                    "mappings": mappings,
                    "dependencies": dependencies,
                    "properties": {
                        "source_type_id": properties.get('source_type_id'),
                        "target_type_id": properties.get('target_type_id'),
                        "natureofsource": properties.get('natureofsource'),
                        "natureoftarget": properties.get('natureoftarget')
                    }
                }

                transformations.append(transformation_data)
                print(f"✅ Discovered: {transform_name}")

            except Exception as e:
                print(f"❌ Error processing {tf}: {e}")
                continue

    return transformations


def extract_source_info(properties, root, jpk, project_folder, transform_id):
    """
    Extract source schema/structure information.

    Args:
        properties: Properties dictionary from transformation XML
        root: XML root element
        jpk: ZipFile object
        project_folder: Project folder name in JPK
        transform_id: Transformation ID

    Returns:
        Dictionary with source information
    """
    source_info = {}

    # Source schema file
    source_xml = properties.get('source_xml')
    if source_xml:
        source_info['schema'] = source_xml

        # Try to load and parse the actual XSD schema
        schema_content = load_schema_file(jpk, project_folder, source_xml)
        if schema_content:
            source_info['schema_content'] = parse_xsd_schema(schema_content)

    # Source root element
    source_root = properties.get('sourcedtd_root')
    if source_root:
        source_info['root'] = source_root

    # Source type
    source_type_id = properties.get('source_type_id')
    source_info['type_id'] = source_type_id
    source_info['type'] = get_source_type_name(source_type_id)

    # Nature of source
    nature = properties.get('natureofsource')
    if nature:
        source_info['nature'] = nature

    # Check for InputStructure element
    input_struct = root.find('InputStructure')
    if input_struct is not None:
        # Web service call reference
        ws_call_id = input_struct.get('wsCallId')
        if ws_call_id:
            source_info['ws_call_id'] = ws_call_id

        call_id = input_struct.get('callId')
        if call_id:
            source_info['call_id'] = call_id
            source_info['call_type'] = input_struct.get('callType')

    # ============================================================
    # SALESFORCE PHASE 1: Set flag for later processing
    # ============================================================
    # For Salesforce sources (type_id='14'), we can't load field structure
    # yet because we need dependencies to be extracted first.
    #
    # The reference chain requires:
    #   Transformation → WebServiceCall (from dependencies)
    #                 → Operation → SalesforceQuery → SOQL fields
    #
    # Since dependencies haven't been extracted yet at this point,
    # we set a flag and handle Salesforce in Phase 2 (main loop).
    # ============================================================
    salesforce_loaded = False
    if source_type_id == '14':
        source_info['_needs_salesforce_fields'] = True  # Flag for Phase 2 processing

    # ============================================================
    # DEFAULT: Load from JTR cache (all non-Salesforce types)
    # ============================================================
    # For NetSuite, HTTP, Database, XML, JSON, etc., field structures
    # are stored in JTR cache files. This is the standard path.
    # ============================================================
    if not salesforce_loaded:
        jtr_fields = load_jtr_structure(jpk, project_folder, transform_id, 'input', source_root)
        if jtr_fields:
            source_info['field_structure'] = jtr_fields
    
    # ============================================================
    # SALESFORCE-ORIGIN XSD DETECTION
    # ============================================================
    # Detect if an XSD schema (type_id=4) is actually derived from Salesforce.
    # This happens when:
    # 1. One transformation queries Salesforce and outputs to an XSD schema
    # 2. Another transformation uses that XSD schema as its source
    # The XSD schema should still get Salesforce metadata (types, O, name).
    # 
    # Heuristic: Check if schema filename matches Salesforce patterns
    # e.g., "ContactsResponse.xsd", "AccountsQuery.xsd", etc.
    # ============================================================
    if source_type_id == '4' and not source_info.get('salesforce_object_name'):
        schema_name = source_info.get('schema', '').lower()
        # Common Salesforce object names to detect
        salesforce_objects = ['contact', 'account', 'opportunity', 'lead', 'case', 
                              'campaign', 'task', 'event', 'user', 'record']
        # Check if schema name contains Salesforce patterns
        for obj in salesforce_objects:
            if obj in schema_name and ('response' in schema_name or 'query' in schema_name):
                # This is likely a Salesforce-origin schema
                # Capitalize first letter of object name
                source_info['salesforce_object_name'] = obj.capitalize()
                print(f"  📋 Detected Salesforce-origin XSD schema: {source_info.get('schema')} (object: {obj.capitalize()})")
                break

    return source_info


def extract_target_info(properties, root, jpk, project_folder, transform_id):
    """
    Extract target schema/structure information.

    Args:
        properties: Properties dictionary from transformation XML
        root: XML root element
        jpk: ZipFile object
        project_folder: Project folder name in JPK
        transform_id: Transformation ID

    Returns:
        Dictionary with target information
    """
    target_info = {}

    # Target schema file
    target_xml = properties.get('target_xml')
    if target_xml:
        target_info['schema'] = target_xml

        # Try to load and parse the actual XSD schema
        schema_content = load_schema_file(jpk, project_folder, target_xml)
        if schema_content:
            target_info['schema_content'] = parse_xsd_schema(schema_content)

    # Target root element
    target_root = properties.get('targetdtd_root')
    if target_root:
        target_info['root'] = target_root

    # Target type - get early for JTR loading logic
    target_type_id = properties.get('target_type_id')

    # For Salesforce WebService Call schemas (type_id=12), the JTR root is always "root"
    # even though there's no targetdtd_root property
    jtr_root_for_loading = target_root
    if target_type_id == '12' and not jtr_root_for_loading:
        jtr_root_for_loading = 'root'

    # Load JTR cache structure for complete field definitions
    jtr_fields = load_jtr_structure(jpk, project_folder, transform_id, 'output', jtr_root_for_loading)
    if jtr_fields:
        target_info['field_structure'] = jtr_fields

    # Target type (already fetched above for JTR loading)
    target_info['type_id'] = target_type_id
    target_info['type'] = get_target_type_name(target_type_id)

    # Nature of target
    nature = properties.get('natureoftarget')
    if nature:
        target_info['nature'] = nature

    # Check for OutputStructure element
    output_struct = root.find('OutputStructure')
    if output_struct is not None:
        # Call reference - try wsCallId first (Salesforce SOAP), then callId (NetSuite)
        ws_call_id = output_struct.get('wsCallId')
        call_id = output_struct.get('callId')

        if ws_call_id:
            target_info['call_id'] = ws_call_id
            target_info['ws_call_id'] = ws_call_id  # Also store as ws_call_id for consistency
        elif call_id:
            target_info['call_id'] = call_id
            target_info['call_type'] = output_struct.get('callType')

        # Document reference (flat schema target)
        doc_id = output_struct.get('docId')
        if doc_id:
            target_info['doc_id'] = doc_id

            # Load Document structure for flat schemas
            # This extracts field definitions from Data/Document/{doc_id}.xml
            doc_structure = load_document_structure(jpk, project_folder, doc_id)
            if doc_structure:
                target_info['field_structure'] = doc_structure

    # ============================================================
    # SALESFORCE REQUEST TRANSFORMATION TARGET HANDLING
    # ============================================================
    # For Salesforce Request transformations (target_type_id=12), we need to:
    # 1. Set salesforce_function from the wizard_role (UPDATE, INSERT, etc.)
    # 2. Ensure call_id is set from wsCallId for origin.id
    # ============================================================
    wizard_role = properties.get('saleforce_wizard_role', '')
    if 'REQUEST' in wizard_role.upper() and target_type_id == '12':
        # Extract operation type from wizard_role (e.g., "UPDATE|REQUEST" → "update")
        operation_type = wizard_role.split('|')[0].lower() if '|' in wizard_role else 'update'
        target_info['salesforce_function'] = operation_type
        print(f"  📊 Request transformation: Target linked to Salesforce {operation_type} input")

    return target_info


def load_schema_file(jpk, project_folder, schema_filename):
    """
    Load XSD schema file from JPK.

    Args:
        jpk: ZipFile object
        project_folder: Project folder name
        schema_filename: Schema file name

    Returns:
        Schema file content as string, or None if not found
    """
    if not project_folder or not schema_filename:
        return None

    # Try files directory
    schema_path = f"{project_folder}/files/{schema_filename}"
    try:
        content = jpk.read(schema_path).decode('utf-8')
        return content
    except KeyError:
        pass

    return None


def load_jtr_structure(jpk, project_folder, transform_id, direction, doc_root=None):
    """
    Load and parse JTR (Jitterbit Tree Representation) cache file.

    Args:
        jpk: ZipFile object
        project_folder: Project folder name
        transform_id: Transformation ID
        direction: 'input' for source or 'output' for target
        doc_root: Optional document root element name for building proper hierarchy

    Returns:
        Parsed field structure dictionary or None
    """
    if not project_folder or not transform_id:
        return None

    # Construct cache file path
    cache_path = f"{project_folder}/cache/TransformationStructures/{transform_id}_{direction}.gz"

    try:
        # Read and decompress .gz file
        compressed_data = jpk.read(cache_path)
        jtr_content = gzip.decompress(compressed_data).decode('utf-8')

        # Parse JTR XML with optional document root
        return parse_jtr_xml(jtr_content, doc_root)
    except KeyError:
        # Cache file doesn't exist (e.g., for Salesforce sources)
        return None
    except Exception as e:
        print(f"⚠️  Warning: Could not parse JTR cache for {transform_id}_{direction}: {e}")
        return None


def parse_jtr_xml(jtr_content, doc_root=None):
    """
    Parse Jitterbit JTR XML format to extract field structure.

    CRITICAL CONCEPT - Type Library vs Document Structure:

    JTR files contain TWO different things:

    1. TYPE LIBRARY (ElementType elements):
       <ElementType Name="typContact">
         <CROM>
           <CROM Name="FirstName" Type="string" />
           <CROM Name="LastName" Type="string" />
         </CROM>
       </ElementType>

       This is a DEFINITION, not the actual document structure.

    2. DOCUMENT ROOT (root-level CROM elements):
       <CROM Name="Contact" Type="typContact" />

       This is the ACTUAL top-level element in the document.

    THE PROBLEM:
    If we just extract all ElementType definitions, we get a flat list
    of types (typContact, typAddress, typCommunication), but we lose
    the actual document hierarchy (Contacts → Contact → fields).

    THE SOLUTION:
    When doc_root is provided (e.g., "Contacts"), we:
    1. Find the root-level CROM element with that name
    2. Resolve its Type reference (e.g., "typContact")
    3. Recursively resolve all child type references
    4. Build the actual document tree structure

    EXAMPLE:
    Without doc_root: Returns [typContact, typAddress, typCommunication]
    With doc_root="Contacts": Returns [Contacts → Contact → Communication → Address]

    Args:
        jtr_content: JTR XML content as string
        doc_root: Optional document root element name (e.g., 'Contacts')
                  If provided, builds tree from root element.
                  If None, returns all type definitions (legacy behavior).

    Returns:
        Dictionary with:
          - field_count: Total number of fields in hierarchy
          - fields: List of field objects with nested children
          - is_flat: True if this is a flat/text schema
          - flat_fields: List of field names for flat schemas
    """
    try:
        root = ET.fromstring(jtr_content)

        # ============================================================
        # FLAT/TEXT SCHEMA HANDLING
        # ============================================================
        # Flat schemas have <JTR Type="Text"> and a different structure:
        # <JTR Type="Text">
        #   <CROM Type="0x8001">
        #     <Text/>
        #     <CROM Type="0x9">
        #       <Text StrQual="&quot;" Delimiter=","/>
        #       <CROM Type="0x1000024" Name="response">  <-- Field name here
        #         <Attr ValType="1"/>
        #       </CROM>
        #     </CROM>
        #   </CROM>
        # </JTR>
        # ============================================================
        jtr_type = root.get('Type', '')
        if jtr_type == 'Text':
            # This is a flat/text schema - extract field names from nested CROM elements
            flat_fields = []
            # Find all CROM elements with Name attribute (these are the field names)
            for crom in root.findall('.//CROM[@Name]'):
                field_name = crom.get('Name')
                if field_name:
                    flat_fields.append(field_name)

            return {
                'field_count': len(flat_fields),
                'fields': [],
                'is_flat': True,
                'flat_fields': flat_fields
            }

        # Build a lookup dictionary of type definitions
        type_defs = {}
        for element_type in root.findall('.//ElementType'):
            type_name = element_type.get('Name')
            root_crom = element_type.find('CROM')
            if root_crom is not None:
                field_def = parse_crom_element(root_crom)
                if field_def:
                    field_def['element_type_id'] = type_name
                    # Key by ElementType ID
                    type_defs[type_name] = field_def
                    # Also key by xml_type if available (for easier lookup)
                    xml_elem = root_crom.find('Xml')
                    if xml_elem is not None:
                        xml_type = xml_elem.get('Type')
                        if xml_type:
                            type_defs[xml_type] = field_def

        # If no doc_root specified, return all type definitions (old behavior)
        if not doc_root:
            fields = list(type_defs.values())
            return {
                'field_count': len(fields),
                'fields': fields
            }

        # Build document tree from root element
        # Remove namespace from doc_root if present
        clean_root = doc_root.split('}')[-1] if '}' in doc_root else doc_root

        # Find the root element's type definition
        root_fields = build_document_tree(clean_root, type_defs, root)

        if not root_fields:
            # Fallback to old behavior if we can't build document tree
            fields = list(type_defs.values())
            return {
                'field_count': len(fields),
                'fields': fields
            }

        return {
            'field_count': count_all_fields(root_fields),
            'fields': root_fields
        }
    except Exception as e:
        return {'error': str(e)}


def build_document_tree(root_element_name, type_defs, jtr_root):
    """
    Build document tree from root element by resolving type references.

    Args:
        root_element_name: Name of the root element (e.g., 'Contacts')
        type_defs: Dictionary mapping type names to their field definitions
        jtr_root: JTR XML root element

    Returns:
        List of field definitions representing document structure
    """
    # First, look for root CROM element at the root level (outside ElementTypes)
    for child in jtr_root:
        if child.tag == 'CROM' and child.get('Name') == root_element_name:
            # Build tree from this root element
            root_field = parse_crom_element_with_types(child, '', type_defs)
            return [root_field] if root_field else []

    # Fallback: Find the root element definition inside ElementType
    for element_type in jtr_root.findall('.//ElementType'):
        root_crom = element_type.find('CROM')
        if root_crom is not None and root_crom.get('Name') == root_element_name:
            # Build tree from this root element
            root_field = parse_crom_element_with_types(root_crom, '', type_defs)
            return [root_field] if root_field else []

    return []


def parse_crom_element_with_types(crom_elem, path, type_defs):
    """
    Parse CROM element and resolve type references to build complete hierarchy.

    Args:
        crom_elem: CROM XML element
        path: Current field path
        type_defs: Dictionary mapping type names to their field definitions

    Returns:
        Dictionary with field information including resolved children
    """
    field_name = crom_elem.get('Name')
    field_type = crom_elem.get('Type')

    if not field_name:
        return None

    # Build current path
    current_path = f"{path}.{field_name}" if path else field_name

    field_def = {
        'name': field_name,
        'path': current_path,
        'type': field_type,
        'children': []
    }

    # Extract XML metadata
    xml_elem = crom_elem.find('Xml')
    if xml_elem is not None:
        field_def['xml_type'] = xml_elem.get('Type')
        field_def['min_occurs'] = xml_elem.get('Min')
        field_def['max_occurs'] = xml_elem.get('Max')
        field_def['namespace'] = xml_elem.get('NS')

    # Extract attribute metadata (for leaf fields)
    attr_elem = crom_elem.find('.//Attr')
    if attr_elem is not None:
        field_def['value_type'] = attr_elem.get('ValType')
        domain = attr_elem.get('Domain')
        if domain:
            field_def['domain_values'] = domain.split('|')[:10]
            field_def['has_domain'] = True

    # CRITICAL: ALWAYS parse direct child CROM elements FIRST
    # This ensures we get the actual document structure with all children
    # The direct children have the real nested structure (e.g., ID/typID/System)
    for child_crom in crom_elem.findall('CROM'):
        child_name = child_crom.get('Name')
        if child_name and not child_name.startswith('xsi:'):
            child_def = parse_crom_element_with_types(child_crom, current_path, type_defs)
            if child_def:
                field_def['children'].append(child_def)

    # If no direct children were found, try type resolution as fallback
    # This handles cases where the element references a type definition for its structure
    if not field_def['children']:
        xml_type = field_def.get('xml_type')
        if xml_type and xml_type in type_defs:
            type_def = type_defs[xml_type]
            if type_def.get('children'):
                for child in type_def['children']:
                    resolved_child = resolve_child_with_path(child, current_path, type_defs)
                    if resolved_child:
                        field_def['children'].append(resolved_child)

    return field_def


def resolve_child_with_path(child_field, parent_path, type_defs):
    """
    Resolve a child field from a type definition, updating its path.

    Args:
        child_field: Child field definition from type
        parent_path: Parent field path
        type_defs: Dictionary mapping type names to their field definitions

    Returns:
        Resolved child field with correct path
    """
    resolved = child_field.copy()
    resolved['path'] = f"{parent_path}.{child_field['name']}"

    # If this child has children, recursively update their paths
    if child_field.get('children'):
        resolved['children'] = []
        for grandchild in child_field['children']:
            resolved_grandchild = resolve_child_with_path(grandchild, resolved['path'], type_defs)
            if resolved_grandchild:
                resolved['children'].append(resolved_grandchild)
    else:
        # Check if child references a type that needs resolution
        xml_type = child_field.get('xml_type')
        if xml_type and xml_type in type_defs:
            type_def = type_defs[xml_type]
            if type_def.get('children'):
                resolved['children'] = []
                for type_child in type_def['children']:
                    resolved_child = resolve_child_with_path(type_child, resolved['path'], type_defs)
                    if resolved_child:
                        resolved['children'].append(resolved_child)

    return resolved


def count_all_fields(fields):
    """
    Recursively count all fields including nested children.

    Args:
        fields: List of field definitions

    Returns:
        Total count of all fields
    """
    count = len(fields)
    for field in fields:
        if field.get('children'):
            count += count_all_fields(field['children'])
    return count


def parse_crom_element(crom_elem, path=''):
    """
    Recursively parse CROM element to extract field definition.

    Args:
        crom_elem: CROM XML element
        path: Current field path

    Returns:
        Dictionary with field information
    """
    field_name = crom_elem.get('Name')
    field_type = crom_elem.get('Type')

    if not field_name:
        return None

    # Build current path
    current_path = f"{path}.{field_name}" if path else field_name

    field_def = {
        'name': field_name,
        'path': current_path,
        'type': field_type,
        'children': []
    }

    # Extract XML metadata
    xml_elem = crom_elem.find('Xml')
    if xml_elem is not None:
        field_def['xml_type'] = xml_elem.get('Type')
        field_def['min_occurs'] = xml_elem.get('Min')
        field_def['max_occurs'] = xml_elem.get('Max')
        field_def['namespace'] = xml_elem.get('NS')

    # Extract attribute metadata (for leaf fields)
    attr_elem = crom_elem.find('.//Attr')
    if attr_elem is not None:
        field_def['value_type'] = attr_elem.get('ValType')
        domain = attr_elem.get('Domain')
        if domain:
            # Parse domain enumeration
            field_def['domain_values'] = domain.split('|')[:10]  # Limit to first 10 for brevity
            field_def['has_domain'] = True

    # Recursively parse child CROM elements
    for child_crom in crom_elem.findall('CROM'):
        child_name = child_crom.get('Name')
        # Skip technical attributes like xsi:nil
        if child_name and not child_name.startswith('xsi:'):
            child_def = parse_crom_element(child_crom, current_path)
            if child_def:
                field_def['children'].append(child_def)

    return field_def


def parse_xsd_schema(schema_content):
    """
    Parse XSD schema and extract element definitions.

    Args:
        schema_content: XSD schema content as string

    Returns:
        Dictionary with parsed schema information
    """
    try:
        root = ET.fromstring(schema_content)

        # Define XML schema namespace
        ns = {'xs': 'http://www.w3.org/2001/XMLSchema'}

        schema_info = {
            'target_namespace': root.get('targetNamespace'),
            'elements': [],
            'complex_types': []
        }

        # Extract root elements
        for elem in root.findall('.//xs:element', ns):
            elem_name = elem.get('name')
            elem_type = elem.get('type')
            if elem_name:
                schema_info['elements'].append({
                    'name': elem_name,
                    'type': elem_type
                })

        # Extract complex types
        for complex_type in root.findall('.//xs:complexType', ns):
            type_name = complex_type.get('name')
            if type_name:
                fields = []
                for elem in complex_type.findall('.//xs:element', ns):
                    field_name = elem.get('name')
                    field_type = elem.get('type')
                    if field_name:
                        fields.append({
                            'name': field_name,
                            'type': field_type,
                            'min_occurs': elem.get('minOccurs'),
                            'max_occurs': elem.get('maxOccurs')
                        })

                schema_info['complex_types'].append({
                    'name': type_name,
                    'fields': fields
                })

        return schema_info
    except Exception as e:
        return {'error': str(e)}


def extract_dependencies(root, properties, mappings, jpk, project_folder):
    """
    Extract transformation dependencies (operations, web service calls, variables).

    Args:
        root: XML root element
        properties: Properties dictionary
        mappings: List of mapping dictionaries
        jpk: ZipFile object
        project_folder: Project folder name

    Returns:
        Dictionary with dependencies
    """
    dependencies = {
        'operations': [],
        'web_service_calls': [],
        'variables': []
    }

    # Extract operation/call references from InputStructure and OutputStructure
    input_struct = root.find('InputStructure')
    if input_struct is not None:
        ws_call_id = input_struct.get('wsCallId')
        call_id = input_struct.get('callId')

        if ws_call_id:
            # Web service call
            ws_call_info = load_web_service_call(jpk, project_folder, ws_call_id)
            if ws_call_info:
                dependencies['web_service_calls'].append(ws_call_info)

        if call_id:
            # Operation call (e.g., NetSuite)
            dependencies['operations'].append({
                'id': call_id,
                'type': input_struct.get('callType'),
                'role': 'input'
            })

    output_struct = root.find('OutputStructure')
    if output_struct is not None:
        call_id = output_struct.get('callId')
        doc_id = output_struct.get('docId')

        if call_id:
            dependencies['operations'].append({
                'id': call_id,
                'type': output_struct.get('callType'),
                'role': 'output'
            })

        if doc_id:
            dependencies['operations'].append({
                'id': doc_id,
                'type': 'document',
                'role': 'output'
            })

    # Extract variable references from mapping expressions
    import re
    variable_pattern = r'\[(\w+(?:\.\w+)*)\]|\$(\w+)\$'

    variables_found = set()

    for mapping in mappings:
        source_expr = mapping.get('source_expression', '')
        target_path = mapping.get('target_path', '')

        # Find variable references in both source and target
        for text in [source_expr, target_path]:
            if text:
                matches = re.findall(variable_pattern, text)
                for match in matches:
                    var_name = match[0] or match[1]
                    # Filter out field references (those with $ inside)
                    if var_name and not ('$' in var_name):
                        variables_found.add(var_name)

    # Add unique variables to dependencies
    for var_name in sorted(variables_found):
        dependencies['variables'].append({
            'name': var_name,
            'type': 'project_variable'
        })

    return dependencies


def load_web_service_call(jpk, project_folder, ws_call_id):
    """
    Load web service call definition from JPK.

    Args:
        jpk: ZipFile object
        project_folder: Project folder name
        ws_call_id: Web service call ID

    Returns:
        Web service call info dictionary or None
    """
    if not project_folder or not ws_call_id:
        return None

    ws_path = f"{project_folder}/Data/WebServiceCall/{ws_call_id}.xml"

    try:
        xml_content = jpk.read(ws_path).decode('utf-8')
        root = ET.fromstring(xml_content)

        header = root.find('Header')
        ws_name = header.get('Name') if header is not None else None

        properties = {}
        props_elem = root.find('Properties')
        if props_elem is not None:
            for item in props_elem.findall('Item'):
                key = item.get('key')
                value = item.get('value')
                properties[key] = value

        return {
            'id': ws_call_id,
            'name': ws_name,
            'type': 'web_service_call',
            'operation': properties.get('operation'),
            'service': properties.get('service'),
            'wsdl': properties.get('wsdl_display')
        }
    except KeyError:
        return None
    except Exception as e:
        print(f"⚠️  Warning: Could not load web service call {ws_call_id}: {e}")
        return None


def load_document_structure(jpk, project_folder, doc_id):
    """
    Load Document entity from JPK and extract field structure for flat schemas.

    This function is called when a transformation's OutputStructure references
    a Document via docId (flat/CSV-like target structure).

    Document XML Location: {project_folder}/Data/Document/{doc_id}.xml

    Document XML Structure:
    <Entity type="Document">
      <Structure>
        <Segment>
          <Fields>
            <Field name="fieldname" type="String"/>
          </Fields>
        </Segment>
      </Structure>
    </Entity>

    Args:
        jpk: ZipFile object
        project_folder: Project folder name in JPK
        doc_id: Document ID (guid)

    Returns:
        Dictionary with:
          - field_count: Number of fields
          - is_flat: True
          - flat_fields: List of field names (strings, not dicts)
        Or None if document cannot be loaded
    """
    if not project_folder or not doc_id:
        return None

    doc_path = f"{project_folder}/Data/Document/{doc_id}.xml"

    try:
        xml_content = jpk.read(doc_path).decode('utf-8')
        root = ET.fromstring(xml_content)

        # Extract fields from Structure/Segment/Fields
        flat_fields = []
        for field in root.findall('.//Segment/Fields/Field'):
            field_name = field.get('name')
            if field_name:
                flat_fields.append(field_name)

        if flat_fields:
            print(f"  Loaded {len(flat_fields)} fields from Document({doc_id[:8]}...)")

        return {
            'field_count': len(flat_fields),
            'is_flat': True,
            'flat_fields': flat_fields
        }
    except KeyError:
        # Document file doesn't exist in JPK
        return None
    except Exception as e:
        print(f"Warning: Could not load Document {doc_id}: {e}")
        return None


def find_operation_by_webservice_call(jpk, project_folder, ws_call_id):
    """
    Find an operation that references a given WebServiceCall.

    This is part of the Salesforce reference chain traversal:
    WebServiceCall → Operation → SalesforceQuery

    CONTEXT:
    In Jitterbit's architecture, Operations are the glue that connect
    WebServiceCalls to their underlying queries (Salesforce, Database, etc.).
    The Operation XML file contains a reference to the WebServiceCall ID
    as plain text, not as a structured property. Therefore, we must search
    through all Operation files to find which one contains the wsCallId.

    EXAMPLE:
    If a Transformation references WebServiceCall "c946915b...", we search
    all Operation files in Data/Operation/ to find one containing "c946915b"
    in its XML content. That Operation will have a salesforce_wizard_guid
    property pointing to the actual SalesforceQuery.

    Args:
        jpk: ZipFile object
        project_folder: Project folder name
        ws_call_id: WebServiceCall ID to search for

    Returns:
        Operation ID (guid) or None if not found
    """
    if not project_folder or not ws_call_id:
        return None

    try:
        # Find all operation files
        all_files = jpk.namelist()
        operation_files = [f for f in all_files
                          if f'{project_folder}/Data/Operation/' in f and f.endswith('.xml')]

        # Search each operation for the WebServiceCall reference
        for op_file in operation_files:
            op_xml = jpk.read(op_file).decode('utf-8')
            if ws_call_id in op_xml:
                # Found it - extract operation ID from filename
                operation_id = op_file.split('/')[-1].replace('.xml', '')
                return operation_id

        return None
    except:
        return None


def load_salesforce_query_from_operation(jpk, project_folder, operation_id):
    """
    Load Salesforce query ID from an operation.

    This is the second step in the Salesforce reference chain:
    Operation → SalesforceQuery

    CONTEXT:
    Operations in Jitterbit have properties stored as <Item key="..." value="..." />
    elements. For Salesforce operations, the key "salesforce_wizard_guid" contains
    the ID of the SalesforceQuery object that holds the actual SOQL query.

    EXAMPLE:
    Operation bae4acba... has property:
      <Item key="salesforce_wizard_guid" value="9c6b28e7..." />

    This tells us to look in Data/SalesforceQuery/9c6b28e7....xml for the
    SOQL query string.

    Args:
        jpk: ZipFile object
        project_folder: Project folder name
        operation_id: Operation ID (guid)

    Returns:
        SalesforceQuery ID (guid) or None if not found
    """
    if not project_folder or not operation_id:
        return None

    operation_path = f"{project_folder}/Data/Operation/{operation_id}.xml"

    try:
        xml_content = jpk.read(operation_path).decode('utf-8')
        root = ET.fromstring(xml_content)

        props = root.find('Properties')
        if props:
            for item in props.findall('Item'):
                if item.get('key') == 'salesforce_wizard_guid':
                    return item.get('value')
        return None
    except:
        return None


def load_salesforce_query_fields(jpk, project_folder, query_id):
    """
    Load Salesforce query and extract field list from SOQL.

    This is the final step in the Salesforce reference chain:
    SalesforceQuery → SOQL field list

    CONTEXT:
    SalesforceQuery XML files contain a SOQL query string in a special
    Konga format (Jitterbit's internal XML structure format). The query
    string contains the actual field list we need.

    EXAMPLE:
    SalesforceQuery 9c6b28e7....xml contains:
      <konga.string name="query_string">
        SELECT Id, AccountId, FirstName, LastName, Birthdate FROM Contact
      </konga.string>

    We parse this SOQL to extract:
    - Object name: "Contact"
    - Field list: ["Id", "AccountId", "FirstName", "LastName", "Birthdate"]

    WHY THIS MATTERS:
    Unlike other sources where field structures are cached in JTR files,
    Salesforce field lists come from the SOQL query. This is because:
    1. Users can select any fields they want in the query
    2. The query defines the exact field set for the transformation
    3. JTR cache doesn't contain Salesforce field structures

    Args:
        jpk: ZipFile object
        project_folder: Project folder name
        query_id: SalesforceQuery ID (guid)

    Returns:
        Dictionary with:
          - object_name: Salesforce object (e.g., "Contact")
          - field_count: Number of fields
          - fields: List of field names
          - soql: Original SOQL query string
        Or None if not found/parseable
    """
    if not project_folder or not query_id:
        return None

    query_path = f"{project_folder}/Data/SalesforceQuery/{query_id}.xml"

    try:
        xml_content = jpk.read(query_path).decode('utf-8')
        root = ET.fromstring(xml_content)

        # Get the SOQL query string
        query_elem = root.find('.//konga.string[@name="query_string"]')
        if query_elem is None or query_elem.text is None:
            return None

        soql = query_elem.text.strip()

        # Parse SOQL: SELECT field1, field2, ... FROM ObjectName
        match = re.search(r'SELECT\s+(.*?)\s+FROM\s+(\w+)', soql, re.IGNORECASE | re.DOTALL)
        if not match:
            return None

        fields_str = match.group(1)
        object_name = match.group(2)

        # Split field list and clean up
        fields = []
        for field in fields_str.split(','):
            field = field.strip()
            # Remove any trailing comments or placeholders
            field = re.sub(r'\[.*?\]', '', field).strip()
            if field and not field.startswith('--'):
                fields.append(field)

        return {
            'object_name': object_name,
            'field_count': len(fields),
            'fields': fields,
            'soql': soql
        }
    except KeyError:
        return None
    except Exception as e:
        print(f"⚠️  Warning: Could not load Salesforce query {query_id}: {e}")
        return None


def build_salesforce_field_structure(sf_query_data, object_name='Contact'):
    """
    Build field structure from Salesforce query field list.

    Args:
        sf_query_data: Dictionary with Salesforce query data
        object_name: Salesforce object name (e.g., 'Contact')

    Returns:
        Field structure dictionary compatible with JTR format
    """
    if not sf_query_data or not sf_query_data.get('fields'):
        return None

    # Create root object node
    root_field = {
        'name': object_name,
        'path': object_name,
        'type': 'salesforce_object',
        'children': []
    }

    # Add each field as a child
    for field_name in sorted(sf_query_data['fields']):
        field_node = {
            'name': field_name,
            'path': f"{object_name}.{field_name}",
            'type': 'salesforce_field',
            'children': []
        }
        root_field['children'].append(field_node)

    return {
        'field_count': len(sf_query_data['fields']) + 1,  # +1 for root
        'fields': [root_field],
        'salesforce_metadata': {
            'object_name': sf_query_data['object_name'],
            'field_count': sf_query_data['field_count'],
            'source': 'soql_query'
        }
    }


def extract_mappings(root):
    """
    Extract mapping rules from transformation.

    Args:
        root: XML root element

    Returns:
        List of mapping dictionaries
    """
    mappings = []

    mappings_elem = root.find('Mappings')
    if mappings_elem is None:
        return mappings

    for mapping in mappings_elem.findall('Mapping'):
        # Get the expression string
        expr_elem = mapping.find('konga.string[@name="expr"]')
        if expr_elem is None or expr_elem.text is None:
            continue

        expr_text = expr_elem.text.strip()

        # Parse the mapping expression
        # Format: [target_path]\t[source_expression] or [target_path]\t<trans>script</trans>
        parts = expr_text.split('\t', 1)
        if len(parts) != 2:
            # Handle mappings without tab separator
            mappings.append({
                "raw_expression": expr_text,
                "target_path": None,
                "source_expression": None
            })
            continue

        target_path = parts[0].strip()
        source_part = parts[1].strip()

        # Check if source has transformation script
        has_script = '<trans>' in source_part

        if has_script:
            # Extract script content between <trans> tags
            import re
            script_match = re.search(r'<trans>(.*?)</trans>', source_part, re.DOTALL)
            if script_match:
                script_content = script_match.group(1).strip()
            else:
                script_content = source_part

            mappings.append({
                "target_path": target_path,
                "source_expression": script_content,
                "has_transformation_script": True
            })
        else:
            # Simple field mapping
            mappings.append({
                "target_path": target_path,
                "source_expression": source_part,
                "has_transformation_script": False
            })

    return mappings


def get_source_type_name(type_id):
    """
    Map source type ID to human-readable name.

    Args:
        type_id: Source type ID string

    Returns:
        Human-readable type name
    """
    type_mapping = {
        '1': 'Text',
        '2': 'Binary',
        '4': 'XML (Schema)',
        '14': 'Salesforce',
        '101': 'NetSuite Request',
        '102': 'NetSuite Response'
    }
    return type_mapping.get(type_id, f'Unknown ({type_id})')


def get_target_type_name(type_id):
    """
    Map target type ID to human-readable name.

    Args:
        type_id: Target type ID string

    Returns:
        Human-readable type name
    """
    type_mapping = {
        '1': 'Text',
        '2': 'Binary',
        '4': 'XML (Schema)',
        '14': 'Salesforce',
        '101': 'NetSuite Request',
        '102': 'NetSuite Response'
    }
    return type_mapping.get(type_id, f'Unknown ({type_id})')


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python discover_transformations.py <jpk_file> [output_json]")
        print("\nExample:")
        print("  python discover_transformations.py original_source_vb.jpk")
        print("  python discover_transformations.py original_source_vb.jpk transformations.json")
        sys.exit(1)

    jpk_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not Path(jpk_path).exists():
        print(f"❌ Error: JPK file not found: {jpk_path}")
        sys.exit(1)

    print(f"🔍 Discovering transformations in: {jpk_path}\n")

    transformations = discover_transformations(jpk_path)

    print(f"\n📊 Discovery Summary:")
    print(f"   Total transformations found: {len(transformations)}")

    # Prepare output
    output = {
        "jpk_file": jpk_path,
        "transformation_count": len(transformations),
        "transformations": transformations
    }

    # Write to file or stdout
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        print(f"\n✅ Output written to: {output_path}")
    else:
        print("\n📄 JSON Output:")
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
