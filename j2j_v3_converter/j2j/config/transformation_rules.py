"""
Transformation Conversion Rules Configuration

This module centralizes all rules, heuristics, and decision logic used in
JPK-to-JSON transformation conversion. All rules are designed to be:
- JPK-driven: Use data from JPK files
- Rule-based: Generic heuristics that work for any JPK
- Configurable: Can be adjusted without modifying core conversion logic
- Reviewable: All rules in one place for easy review and maintenance

Date: December 14, 2025
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass


# ============================================================================
# TYPE ID MAPPINGS
# ============================================================================

TYPE_ID_TO_ADAPTER: Dict[str, str] = {
    '12': 'salesforce',     # Salesforce SOAP input (Request transformations)
    '14': 'salesforce',     # Salesforce Query output (Response transformations)
    '101': 'netsuite',
    '102': 'netsuite',
}

TYPE_ID_TO_SCHEMA_TYPE: Dict[str, str] = {
    '12': 'connector',      # Salesforce SOAP input connector schema
    '14': 'connector',      # Salesforce Query connector schema
    '101': 'connector',     # NetSuite request connector schema
    '102': 'connector',     # NetSuite response connector schema
    '1': 'user',            # User schema
    '4': 'canonical',       # Canonical schema
}

TYPE_ID_TO_FUNCTION_NAME: Dict[str, str] = {
    '101': 'upsert',        # NetSuite request
    '102': 'upsert',        # NetSuite response
}

TYPE_ID_TO_DIRECTION: Dict[str, str] = {
    '12': 'input',          # Salesforce SOAP input → input direction (Request)
    '14': 'output',         # Salesforce Query → output direction (Response)
    '101': 'input',         # NetSuite request → input direction
    '102': 'output',        # NetSuite response → output direction
}


# ============================================================================
# FLAT SCHEMA DETECTION RULES
# ============================================================================

FLAT_SCHEMA_NATURE_VALUES: List[str] = ['Flat']
FLAT_SCHEMA_TYPE_VALUES: List[str] = ['Text']

def is_flat_schema(jpk_schema: Dict[str, Any]) -> bool:
    """
    Determine if a schema is a flat/text schema from JPK data.
    
    Rule: Check nature == 'Flat' OR type == 'Text'
    
    Args:
        jpk_schema: Schema data from JPK
        
    Returns:
        True if flat schema, False otherwise
    """
    nature = jpk_schema.get('nature')
    schema_type = jpk_schema.get('type')
    return (nature in FLAT_SCHEMA_NATURE_VALUES or 
            schema_type in FLAT_SCHEMA_TYPE_VALUES)


# ============================================================================
# SCHEMA FORMAT DETERMINATION RULES
# ============================================================================

@dataclass
class SchemaFormatRule:
    """Rule for determining schema format and metadata version."""
    format: str
    metadata_version: str
    condition: str  # Description of when this rule applies

SCHEMA_FORMAT_RULES: List[SchemaFormatRule] = [
    SchemaFormatRule(
        format="csv",
        metadata_version="3.0.1",
        condition="is_flat_schema == True"
    ),
    SchemaFormatRule(
        format="csv",
        metadata_version="2.0.0",
        condition="is_connector_schema == True (has origin_id and adapter_id)"
    ),
    SchemaFormatRule(
        format="xml",
        metadata_version="3.0.1",
        condition="is_user_schema == True (no origin, has document)"
    ),
]

def get_schema_format(is_flat: bool, is_connector: bool) -> Tuple[str, str]:
    """
    Determine schema format and metadata version based on schema type.
    
    Rules:
    1. Flat schemas → csv, 3.0.1
    2. Connector schemas → csv, 2.0.0
    3. User schemas → xml, 3.0.1
    
    Args:
        is_flat: True if flat schema
        is_connector: True if connector schema (has origin_id and adapter_id)
        
    Returns:
        Tuple of (format, metadata_version)
    """
    if is_flat:
        return ("csv", "3.0.1")
    elif is_connector:
        return ("csv", "2.0.0")
    else:
        return ("xml", "3.0.1")


# ============================================================================
# PATH EXTRACTION RULES
# ============================================================================

# Navigation prefixes to strip when extracting schema-relative paths
NAVIGATION_PREFIXES: List[str] = [
    'root',
    'transaction',
    'response',
    'body',
    'queryresponse',
    'result',
]

# Collection roots to strip (when navigation prefix is present)
COLLECTION_ROOTS: List[str] = [
    'records',
    'rows',
    'row',
    'data',
    'items',
    'list',
    'entry',
    'element',
]

# Variable reference pattern: $VariableName$
VARIABLE_REFERENCE_PATTERN: str = r'^[\$][A-Za-z_][A-Za-z0-9_]*[\$]$'


def is_literal_string_constant(expression: str) -> bool:
    """
    Detect if an expression is a literal string constant (quoted string).

    Expressions like "Id" or "Email" are constant values assigned to fields,
    NOT source field references. These should not appear in srcPaths.

    Examples:
        - "Id" → True (literal string constant)
        - "Email" → True (literal string constant)
        - Contact$Id$ → False (field reference)
        - $VariableName$ → False (variable reference, handled separately)

    Args:
        expression: The expression string to check

    Returns:
        True if expression is a literal string constant, False otherwise
    """
    expr = expression.strip().strip('[]').strip()
    return expr.startswith('"') and expr.endswith('"')


# ============================================================================
# ARRAY INDEX FILTERING RULES
# ============================================================================

def should_keep_numeric_segment(segment: str, next_segment: Optional[str]) -> bool:
    """
    Determine if a numeric segment should be kept (schema structure) or removed (array index).
    
    Rule: Keep numeric segment if followed by a capitalized field name (schema structure).
          Remove numeric segment if followed by lowercase field name or end of path (array index).
    
    Examples:
        - baseRef/1/RecordRef → Keep /1/ (followed by RecordRef with capital R)
        - statusDetail/1/message → Remove /1/ (followed by message with lowercase m)
    
    Args:
        segment: The numeric segment to evaluate
        next_segment: The next segment in the path (None if at end)
        
    Returns:
        True if segment should be kept, False if it should be removed
    """
    if not segment.isdigit():
        return True  # Non-numeric segments are always kept
    
    if next_segment is None:
        return False  # At end of path, numeric is likely array index
    
    # Keep if next segment starts with capital letter (schema field name)
    if next_segment and next_segment[0].isupper():
        return True  # Part of schema structure (e.g., baseRef/1/RecordRef)
    
    return False  # Array index (e.g., statusDetail/1/message)


# ============================================================================
# RESPONSE TRANSFORMATION RULES
# ============================================================================

RESPONSE_TRANSFORMATION_KEYWORDS: List[str] = ['Response']

def is_response_transformation(transformation_name: str) -> bool:
    """
    Determine if a transformation is a Response transformation.
    
    Rule: Transformation name contains "Response"
    
    Args:
        transformation_name: Name of the transformation
        
    Returns:
        True if Response transformation, False otherwise
    """
    return any(keyword in transformation_name for keyword in RESPONSE_TRANSFORMATION_KEYWORDS)

def has_script_based_mappings(mapping_rules: List[Dict[str, Any]]) -> bool:
    """
    Determine if transformation has script-based mappings.
    
    Rule: Any mapping rule has transformScript field
    
    Args:
        mapping_rules: List of mapping rules from transformation
        
    Returns:
        True if has script-based mappings, False otherwise
    """
    return any(mr.get('transformScript') for mr in mapping_rules)

def should_remove_source_origin(transformation_name: str, mapping_rules: List[Dict[str, Any]]) -> bool:
    """
    Determine if source origin should be removed for Response transformations.
    
    Rule: Response transformation with script-based mappings → remove origin, set source.id
    
    Args:
        transformation_name: Name of the transformation
        mapping_rules: List of mapping rules
        
    Returns:
        True if origin should be removed, False otherwise
    """
    return (is_response_transformation(transformation_name) and 
            has_script_based_mappings(mapping_rules))


# ============================================================================
# REFERENCE FILE LOOKUP PRIORITY RULES
# ============================================================================

@dataclass
class ReferenceFileLookupRule:
    """Rule for reference file lookup priority."""
    priority: int
    description: str
    pattern: Optional[str] = None  # Pattern or condition

REFERENCE_FILE_LOOKUP_PRIORITY: List[ReferenceFileLookupRule] = [
    ReferenceFileLookupRule(
        priority=0,
        description="Transformation-specific reference files",
        pattern="{transformation_name}_{role}_document.json"
    ),
    ReferenceFileLookupRule(
        priority=1,
        description="XSD-based schema from origin_to_schema_map",
        pattern="Uses (origin_id, direction) tuple from JPK"
    ),
    ReferenceFileLookupRule(
        priority=2,
        description="Connector schema glob pattern match",
        pattern="{adapter_id}_{Function}_{direction}_*.json"
    ),
    ReferenceFileLookupRule(
        priority=3,
        description="Exact name match or transformation-specific files",
        pattern="{schema_name}.json or {transformation_name}_{role}_document.json"
    ),
    ReferenceFileLookupRule(
        priority=4,
        description="Embedded document from transformation (user schemas)",
        pattern="Uses document field from transformation source/target"
    ),
    ReferenceFileLookupRule(
        priority=5,
        description="JPK field_structure fallback",
        pattern="Uses field_structure from JPK schema data"
    ),
]

# Flat schema reference file fallback (when JPK name doesn't match)
FLAT_SCHEMA_FALLBACK_REFERENCE: str = "New Flat Schema.json"

# ============================================================================
# FLAT SCHEMA BASELINE DEFAULTS (for matching baseline behavior)
# ============================================================================
# These defaults are used when JPK flat schema data should be normalized
# to match baseline expectations. Set USE_JPK_FLAT_FIELD_NAMES=True to
# use actual JPK field names instead.

# Whether to use actual field names from JPK Document extraction
# False = use FLAT_SCHEMA_DEFAULT_FIELD (matches baseline)
# True = use actual field names from JPK (JPK-driven)
USE_JPK_FLAT_FIELD_NAMES: bool = True

# Default schema name for flat schemas (used when USE_JPK_FLAT_FIELD_NAMES=False)
FLAT_SCHEMA_DEFAULT_NAME: str = "New Flat Schema"

# Default field name for flat schemas (used when USE_JPK_FLAT_FIELD_NAMES=False)
FLAT_SCHEMA_DEFAULT_FIELD: str = "field"


def get_flat_schema_field_name(jpk_field_names: List[str] = None) -> str:
    """
    Get the field name to use for flat schemas.

    Rule:
    - If USE_JPK_FLAT_FIELD_NAMES=True and jpk_field_names provided, use first JPK field
    - Otherwise, use FLAT_SCHEMA_DEFAULT_FIELD

    Args:
        jpk_field_names: Field names extracted from JPK Document

    Returns:
        Field name to use in flat schema structure
    """
    if USE_JPK_FLAT_FIELD_NAMES and jpk_field_names:
        return jpk_field_names[0]
    return FLAT_SCHEMA_DEFAULT_FIELD


def get_flat_schema_name(jpk_schema_name: str = None) -> str:
    """
    Get the schema name to use for flat schemas.

    Rule:
    - If USE_JPK_FLAT_FIELD_NAMES=True and jpk_schema_name provided, use JPK name
    - Otherwise, use FLAT_SCHEMA_DEFAULT_NAME

    Args:
        jpk_schema_name: Schema name from JPK Document

    Returns:
        Schema name to use
    """
    if USE_JPK_FLAT_FIELD_NAMES and jpk_schema_name:
        return jpk_schema_name
    return FLAT_SCHEMA_DEFAULT_NAME


# ============================================================================
# SOURCE SCHEMA SELECTION RULES
# ============================================================================

@dataclass
class SourceSchemaSelectionRule:
    """Rule for selecting source schema when multiple schemas share same origin."""
    priority: int
    description: str
    method: str

SOURCE_SCHEMA_SELECTION_PRIORITY: List[SourceSchemaSelectionRule] = [
    SourceSchemaSelectionRule(
        priority=1,
        description="Exact name match",
        method="Match by source.name to Type 900 schema name"
    ),
    SourceSchemaSelectionRule(
        priority=2,
        description="Origin + direction + structure match",
        method="Match by (origin_id, direction) AND verify schema has required nested structure from srcPaths"
    ),
    SourceSchemaSelectionRule(
        priority=3,
        description="Origin + direction match",
        method="Fallback to first match by (origin_id, direction)"
    ),
]


# ============================================================================
# TARGET SCHEMA MATCHING RULES
# ============================================================================

def match_target_schema_by_structure(target_doc: Dict[str, Any], schema_components: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Match transformation target to Type 900 schema by structure.
    
    Rule: For flat schemas, find Type 900 schema with customSchemaIsFlat == True
    
    Args:
        target_doc: Target document from transformation
        schema_components: List of Type 900 schema components
        
    Returns:
        Matching schema component or None
    """
    is_flat = target_doc.get('O', {}).get('customSchemaIsFlat', False) if isinstance(target_doc, dict) else False
    
    if is_flat:
        # Find flat schema by structure match
        for schema_comp in schema_components:
            schema_doc = schema_comp.get('schemaTypeDocument', {})
            schema_is_flat = schema_doc.get('O', {}).get('customSchemaIsFlat', False) if isinstance(schema_doc, dict) else False
            if schema_is_flat:
                return schema_comp
    
    return None


