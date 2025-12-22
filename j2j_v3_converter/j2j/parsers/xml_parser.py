"""
XML parser utilities for J2J v327.

This module provides common XML parsing utilities for reuse across
JPK parsing modules, with proper error handling and context management.
"""

import xml.etree.ElementTree as ET
import zipfile
from contextlib import contextmanager
from typing import Optional, Dict, Any, Generator

from ..utils.exceptions import JPKParsingError


class XMLParser:
    """
    XML parser utilities for JPK file processing.

    This class provides reusable methods for common XML operations
    when parsing JPK files, including safe parsing and header extraction.
    """

    def __init__(self):
        """Initialize XML parser utilities."""
        pass

    @contextmanager
    def open_jpk(self, jpk_path: str) -> Generator[zipfile.ZipFile, None, None]:
        """
        Context manager for safely opening JPK files.

        Args:
            jpk_path: Path to JPK file

        Yields:
            ZipFile object for reading

        Raises:
            JPKParsingError: If JPK file cannot be opened
        """
        try:
            with zipfile.ZipFile(jpk_path, 'r') as jpk:
                yield jpk
        except zipfile.BadZipFile:
            raise JPKParsingError(f"Invalid JPK file: {jpk_path}")
        except FileNotFoundError:
            raise JPKParsingError(f"JPK file not found: {jpk_path}")
        except Exception as e:
            raise JPKParsingError(f"Error opening JPK file {jpk_path}: {e}")

    def parse_xml_from_jpk(self, jpk: zipfile.ZipFile, file_path: str) -> Optional[ET.Element]:
        """
        Parse XML content from a file within JPK archive.

        Args:
            jpk: Open ZipFile object
            file_path: Path to XML file within JPK

        Returns:
            Parsed XML root element or None if parsing fails

        Raises:
            JPKParsingError: If XML parsing fails critically
        """
        try:
            content = jpk.read(file_path).decode('utf-8')
            return ET.fromstring(content)
        except UnicodeDecodeError as e:
            raise JPKParsingError(f"Cannot decode XML file {file_path}: {e}")
        except ET.ParseError as e:
            raise JPKParsingError(f"Invalid XML in file {file_path}: {e}")
        except KeyError:
            # File not found in JPK - return None for graceful handling
            return None
        except Exception as e:
            raise JPKParsingError(f"Error reading XML file {file_path}: {e}")

    def safe_parse_xml(self, xml_content: str, source_info: str = "XML") -> Optional[ET.Element]:
        """
        Safely parse XML content with error handling.

        Args:
            xml_content: XML content as string
            source_info: Information about XML source for error messages

        Returns:
            Parsed XML root element or None if parsing fails
        """
        try:
            return ET.fromstring(xml_content)
        except ET.ParseError as e:
            print(f"   Warning: Invalid XML in {source_info}: {e}")
            return None
        except Exception as e:
            print(f"   Warning: Error parsing XML from {source_info}: {e}")
            return None

    def extract_header_info(self, root: ET.Element) -> Dict[str, Optional[str]]:
        """
        Extract common header information from XML root element.

        This method extracts the standard ID and Name attributes from
        Header elements commonly found in JPK component files.

        Args:
            root: XML root element

        Returns:
            Dictionary with 'id' and 'name' keys (values may be None)
        """
        header = root.find('Header')
        if header is None:
            return {'id': None, 'name': None}

        return {
            'id': header.attrib.get('ID'),
            'name': header.attrib.get('Name')
        }

    def get_header_attribute(self, root: ET.Element, attribute: str,
                           default: Optional[str] = None) -> Optional[str]:
        """
        Get specific attribute from Header element.

        Args:
            root: XML root element
            attribute: Attribute name to retrieve
            default: Default value if attribute not found

        Returns:
            Attribute value or default
        """
        header = root.find('Header')
        if header is None:
            return default

        return header.attrib.get(attribute, default)

    def find_component_files(self, jpk: zipfile.ZipFile, component_type: str) -> list:
        """
        Find all XML files for a specific component type in JPK.

        Args:
            jpk: Open ZipFile object
            component_type: Component type to search for (e.g., 'Source', 'Target')

        Returns:
            List of file paths matching the component type
        """
        file_list = jpk.namelist()
        return [f for f in file_list if f'/{component_type}/' in f and f.endswith('.xml')]

    def extract_properties(self, root: ET.Element) -> Dict[str, str]:
        """
        Extract properties from XML Properties section.

        Args:
            root: XML root element

        Returns:
            Dictionary of property key-value pairs
        """
        properties = {}
        properties_element = root.find('Properties')

        if properties_element is not None:
            for item in properties_element.findall('Item'):
                key = item.get('key', '')
                value = item.get('value', '')
                if key:
                    properties[key] = value

        return properties

    def validate_xml_structure(self, root: ET.Element, required_elements: list) -> bool:
        """
        Validate that XML has required elements.

        Args:
            root: XML root element
            required_elements: List of required element names

        Returns:
            True if all required elements are present, False otherwise
        """
        for element_name in required_elements:
            if root.find(element_name) is None:
                return False
        return True

    def get_component_type_from_path(self, file_path: str) -> Optional[str]:
        """
        Extract component type from JPK file path.

        Args:
            file_path: Path within JPK (e.g., 'Data/Source/component.xml')

        Returns:
            Component type string or None if not determinable
        """
        path_parts = file_path.split('/')
        if len(path_parts) >= 3 and path_parts[0] == 'Data':
            return path_parts[1]
        return None
