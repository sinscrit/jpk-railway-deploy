"""
Operation factory for J2J v327.

This module provides factory methods for creating Type 200 operation components
from JPK operation data.
"""

import uuid
from typing import Dict, Any, List, Optional

from ..utils.constants import COMPONENT_TYPES


class OperationFactory:
    """
    Factory class for creating operation components (Type 200).
    
    This class converts JPK operation data to Type 200 JSON format,
    mapping activities to steps and handling operation properties.
    """
    
    def __init__(self):
        """Initialize operation factory."""
        pass
    
    def create_operation(
        self,
        operation_id: str,
        operation_name: str,
        activities: List[Dict[str, Any]] = None,
        properties: Dict[str, Any] = None,
        failure_operation_id: Optional[str] = None,
        existing_transformation_ids: Optional[set] = None
    ) -> Dict[str, Any]:
        """
        Create a Type 200 operation component from JPK operation data.
        
        Args:
            operation_id: JPK operation ID (used as JSON operation ID)
            operation_name: Operation name from JPK
            activities: List of JPK activities (for step generation)
            properties: JPK operation properties
            failure_operation_id: Optional failure operation ID for outcomes
            
        Returns:
            Dictionary representing Type 200 operation component
        """
        operation = {
            "type": 200,
            "id": operation_id,
            "name": operation_name,
            "operationType": 3,  # Default operation type (3 = standard operation)
            "checksum": "1",  # Default checksum
            "validationState": 100,  # Valid state
            "encryptedAtRest": True,
            "hidden": False,
            "chunks": 1,
            "partial": False,
            "requiresDeploy": True,
            "metadataVersion": "3.0.1",
            "isNew": False,
            "steps": [],
            "outcomes": []
        }
        
        # Map activities to steps
        if activities:
            operation["steps"] = self._map_activities_to_steps(activities, existing_transformation_ids)
        
        # Create outcomes if failure handler exists
        if failure_operation_id:
            operation["outcomes"] = self._create_outcomes(failure_operation_id)
        
        # Add properties if provided
        if properties:
            operation["properties"] = properties
        
        return operation
    
    def _map_activities_to_steps(self, activities: List[Dict[str, Any]], existing_transformation_ids: Optional[set] = None) -> List[Dict[str, Any]]:
        """
        Map JPK activities to operation steps.
        
        Mapping rules:
        - Script role (type 23) → Type 400 (script component) - Use activity_id as step ID
        - Source/Target role (type 2/3) → Type 500 (endpoint component) - Use activity_id as step ID
        - Request/Response role (type 4) → Type 700 (transformation component) - Use content_id as step ID
        - NetSuite Function/Web Service Call → Type 500 (endpoint component) - Use activity_id as step ID
        
        CRITICAL FIX (December 15, 2025):
        - Request transformations are only included as steps if they exist as Type 700 components
        - Request transformations in JPK are configuration/metadata for activities, not always workflow steps
        - If existing_transformation_ids is provided and Request transformation's content_id is not in it, skip it
        
        Args:
            activities: List of JPK activity dictionaries
            existing_transformation_ids: Optional set of transformation content_ids that exist as Type 700 components
            
        Returns:
            List of step dictionaries with id and type
        """
        steps = []
        
        for activity in activities:
            role = activity.get('role', '').lower()
            activity_type = activity.get('type', '')
            activity_id = activity.get('activity_id', '')
            content_id = activity.get('content_id', '')
            
            # CRITICAL FIX: Skip Request transformations that don't exist as Type 700 components
            # Request transformations are configuration for activities, not always separate workflow steps
            if role == 'request' and existing_transformation_ids is not None:
                if content_id and content_id not in existing_transformation_ids:
                    # Skip this Request transformation - it doesn't exist as a Type 700 component
                    continue
            
            # Determine step type based on role and activity type
            step_type = self._determine_step_type(role, activity_type)
            
            # Determine step ID
            # For transformations (Request/Response), use content_id (references transformation)
            # For other activities, use activity_id (references endpoint/script)
            if step_type == 700:
                step_id = content_id if content_id else activity_id
            else:
                step_id = activity_id if activity_id else content_id
            
            if step_id:
                steps.append({
                    "id": step_id,
                    "type": step_type
                })
        
        return steps
    
    def _determine_step_type(self, role: str, activity_type: str) -> int:
        """
        Determine step type (400, 500, 700) from JPK activity role and type.
        
        Mapping:
        - Request/Response role → Type 700 (transformation)
        - Script role → Type 400 (script component) or Type 500 if it's an endpoint
        - Source/Target role → Type 500 (endpoint)
        - NetSuite Function/Web Service Call → Type 500 (endpoint)
        
        Args:
            role: JPK activity role (e.g., "Script", "Request", "Response", "Source", "Target")
            activity_type: JPK activity type (string number like "23", "2", "4")
            
        Returns:
            Step type (400, 500, or 700)
        """
        role_lower = role.lower() if role else ""
        
        # Request/Response activities map to transformations (Type 700)
        if role_lower in ["request", "response"]:
            return 700
        
        # Source/Target activities map to endpoints (Type 500)
        if role_lower in ["source", "target"]:
            return 500
        
        # Script activities - default to Type 400 (script component)
        # Some scripts may reference endpoints, but we'll use 400 as default
        if role_lower == "script":
            # Activity type "23" is Script, which maps to Type 400
            return 400
        
        # NetSuite Function, Web Service Call, etc. map to Type 500 (endpoint)
        # These are typically connector function calls
        return 500
    
    def _create_outcomes(self, failure_operation_id: str) -> List[Dict[str, Any]]:
        """
        Create outcomes array for operation failure handler.

        Args:
            failure_operation_id: ID of operation to call on failure

        Returns:
            List of outcome dictionaries
        """
        # Create outcome for failure handler
        # outcomeType 200 matches the baseline format for failure operation links
        # This creates the visual red lines in Jitterbit linking to failure handlers
        return [
            {
                "outcomeType": 200,  # Matches baseline format
                "operationId": failure_operation_id,
                "id": str(uuid.uuid4())  # Generate outcome ID
            }
        ]

