"""Syslog entry parsing, filtering, and formatting for CLI display."""

from __future__ import annotations

import datetime
import json
import posixpath
import re
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Any, Callable, Iterator, List, Optional, Pattern, TextIO


class SyslogLevel(IntEnum):
    """Log severity levels matching iOS syslog."""

    DEBUG = 0
    INFO = 1
    NOTICE = 2
    USER_ACTION = 3
    ERROR = 4
    FAULT = 5

    @classmethod
    def from_name(cls, name: str) -> "SyslogLevel":
        """Get level by name (case-insensitive)."""
        name_upper = name.upper()
        for level in cls:
            if level.name == name_upper:
                return level
        return cls.DEBUG


class OutputFormat(str, Enum):
    """Output format for syslog entries."""

    TEXT = "text"
    JSON = "json"


@dataclass
class SyslogLabel:
    """Label containing subsystem and category."""

    subsystem: str
    category: str

    def __str__(self) -> str:
        return f"[{self.subsystem}][{self.category}]"


@dataclass
class SyslogEntry:
    """A parsed syslog entry with all relevant fields."""

    timestamp: datetime.datetime
    level: SyslogLevel
    pid: int
    filename: str
    message: str
    image_name: str = ""
    image_offset: int = 0
    label: Optional[SyslogLabel] = None

    @property
    def process_name(self) -> str:
        """Extract process name from filename."""
        return posixpath.basename(self.filename) if self.filename else ""

    @property
    def short_image_name(self) -> str:
        """Extract short image name."""
        return posixpath.basename(self.image_name) if self.image_name else ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.name,
            "pid": self.pid,
            "filename": self.filename,
            "message": self.message,
            "image_name": self.image_name,
            "image_offset": self.image_offset,
        }
        if self.label:
            result["label"] = {
                "subsystem": self.label.subsystem,
                "category": self.label.category,
            }
        else:
            result["label"] = None
        return result