# ============================================================================
# PRECONDITION GENERATION RULES
# ============================================================================

FLAT_SCHEMA_TARGET_PREFIX: str = "__flat__"

def should_skip_precondition_generation(mapping_rules: List[Dict[str, Any]]) -> bool:
    """
    Determine if precondition generation should be skipped.
    
    Rule: Skip for flat schemas (target paths start with __flat__)
    
    Args:
        mapping_rules: List of mapping rules
        
    Returns:
        True if preconditions should be skipped, False otherwise
    """
    return any(
        mr.get('targetPath', '').startswith(FLAT_SCHEMA_TARGET_PREFIX)
        for mr in mapping_rules
    )


# ============================================================================
# FLAT SCHEMA TARGET PATH RULES
# ============================================================================

FLAT_SCHEMA_TARGET_PREFIX = '__flat__/'

def map_flat_schema_target_path(target_path: str, flat_field_names: List[str] = None) -> str:
    """
    Map target paths for flat schemas.

    Rules (JPK-driven when USE_JPK_FLAT_FIELD_NAMES=True):
    1. If target_path matches a JPK field name, use __flat__/{jpk_field_name}
    2. If target_path is 'data' (common JPK pattern), map to __flat__/{actual_field}
    3. If already prefixed with __flat__/, keep as-is

    Rules (baseline mode when USE_JPK_FLAT_FIELD_NAMES=False):
    1. Map 'data' → '__flat__/field' (baseline behavior)
    2. All flat fields normalize to 'field'

    Args:
        target_path: Original target path from JPK
        flat_field_names: Optional list of flat schema field names from JPK Document

    Returns:
        Mapped target path with __flat__/ prefix for flat schema fields
    """
    # Already prefixed - return as-is
    if target_path.startswith(FLAT_SCHEMA_TARGET_PREFIX):
        return target_path

    # Get the actual field name to use based on rules
    actual_field = get_flat_schema_field_name(flat_field_names)

    # If target_path matches any known flat field name, map to actual field
    if flat_field_names and target_path in flat_field_names:
        return f"{FLAT_SCHEMA_TARGET_PREFIX}{actual_field}"

    # Common JPK pattern: 'data' is the target path for flat schemas
    if target_path == 'data':
        return f"{FLAT_SCHEMA_TARGET_PREFIX}{actual_field}"

    # For simple field names (no slashes), assume they're flat schema fields
    if '/' not in target_path and target_path:
        return f"{FLAT_SCHEMA_TARGET_PREFIX}{actual_field}"

    return target_path


