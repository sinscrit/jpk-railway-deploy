"""
Operation Conversion Rules Configuration

This module centralizes all rules, heuristics, and decision logic used in
JPK-to-JSON operation conversion. All rules are designed to be:
- JPK-driven: Use data from JPK files
- Rule-based: Generic heuristics that work for any JPK
- Configurable: Can be adjusted without modifying core conversion logic
- Reviewable: All rules in one place for easy review and maintenance

Date: December 14, 2025
"""

from typing import Dict, List, Any, Optional


# ============================================================================
# ACTIVITY ROLE TO STEP TYPE MAPPINGS
# ============================================================================

ACTIVITY_ROLE_TO_STEP_TYPE: Dict[str, int] = {
    'script': 400,        # Script role → Type 400 (script component)
    'request': 700,       # Request role → Type 700 (transformation)
    'response': 700,      # Response role → Type 700 (transformation)
    'source': 500,        # Source role → Type 500 (endpoint)
    'target': 500,        # Target role → Type 500 (endpoint)
}

ACTIVITY_TYPE_TO_STEP_TYPE: Dict[str, int] = {
    '23': 400,            # Script type 23 → Type 400
    '4': 700,             # Transformation type 4 → Type 700
    '2': 500,             # Source type 2 → Type 500
    '3': 500,             # Target type 3 → Type 500
    '232': 500,           # NetSuite Function → Type 500
}

def determine_step_type(role: str, activity_type: str) -> int:
    """
    Determine step type (400, 500, 700) from JPK activity role and type.
    
    Mapping rules:
    - Request/Response role → Type 700 (transformation)
    - Script role → Type 400 (script component)
    - Source/Target role → Type 500 (endpoint)
    - NetSuite Function/Web Service Call → Type 500 (endpoint)
    
    Args:
        role: JPK activity role (e.g., "Script", "Request", "Response", "Source", "Target")
        activity_type: JPK activity type (string number like "23", "2", "4")
        
    Returns:
        Step type (400, 500, or 700)
    """
    role_lower = role.lower() if role else ""
    
    # Check role-based mapping first
    if role_lower in ACTIVITY_ROLE_TO_STEP_TYPE:
        return ACTIVITY_ROLE_TO_STEP_TYPE[role_lower]
    
    # Fall back to activity type mapping
    activity_type_str = str(activity_type) if activity_type else ""
    if activity_type_str in ACTIVITY_TYPE_TO_STEP_TYPE:
        return ACTIVITY_TYPE_TO_STEP_TYPE[activity_type_str]
    
    # Default fallback: assume endpoint for unknown types
    return 500


# ============================================================================
# STEP ID MAPPING RULES
# ============================================================================

def get_step_id_for_activity(activity: Dict[str, Any], step_type: int) -> Optional[str]:
    """
    Get the appropriate step ID for an activity based on step type.
    
    Mapping rules:
    - For Type 700 (transformations): Use content_id (references transformation)
    - For Type 400 (scripts): Use activity_id (references script component)
    - For Type 500 (endpoints): Use activity_id (references endpoint component)
    
    Args:
        activity: JPK activity dictionary with activity_id, content_id, etc.
        step_type: Step type (400, 500, or 700)
        
    Returns:
        Step ID string or None if not available
    """
    activity_id = activity.get('activity_id', '')
    content_id = activity.get('content_id', '')
    
    if step_type == 700:
        # Transformations use content_id
        return content_id if content_id else activity_id
    else:
        # Scripts and endpoints use activity_id
        return activity_id if activity_id else content_id


# ============================================================================
# OPERATION TYPE CONFIGURATION
# ============================================================================

# Default operation type for standard operations
DEFAULT_OPERATION_TYPE: int = 3

# Operation outcome types
OUTCOME_TYPE_SUCCESS: int = 200
OUTCOME_TYPE_ERROR: int = 400


# ============================================================================
# SCRIPT CONTENT EXTRACTION RULES
# ============================================================================

def should_extract_script_content(activity: Dict[str, Any]) -> bool:
    """
    Determine if script content should be extracted for an activity.
    
    Rule: Extract script content for activities with role "Script" and type "23"
    
    Args:
        activity: JPK activity dictionary
        
    Returns:
        True if script content should be extracted
    """
    role = activity.get('role', '').lower()
    activity_type = str(activity.get('type', ''))
    return role == 'script' and activity_type == '23'


def get_script_file_path(content_id: str) -> str:
    """
    Generate expected script file path in JPK based on content_id.
    
    Rule: Script files are located at: {project_dir}/Data/Script/{content_id}.xml
    
    Args:
        content_id: Script content ID from JPK activity
        
    Returns:
        Expected file path within JPK archive
    """
    # Note: Actual path extraction handles various project directory patterns
    # This is just for reference/documentation
    return f"Data/Script/{content_id}.xml"





