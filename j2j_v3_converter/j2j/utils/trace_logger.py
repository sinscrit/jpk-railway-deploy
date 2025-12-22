"""
Trace Logger Utility for J2J Converter

This module provides configurable trace logging for the JPK to JSON conversion process.
It supports multiple verbosity levels and outputs logs in Markdown format.

Created: 2025-12-06
Purpose: Document conversion decisions, source data, and reasoning for debugging
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class VerbosityLevel(Enum):
    """Verbosity levels for trace logging."""
    MINIMAL = 1
    NORMAL = 2
    DETAILED = 3
    DEBUG = 4
    
    @classmethod
    def from_string(cls, level: str) -> 'VerbosityLevel':
        """Convert string to VerbosityLevel enum.
        
        Args:
            level: String representation of verbosity level
            
        Returns:
            VerbosityLevel enum value
            
        Raises:
            ValueError: If level string is not recognized
        """
        level_map = {
            'minimal': cls.MINIMAL,
            'normal': cls.NORMAL,
            'detailed': cls.DETAILED,
            'debug': cls.DEBUG
        }
        level_lower = level.lower()
        if level_lower not in level_map:
            raise ValueError(f"Unknown verbosity level: {level}. Must be one of: {list(level_map.keys())}")
        return level_map[level_lower]


class TraceLogger:
    """
    Trace logger for documenting conversion decisions in Markdown format.
    
    Buffers log entries and writes them to a file at the end of conversion.
    Supports configurable verbosity levels to control output detail.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        verbosity: VerbosityLevel = VerbosityLevel.NORMAL,
        output_directory: Path = Path("trace_logs"),
        log_file_name: Optional[str] = None
    ):
        """Initialize the trace logger.
        
        Args:
            enabled: Whether trace logging is enabled
            verbosity: Verbosity level for logging
            output_directory: Directory to write trace log files
            log_file_name: Optional specific filename for the log
        """
        self.enabled = enabled
        self.verbosity = verbosity
        self.output_directory = Path(output_directory)
        self.log_file_name = log_file_name
        self.entries: List[Dict[str, Any]] = []
        self.start_time = datetime.now()
    
    def log_decision(
        self,
        decision: str,
        context: Dict[str, Any] = None,
        verbosity_required: VerbosityLevel = VerbosityLevel.NORMAL
    ) -> None:
        """Log a conversion decision.
        
        Args:
            decision: Description of the decision made
            context: Additional context data
            verbosity_required: Minimum verbosity level required to log this entry
        """
        if not self.enabled or verbosity_required.value > self.verbosity.value:
            return
        
        self.entries.append({
            'type': 'decision',
            'timestamp': datetime.now().isoformat(),
            'decision': decision,
            'context': context or {},
            'verbosity': verbosity_required.name
        })
    
    def log_source_data(
        self,
        source_type: str,
        source_data: Any,
        verbosity_required: VerbosityLevel = VerbosityLevel.DETAILED
    ) -> None:
        """Log source data used in a decision.
        
        Args:
            source_type: Type/name of the source data
            source_data: The actual source data
            verbosity_required: Minimum verbosity level required to log this entry
        """
        if not self.enabled or verbosity_required.value > self.verbosity.value:
            return
        
        self.entries.append({
            'type': 'source_data',
            'timestamp': datetime.now().isoformat(),
            'source_type': source_type,
            'data': source_data,
            'verbosity': verbosity_required.name
        })
    
    def log_reasoning(
        self,
        reasoning: str,
        context: Dict[str, Any] = None,
        verbosity_required: VerbosityLevel = VerbosityLevel.DETAILED
    ) -> None:
        """Log reasoning behind a decision.
        
        Args:
            reasoning: Explanation of the reasoning
            context: Additional context data
            verbosity_required: Minimum verbosity level required to log this entry
        """
        if not self.enabled or verbosity_required.value > self.verbosity.value:
            return
        
        self.entries.append({
            'type': 'reasoning',
            'timestamp': datetime.now().isoformat(),
            'reasoning': reasoning,
            'context': context or {},
            'verbosity': verbosity_required.name
        })
    
    def write_log(self, jpk_file: str, output_file: str) -> Optional[Path]:
        """Write the buffered log entries to a Markdown file.
        
        Args:
            jpk_file: Path to the source JPK file
            output_file: Path to the output JSON file
            
        Returns:
            Path to the written log file, or None if logging is disabled
        """
        if not self.enabled:
            return None
        
        # Create output directory if it doesn't exist
        self.output_directory.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        jpk_stem = Path(jpk_file).stem
        if self.log_file_name:
            filename = self.log_file_name
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{jpk_stem}_{timestamp}.md"
        
        log_path = self.output_directory / filename
        
        # Generate Markdown content
        content = self._generate_markdown(jpk_file, output_file)
        
        # Write to file
        log_path.write_text(content, encoding='utf-8')
        
        return log_path
    
    def _generate_markdown(self, jpk_file: str, output_file: str) -> str:
        """Generate Markdown content from buffered entries.
        
        Args:
            jpk_file: Path to the source JPK file
            output_file: Path to the output JSON file
            
        Returns:
            Markdown formatted string
        """
        lines = []
        
        # Header
        lines.append(f"# Trace Log: {Path(jpk_file).name} → {Path(output_file).name}")
        lines.append("")
        lines.append(f"**Generated**: {datetime.now().isoformat()}")
        lines.append(f"**Start Time**: {self.start_time.isoformat()}")
        lines.append(f"**Verbosity Level**: {self.verbosity.name}")
        lines.append(f"**Total Entries**: {len(self.entries)}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Group entries by type
        decisions = [e for e in self.entries if e['type'] == 'decision']
        source_data = [e for e in self.entries if e['type'] == 'source_data']
        reasoning = [e for e in self.entries if e['type'] == 'reasoning']
        
        # Decisions section
        if decisions:
            lines.append("## Decisions")
            lines.append("")
            for i, entry in enumerate(decisions, 1):
                lines.append(f"### {i}. {entry['decision']}")
                lines.append(f"- **Time**: {entry['timestamp']}")
                lines.append(f"- **Level**: {entry['verbosity']}")
                if entry['context']:
                    lines.append("- **Context**:")
                    for key, value in entry['context'].items():
                        lines.append(f"  - {key}: `{value}`")
                lines.append("")
        
        # Source Data section
        if source_data:
            lines.append("## Source Data")
            lines.append("")
            for i, entry in enumerate(source_data, 1):
                lines.append(f"### {i}. {entry['source_type']}")
                lines.append(f"- **Time**: {entry['timestamp']}")
                lines.append(f"- **Level**: {entry['verbosity']}")
                lines.append("- **Data**:")
                lines.append("```json")
                import json
                try:
                    lines.append(json.dumps(entry['data'], indent=2, default=str))
                except:
                    lines.append(str(entry['data']))
                lines.append("```")
                lines.append("")
        
        # Reasoning section
        if reasoning:
            lines.append("## Reasoning")
            lines.append("")
            for i, entry in enumerate(reasoning, 1):
                lines.append(f"### {i}. {entry['reasoning']}")
                lines.append(f"- **Time**: {entry['timestamp']}")
                lines.append(f"- **Level**: {entry['verbosity']}")
                if entry['context']:
                    lines.append("- **Context**:")
                    for key, value in entry['context'].items():
                        lines.append(f"  - {key}: `{value}`")
                lines.append("")
        
        # Summary
        lines.append("---")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Decisions logged**: {len(decisions)}")
        lines.append(f"- **Source data entries**: {len(source_data)}")
        lines.append(f"- **Reasoning entries**: {len(reasoning)}")
        
        return "\n".join(lines)

