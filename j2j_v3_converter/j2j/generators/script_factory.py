"""
Script factory for J2J v327.

This module provides factory methods for creating Type 400 script components
from JPK script data.
"""

import re
from typing import Dict, Any, Optional, List
from ..utils.constants import DEFAULT_PROPERTIES


class ScriptFactory:
    """
    Factory class for creating script components (Type 400).
    
    This class converts JPK script data to Type 400 JSON format,
    extracting script content and setting proper component structure.
    """
    
    def __init__(self):
        """Initialize script factory."""
        pass
    
    def create_script(
        self,
        script_id: str,
        script_name: str,
        script_body: str = "",
        script_content_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a Type 400 script component from JPK script data.
        
        CRITICAL: Uses script_id (which should be JPK activity_id) as component ID
        so that operation steps can reference scripts correctly.
        
        Args:
            script_id: Script component ID (should be JPK activity_id for step references)
            script_name: Script name from JPK Header
            script_body: Script content body (without <trans> tags)
            script_content_id: Optional JPK content_id for reference
            
        Returns:
            Dictionary representing Type 400 script component
        """
        # Wrap script body in <trans> tags if not already wrapped
        if script_body and not script_body.strip().startswith('<trans>'):
            wrapped_body = f"<trans>\n{script_body}\n</trans>"
        elif script_body:
            wrapped_body = script_body
        else:
            wrapped_body = "<trans>\n</trans>"
        
        script_component = {
            "type": 400,
            "id": script_id,  # CRITICAL: Use activity_id so operations can reference it
            "name": script_name,
            "scriptBody": wrapped_body,
            "scriptBodyCleansed": wrapped_body,  # Same as scriptBody
            "scriptType": 1,  # Integer type
            "globalVariables": [],  # Empty list by default
            "notes": "",  # Empty string
            "checksum": DEFAULT_PROPERTIES['CHECKSUM'],
            "requiresDeploy": True,
            "metadataVersion": DEFAULT_PROPERTIES['METADATA_VERSION'],
            "encryptedAtRest": True,
            "chunks": 1,
            "cursor": "",  # Empty string
            "partial": False,
            "validationState": 100,  # Scripts should be valid (100) to match baseline, not invalid (300)
            "hidden": False
        }
        
        # Store original content_id for reference if provided
        if script_content_id:
            script_component['_conversion_metadata'] = {
                'original_content_id': script_content_id
            }
        
        return script_component
    
    def extract_script_body_from_xml(self, script_text: str) -> str:
        """
        Extract script body content from JPK script text.

        Args:
            script_text: Script text content from JPK (already extracted from XML element)

        Returns:
            Script body content (without <trans> tags)
        """
        if not script_text:
            return ""

        try:
            # Extract content between <trans> tags if present
            match = re.search(r'<trans>(.*?)</trans>', script_text, re.DOTALL)
            if match:
                return match.group(1).strip()
            else:
                # Return raw script text if no <trans> tags
                return script_text.strip()

        except Exception as e:
            print(f"   ⚠️  Error extracting script body from text: {e}")

        return ""

    def transform_script_references(
        self,
        script_body: str,
        reference_maps: Dict[str, Dict[str, str]]
    ) -> str:
        """
        Transform JPK-style references to Integration Studio TAG format.

        Transforms:
        - RunOperation("op.UUID") → RunOperation("<TAG>operation:OperationName</TAG>")
        - RunScript("sc.UUID") → RunScript("<TAG>script:ScriptName</TAG>")

        Args:
            script_body: Script body content (may include <trans> tags)
            reference_maps: Dictionary with 'operations' and 'scripts' mappings
                           {uuid: name, ...}

        Returns:
            Script body with transformed references
        """
        if not script_body:
            return script_body

        transformed = script_body

        # Transform RunOperation("op.UUID") references
        op_pattern = re.compile(r'RunOperation\s*\(\s*"op\.([a-f0-9-]+)"\s*\)')
        operations_map = reference_maps.get('operations', {})

        def replace_operation(match):
            uuid = match.group(1)
            op_name = operations_map.get(uuid)
            if op_name:
                return f'RunOperation("<TAG>operation:{op_name}</TAG>")'
            else:
                # Keep original if no mapping found
                print(f"   ⚠️  No operation name found for UUID: {uuid}")
                return match.group(0)

        transformed = op_pattern.sub(replace_operation, transformed)

        # Transform RunScript("sc.UUID") references
        script_pattern = re.compile(r'RunScript\s*\(\s*"sc\.([a-f0-9-]+)"\s*\)')
        scripts_map = reference_maps.get('scripts', {})

        def replace_script(match):
            uuid = match.group(1)
            script_name = scripts_map.get(uuid)
            if script_name:
                return f'RunScript("<TAG>script:{script_name}</TAG>")'
            else:
                # Keep original if no mapping found
                print(f"   ⚠️  No script name found for UUID: {uuid}")
                return match.group(0)

        transformed = script_pattern.sub(replace_script, transformed)

        return transformed

    def transform_all_scripts(
        self,
        scripts: List[Dict[str, Any]],
        reference_maps: Dict[str, Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        Transform references in all script components.

        Args:
            scripts: List of script components (Type 400)
            reference_maps: Dictionary with 'operations' and 'scripts' mappings

        Returns:
            List of scripts with transformed references
        """
        transformed_count = 0

        for script in scripts:
            script_body = script.get('scriptBody', '')
            if script_body:
                # Check if transformation is needed
                if 'RunOperation("op.' in script_body or 'RunScript("sc.' in script_body:
                    transformed_body = self.transform_script_references(
                        script_body, reference_maps
                    )
                    script['scriptBody'] = transformed_body
                    script['scriptBodyCleansed'] = transformed_body
                    transformed_count += 1
                    print(f"   🔄 Transformed references in script: {script.get('name', 'Unknown')}")

        if transformed_count > 0:
            print(f"   ✅ Transformed references in {transformed_count} scripts")

        return scripts


