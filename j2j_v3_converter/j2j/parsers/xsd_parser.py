"""
XSD parser for J2J v327.

This module handles parsing of XSD schema files within JPK archives,
extracting field hierarchies and creating rich schema documents.
"""

import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional

from ..utils.exceptions import JPKParsingError
from ..utils.constants import XML_SCHEMA_NAMESPACE


class XSDParser:
    """
    XSD parser for extracting schema information from JPK files.

    This class provides methods to parse XSD files within JPK archives
    and create structured schema documents for transformations.
    """

    def __init__(self):
        """Initialize XSD parser."""
        self.namespace = XML_SCHEMA_NAMESPACE

    def parse_structure(self, jpk_path: str, xsd_filename: str) -> Dict[str, Any]:
        """
        Enhanced XSD parsing that extracts complete field hierarchies.

        Extracts complex types, elements, and their relationships from
        XSD files within JPK archives.

        Args:
            jpk_path: Path to the JPK file
            xsd_filename: Name of the XSD file to parse

        Returns:
            Dictionary containing parsed XSD structure with fields,
            target namespace, and counts

        Raises:
            JPKParsingError: If JPK file cannot be read or XSD parsing fails
        """
        try:
            with zipfile.ZipFile(jpk_path, 'r') as jpk:
                # Find the XSD file
                xsd_files = [f for f in jpk.namelist() if f.endswith(xsd_filename)]

                if not xsd_files:
                    print(f"   Warning: XSD file {xsd_filename} not found in JPK")
                    return {}

                # Read and parse XSD content
                try:
                    xsd_content = jpk.read(xsd_files[0]).decode('utf-8')
                    root = ET.fromstring(xsd_content)
                except ET.ParseError as e:
                    raise JPKParsingError(f"Invalid XML in XSD file {xsd_filename}: {e}")
                except UnicodeDecodeError as e:
                    raise JPKParsingError(f"Cannot decode XSD file {xsd_filename}: {e}")

                # Extract target namespace
                target_namespace = root.get('targetNamespace', '')

                # Extract all elements and complex types
                elements = root.findall('.//xs:element', self.namespace)
                complex_types = root.findall('.//xs:complexType', self.namespace)

                # Build field structure
                fields = self._build_field_structure(elements)

                return {
                    'target_namespace': target_namespace,
                    'fields': fields,
                    'element_count': len(elements),
                    'complex_type_count': len(complex_types)
                }

        except zipfile.BadZipFile:
            raise JPKParsingError(f"Invalid JPK file: {jpk_path}")
        except FileNotFoundError:
            raise JPKParsingError(f"JPK file not found: {jpk_path}")
        except Exception as e:
            print(f"   Error parsing enhanced XSD {xsd_filename}: {e}")
            return {}

    def create_schema_document(self, name: str, xsd_structure: Dict[str, Any],
                             root_element: str = None) -> Dict[str, Any]:
        """
        Create a rich schema document with proper field structure for transformations.

        Args:
            name: Name for the schema document
            xsd_structure: Parsed XSD structure from parse_structure()
            root_element: Optional root element name

        Returns:
            Dictionary representing rich schema document
        """
        if not xsd_structure or 'fields' not in xsd_structure:
            # Fallback to basic schema
            return self._create_fallback_schema(name, root_element)

        # Use the parsed XSD structure
        fields = xsd_structure['fields']

        # Find root element if specified
        root_field = self._find_root_field(fields, root_element)

        if root_field:
            return {
                "name": name,
                "document": {
                    "root": {
                        "N": root_field.get('N', root_element or 'root'),
                        "MN": 1,
                        "MX": 1,
                        "C": root_field.get('C', fields),  # Use children if available
                        "I": 0,
                        "L": 0,
                        "O": {"generatedAsInode": True}
                    }
                }
            }
        else:
            # Fallback schema using all fields
            return {
                "name": name,
                "document": {
                    "root": {
                        "N": root_element or "root",
                        "MN": 1,
                        "MX": 1,
                        "C": fields,
                        "I": 0,
                        "L": 0,
                        "O": {"generatedAsInode": True}
                    }
                }
            }

    def _build_field_structure(self, elements: List[ET.Element]) -> List[Dict[str, Any]]:
        """
        Build field structure from XSD elements.

        Args:
            elements: List of XSD element nodes

        Returns:
            List of field dictionaries
        """
        fields = []
        field_index = 1

        # Process root elements
        for element in elements:
            if element.get('name'):  # Only named elements
                field = {
                    "N": element.get('name'),
                    "T": self._extract_type(element.get('type', 'string')),
                    "MN": int(element.get('minOccurs', '0')),
                    "MX": self._parse_max_occurs(element.get('maxOccurs', '1')),
                    "NIL": True,
                    "I": field_index,
                    "L": 2
                }

                # Check for complex type children
                complex_type = element.find('.//xs:complexType', self.namespace)
                if complex_type is not None:
                    children = self._extract_child_elements(complex_type)
                    if children:
                        field["C"] = children

                fields.append(field)
                field_index += 1

        return fields

    def _extract_child_elements(self, complex_type: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract child elements from complex type.

        Args:
            complex_type: Complex type element

        Returns:
            List of child field dictionaries
        """
        children = []
        child_elements = complex_type.findall('.//xs:element', self.namespace)

        child_index = 1
        for child_elem in child_elements:
            if child_elem.get('name'):
                child_field = {
                    "N": child_elem.get('name'),
                    "T": self._extract_type(child_elem.get('type', 'string')),
                    "MN": int(child_elem.get('minOccurs', '0')),
                    "MX": self._parse_max_occurs(child_elem.get('maxOccurs', '1')),
                    "NIL": True,
                    "I": child_index,
                    "L": 3
                }
                children.append(child_field)
                child_index += 1

        return children

    def _extract_type(self, type_attr: str) -> str:
        """
        Extract type name, removing namespace prefix.

        Args:
            type_attr: Type attribute value

        Returns:
            Clean type name
        """
        if type_attr:
            return type_attr.split(':')[-1]  # Remove namespace prefix
        return 'string'

    def _parse_max_occurs(self, max_occurs: str) -> int:
        """
        Parse maxOccurs attribute.

        Args:
            max_occurs: maxOccurs attribute value

        Returns:
            Parsed integer value, -1 for 'unbounded'
        """
        if max_occurs == 'unbounded':
            return -1
        try:
            return int(max_occurs)
        except (ValueError, TypeError):
            return 1

    def _find_root_field(self, fields: List[Dict[str, Any]],
                        root_element: str = None) -> Optional[Dict[str, Any]]:
        """
        Find root field in fields list.

        Args:
            fields: List of field dictionaries
            root_element: Optional root element name to search for

        Returns:
            Root field dictionary or None
        """
        if root_element:
            for field in fields:
                if field.get('N') == root_element:
                    return field

        # Use the first field as root if no specific root element found
        return fields[0] if fields else None

    def _create_fallback_schema(self, name: str, root_element: str = None) -> Dict[str, Any]:
        """
        Create fallback schema when XSD parsing fails.

        Args:
            name: Schema name
            root_element: Optional root element name

        Returns:
            Basic schema document
        """
        return {
            "name": name,
            "document": {
                "root": {
                    "N": root_element or "root",
                    "MN": 1,
                    "MX": 1,
                    "C": [
                        {"NIL": True, "MN": 0, "MX": 1, "N": "Id", "T": "string", "I": 1, "L": 2},
                        {"NIL": True, "MN": 0, "MX": 1, "N": "Name", "T": "string", "I": 2, "L": 2}
                    ],
                    "I": 0,
                    "L": 0,
                    "O": {"generatedAsInode": True}
                }
            }
        }