# ============================================================================
# SCHEMA STORAGE RULES (Type 700 Transformations)
# ============================================================================

def should_use_origin_reference(type_id: str) -> bool:
    """
    Determine if schema should use origin reference (connector) or embedded document (user).
    
    Rule: Connector schemas (type_id 14, 101, 102) → use origin, NO document
          User/canonical schemas (type_id 1, 4) → embed document, NO origin
    
    Args:
        type_id: Type ID from JPK
        
    Returns:
        True if should use origin reference, False if should embed document
    """
    return type_id in TYPE_ID_TO_ADAPTER


# ============================================================================
# VALIDATION RULES
# ============================================================================

def validate_schema_reference(schema_name: Optional[str], schema_id: Optional[str], 
                              schema_components: List[Dict[str, Any]]) -> bool:
    """
    Validate that a schema reference can be resolved to a Type 900 component.
    
    Rule: Check by ID first, then by name
    
    Args:
        schema_name: Schema name from transformation
        schema_id: Schema ID from transformation
        schema_components: List of Type 900 schema components
        
    Returns:
        True if reference can be resolved, False otherwise
    """
    schema_id_to_comp = {sc.get('id'): sc for sc in schema_components if sc.get('id')}
    schema_name_to_comp = {sc.get('name'): sc for sc in schema_components if sc.get('name')}
    
    if schema_id and schema_id in schema_id_to_comp:
        return True
    if schema_name and schema_name in schema_name_to_comp:
        return True
    
    return False