@dataclass
class SyslogFilter:
    """Filter configuration for syslog entries."""

    pid: int = -1
    process_name: Optional[str] = None
    match: List[str] = field(default_factory=list)
    match_insensitive: List[str] = field(default_factory=list)
    invert_match: List[str] = field(default_factory=list)
    invert_match_insensitive: List[str] = field(default_factory=list)
    regex_patterns: List[Pattern[str]] = field(default_factory=list)
    exclude_debug: bool = False
    exclude_info: bool = False
    start_after: Optional[str] = None

    # Internal state
    _started: bool = field(default=True, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize state based on start_after."""
        self._started = self.start_after is None

    def add_regex(self, pattern: str, case_insensitive: bool = False) -> None:
        """Add a regex pattern to the filter.

        Args:
            pattern: Regex pattern string.
            case_insensitive: Whether to match case-insensitively.
        """
        flags = re.DOTALL
        if case_insensitive:
            flags |= re.IGNORECASE
        compiled = re.compile(f".*({pattern}).*", flags)
        self.regex_patterns.append(compiled)

    def matches_entry(self, entry: SyslogEntry) -> bool:
        """Check if an entry passes all filter criteria.

        Args:
            entry: The syslog entry to check.

        Returns:
            True if the entry should be included, False to skip.
        """
        # PID filter
        if self.pid != -1 and entry.pid != self.pid:
            return False

        # Process name filter
        if self.process_name and entry.process_name != self.process_name:
            return False

        # Level filters
        if self.exclude_debug and entry.level == SyslogLevel.DEBUG:
            return False
        if self.exclude_info and entry.level == SyslogLevel.INFO:
            return False

        return True

    def matches_text(self, text: str) -> bool:
        """Check if formatted text passes text-based filters.

        Args:
            text: The formatted log line to check.

        Returns:
            True if the text passes all filters.
        """
        # Handle start_after
        if not self._started:
            if self.start_after and self.start_after in text:
                self._started = True
                # Continue to check other filters for the marker line
            else:
                return False

        # Invert match (exclude if any match)
        for pattern in self.invert_match:
            if pattern in text:
                return False

        text_lower = text.lower()
        for pattern in self.invert_match_insensitive:
            if pattern.lower() in text_lower:
                return False

        # Must match all (conjunction)
        for pattern in self.match:
            if pattern not in text:
                return False

        for pattern in self.match_insensitive:
            if pattern.lower() not in text_lower:
                return False

        # Regex patterns (any match - disjunction)
        if self.regex_patterns:
            if not any(r.search(text) for r in self.regex_patterns):
                return False

        return True

    def filter_entries(
        self, entries: Iterator[SyslogEntry], formatter: "SyslogFormatter"
    ) -> Iterator[tuple[SyslogEntry, str]]:
        """Filter and format entries.

        Args:
            entries: Iterator of syslog entries.
            formatter: Formatter for generating text output.

        Yields:
            Tuples of (entry, formatted_text) for matching entries.
        """
        for entry in entries:
            if not self.matches_entry(entry):
                continue

            # Format without color for filtering
            text = formatter.format_text(entry, color=False)

            if not self.matches_text(text):
                continue

            yield entry, text


# ANSI color codes
class _Colors:
    """ANSI terminal color codes."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    # Foreground colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


def _colorize(text: str, color: str) -> str:
    """Apply ANSI color to text."""
    return f"{color}{text}{_Colors.RESET}"


def _bold_underline(text: str) -> str:
    """Make text bold and underlined."""
    return f"{_Colors.BOLD}{_Colors.UNDERLINE}{text}{_Colors.RESET}"


@dataclass
class SyslogFormatter:
    """Formats syslog entries for display."""

    include_label: bool = False
    include_image_offset: bool = False
    use_color: bool = True

    # Level to color mapping
    _level_colors: dict[SyslogLevel, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        """Initialize level colors."""
        self._level_colors = {
            SyslogLevel.DEBUG: _Colors.GREEN,
            SyslogLevel.INFO: _Colors.WHITE,
            SyslogLevel.NOTICE: _Colors.WHITE,
            SyslogLevel.USER_ACTION: _Colors.WHITE,
            SyslogLevel.ERROR: _Colors.RED,
            SyslogLevel.FAULT: _Colors.RED,
        }

    def format_json(self, entry: SyslogEntry) -> str:
        """Format entry as JSON line.

        Args:
            entry: Syslog entry to format.

        Returns:
            JSON string.
        """
        return json.dumps(entry.to_dict(), ensure_ascii=False)

    def format_text(self, entry: SyslogEntry, color: bool = True) -> str:
        """Format entry as human-readable text.

        Args:
            entry: Syslog entry to format.
            color: Whether to apply terminal colors.

        Returns:
            Formatted text line.
        """
        use_color = color and self.use_color

        # Components
        timestamp_str = str(entry.timestamp)
        process = entry.process_name
        image = entry.short_image_name
        offset_str = ""
        if self.include_image_offset and image:
            offset_str = f"+0x{entry.image_offset:x}"
        pid_str = str(entry.pid)
        level_str = entry.level.name
        message = entry.message
        label_str = ""
        if self.include_label and entry.label:
            label_str = f" {entry.label}"

        if use_color:
            level_color = self._level_colors.get(entry.level, _Colors.WHITE)

            timestamp_str = _colorize(timestamp_str, _Colors.GREEN)
            process = _colorize(process, _Colors.MAGENTA)
            if image:
                image = _colorize(image, _Colors.MAGENTA)
            if offset_str:
                offset_str = _colorize(offset_str, _Colors.BLUE)
            pid_str = _colorize(pid_str, _Colors.CYAN)
            level_str = _colorize(level_str, level_color)
            message = _colorize(message, level_color)
            if label_str:
                label_str = _colorize(label_str, _Colors.CYAN)

        return (
            f"{timestamp_str} {process}{{{image}{offset_str}}}[{pid_str}] "
            f"<{level_str}>: {message}{label_str}"
        )

    def highlight_matches(
        self,
        text: str,
        match: List[str],
        match_insensitive: List[str],
        regex_patterns: List[Pattern[str]],
    ) -> str:
        """Highlight matched text patterns.

        Args:
            text: The formatted text line.
            match: Case-sensitive patterns to highlight.
            match_insensitive: Case-insensitive patterns to highlight.
            regex_patterns: Regex patterns to highlight.

        Returns:
            Text with highlighted matches.
        """
        # Highlight exact matches
        for pattern in match:
            if pattern in text:
                text = text.replace(pattern, _bold_underline(pattern))

        # Highlight case-insensitive matches
        for pattern in match_insensitive:
            lower = pattern.lower()
            idx = text.lower().find(lower)
            if idx != -1:
                original = text[idx : idx + len(pattern)]
                text = text[:idx] + _bold_underline(original) + text[idx + len(pattern) :]

        # Highlight regex matches
        for regex in regex_patterns:
            match_obj = regex.search(text)
            if match_obj and match_obj.groups():
                group = match_obj.group(1)
                text = text.replace(group, _bold_underline(group))

        return text


def emit_entry(
    entry: SyslogEntry,
    formatter: SyslogFormatter,
    filter_config: SyslogFilter,
    output_format: OutputFormat = OutputFormat.TEXT,
    output_file: Optional[TextIO] = None,
    print_fn: Callable[[str], None] = print,
) -> None:
    """Format and emit a syslog entry.

    Args:
        entry: The syslog entry to emit.
        formatter: Formatter configuration.
        filter_config: Filter configuration (for highlight patterns).
        output_format: Output format (TEXT or JSON).
        output_file: Optional file to write to (in addition to stdout).
        print_fn: Function to use for printing (default: print).
    """
    if output_format == OutputFormat.JSON:
        line = formatter.format_json(entry)
    else:
        line = formatter.format_text(entry, color=formatter.use_color)
        if formatter.use_color:
            line = formatter.highlight_matches(
                line,
                filter_config.match,
                filter_config.match_insensitive,
                filter_config.regex_patterns,
            )

    print_fn(line)

    if output_file:
        # Write without colors to file
        if output_format == OutputFormat.JSON:
            plain_line = line
        else:
            plain_line = formatter.format_text(entry, color=False)
        output_file.write(plain_line + "\n")
        output_file.flush()