# ============================================================================
# PATH TRANSLATION RULES (Request #010)
# ============================================================================

# Root translation mappings for Salesforce-origin schemas
# These are applied ONLY when the schema is detected as Salesforce-origin
# (i.e., salesforce_object_name is set or schema name matches Salesforce pattern)
SALESFORCE_ROOT_TRANSLATIONS: Dict[str, str] = {
    'Contacts': 'records',  # Salesforce Query Response schema uses 'records' root
}

def should_skip_root_translation(source_root: Optional[str], salesforce_object_name: Optional[str]) -> bool:
    """
    Determine if canonical-to-runtime root translation should be skipped.

    RULE: This is a JPK-driven detection rule.

    - If source root has namespace prefix (e.g., "{http://...}Contacts"), it's a TRUE
      canonical schema and translation should be SKIPPED.
    - If salesforce_object_name is detected, the schema is Salesforce-origin and
      translation should be APPLIED.
    - If source root is simple (no namespace, like "records"), no translation needed.

    CONTEXT:
    - VB2_1 JPK: Uses ContactsResponse.xsd with root "records" → salesforce_object_name detected
      → Translation NOT needed (already uses "records")
    - VC JPK: Uses jb-canonical-contact.xsd with root "{namespace}Contacts"
      → Namespace detected → Translation SKIPPED (keeps "Contacts")

    Args:
        source_root: The sourcedtd_root from JPK (e.g., "{namespace}Contacts" or "records")
        salesforce_object_name: Salesforce object name if detected during discovery

    Returns:
        True if root translation should be SKIPPED (canonical schema with namespace)
        False if root translation should be APPLIED (Salesforce-origin schema)
    """
    # If source root has namespace prefix, it's a true canonical schema - skip translation
    if source_root and '}' in source_root:
        return True

    # If no Salesforce object detected, the root likely doesn't need translation
    if not salesforce_object_name:
        return True

    # Salesforce-origin schema detected - translation should be applied
    return False


def get_root_translation(root_element: str, skip_translation: bool) -> str:
    """
    Get the translated root element name for path construction.

    Args:
        root_element: The root element name (e.g., "Contacts", "records")
        skip_translation: True if translation should be skipped

    Returns:
        Translated root element (or original if skipped/no translation defined)
    """
    if skip_translation:
        return root_element

    return SALESFORCE_ROOT_TRANSLATIONS.get(root_element, root_element)


# ============================================================================
# HELPER FUNCTIONS FOR RULE APPLICATION
# ============================================================================

def get_adapter_id(type_id: str) -> Optional[str]:
    """Get adapterId from type_id using mapping rules."""
    return TYPE_ID_TO_ADAPTER.get(type_id)

def get_schema_type(type_id: str) -> Optional[str]:
    """Get schema type (connector/user/canonical) from type_id."""
    return TYPE_ID_TO_SCHEMA_TYPE.get(type_id)

def get_function_name(type_id: str) -> Optional[str]:
    """Get function name from type_id."""
    return TYPE_ID_TO_FUNCTION_NAME.get(type_id)

def get_direction(type_id: str) -> Optional[str]:
    """Get direction (input/output) from type_id."""
    return TYPE_ID_TO_DIRECTION.get(type_id)

