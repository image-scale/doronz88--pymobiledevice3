"""Tests for CLI syslog module."""

import datetime
import json
import re
from io import StringIO

import pytest

from iosdevice.cli.syslog import (
    SyslogEntry,
    SyslogLevel,
    SyslogLabel,
    SyslogFilter,
    SyslogFormatter,
    OutputFormat,
    emit_entry,
    _colorize,
    _bold_underline,
    _Colors,
)


class TestSyslogLevel:
    """Tests for SyslogLevel enumeration."""

    def test_level_values(self):
        """Should have expected integer values."""
        assert SyslogLevel.DEBUG == 0
        assert SyslogLevel.INFO == 1
        assert SyslogLevel.NOTICE == 2
        assert SyslogLevel.USER_ACTION == 3
        assert SyslogLevel.ERROR == 4
        assert SyslogLevel.FAULT == 5

    def test_from_name_valid(self):
        """Should parse valid level names."""
        assert SyslogLevel.from_name("DEBUG") == SyslogLevel.DEBUG
        assert SyslogLevel.from_name("error") == SyslogLevel.ERROR
        assert SyslogLevel.from_name("Info") == SyslogLevel.INFO

    def test_from_name_invalid(self):
        """Should return DEBUG for unknown names."""
        assert SyslogLevel.from_name("unknown") == SyslogLevel.DEBUG

    def test_level_ordering(self):
        """Levels should be ordered by severity."""
        assert SyslogLevel.DEBUG < SyslogLevel.INFO
        assert SyslogLevel.INFO < SyslogLevel.ERROR
        assert SyslogLevel.ERROR < SyslogLevel.FAULT


class TestSyslogLabel:
    """Tests for SyslogLabel."""

    def test_str_format(self):
        """Should format as [subsystem][category]."""
        label = SyslogLabel(subsystem="com.apple.test", category="network")
        assert str(label) == "[com.apple.test][network]"

    def test_empty_values(self):
        """Should handle empty values."""
        label = SyslogLabel(subsystem="", category="")
        assert str(label) == "[][]"


class TestSyslogEntry:
    """Tests for SyslogEntry dataclass."""

    @pytest.fixture
    def sample_entry(self):
        """Create a sample entry for testing."""
        return SyslogEntry(
            timestamp=datetime.datetime(2024, 1, 15, 10, 30, 45),
            level=SyslogLevel.INFO,
            pid=1234,
            filename="/usr/bin/myapp",
            message="Test message",
            image_name="/System/Library/Frameworks/Foundation.framework/Foundation",
            image_offset=0x1234,
            label=SyslogLabel("com.example.app", "main"),
        )

    def test_process_name(self, sample_entry):
        """Should extract process name from filename."""
        assert sample_entry.process_name == "myapp"

    def test_short_image_name(self, sample_entry):
        """Should extract short image name."""
        assert sample_entry.short_image_name == "Foundation"

    def test_process_name_empty(self):
        """Should handle empty filename."""
        entry = SyslogEntry(
            timestamp=datetime.datetime.now(),
            level=SyslogLevel.DEBUG,
            pid=0,
            filename="",
            message="",
        )
        assert entry.process_name == ""

    def test_to_dict(self, sample_entry):
        """Should convert to dictionary."""
        d = sample_entry.to_dict()

        assert d["timestamp"] == "2024-01-15T10:30:45"
        assert d["level"] == "INFO"
        assert d["pid"] == 1234
        assert d["filename"] == "/usr/bin/myapp"
        assert d["message"] == "Test message"
        assert d["label"]["subsystem"] == "com.example.app"
        assert d["label"]["category"] == "main"

    def test_to_dict_no_label(self):
        """Should handle None label."""
        entry = SyslogEntry(
            timestamp=datetime.datetime.now(),
            level=SyslogLevel.DEBUG,
            pid=1,
            filename="test",
            message="test",
        )
        d = entry.to_dict()
        assert d["label"] is None


class TestSyslogFilter:
    """Tests for SyslogFilter."""

    @pytest.fixture
    def entry(self):
        """Create test entry."""
        return SyslogEntry(
            timestamp=datetime.datetime.now(),
            level=SyslogLevel.INFO,
            pid=100,
            filename="/usr/bin/springboard",
            message="App launched",
        )

    def test_matches_any_pid(self, entry):
        """Should match any PID when filter is -1."""
        filter_config = SyslogFilter(pid=-1)
        assert filter_config.matches_entry(entry) is True

    def test_matches_specific_pid(self, entry):
        """Should filter by specific PID."""
        filter_config = SyslogFilter(pid=100)
        assert filter_config.matches_entry(entry) is True

        filter_config = SyslogFilter(pid=200)
        assert filter_config.matches_entry(entry) is False

    def test_matches_process_name(self, entry):
        """Should filter by process name."""
        filter_config = SyslogFilter(process_name="springboard")
        assert filter_config.matches_entry(entry) is True

        filter_config = SyslogFilter(process_name="other")
        assert filter_config.matches_entry(entry) is False

    def test_exclude_debug(self):
        """Should exclude debug entries when requested."""
        debug_entry = SyslogEntry(
            timestamp=datetime.datetime.now(),
            level=SyslogLevel.DEBUG,
            pid=1,
            filename="test",
            message="debug",
        )

        filter_config = SyslogFilter(exclude_debug=True)
        assert filter_config.matches_entry(debug_entry) is False

        filter_config = SyslogFilter(exclude_debug=False)
        assert filter_config.matches_entry(debug_entry) is True

    def test_exclude_info(self, entry):
        """Should exclude info entries when requested."""
        filter_config = SyslogFilter(exclude_info=True)
        assert filter_config.matches_entry(entry) is False

        filter_config = SyslogFilter(exclude_info=False)
        assert filter_config.matches_entry(entry) is True

    def test_matches_text_simple(self):
        """Should match simple text patterns."""
        filter_config = SyslogFilter(match=["error"])
        assert filter_config.matches_text("An error occurred") is True
        assert filter_config.matches_text("All good") is False

    def test_matches_text_insensitive(self):
        """Should match case-insensitively."""
        filter_config = SyslogFilter(match_insensitive=["ERROR"])
        assert filter_config.matches_text("An error occurred") is True
        assert filter_config.matches_text("ERROR: fail") is True
        assert filter_config.matches_text("All good") is False

    def test_invert_match(self):
        """Should exclude lines with inverted patterns."""
        filter_config = SyslogFilter(invert_match=["debug"])
        assert filter_config.matches_text("info message") is True
        assert filter_config.matches_text("debug message") is False

    def test_invert_match_insensitive(self):
        """Should exclude lines case-insensitively."""
        filter_config = SyslogFilter(invert_match_insensitive=["DEBUG"])
        assert filter_config.matches_text("info message") is True
        assert filter_config.matches_text("Debug message") is False

    def test_conjunction_match(self):
        """All match patterns must be present."""
        filter_config = SyslogFilter(match=["error", "network"])
        assert filter_config.matches_text("network error occurred") is True
        assert filter_config.matches_text("error occurred") is False
        assert filter_config.matches_text("network connected") is False

    def test_add_regex(self):
        """Should add and use regex patterns."""
        filter_config = SyslogFilter()
        filter_config.add_regex(r"error_\d+")
        assert filter_config.matches_text("Got error_123 from server") is True
        assert filter_config.matches_text("Got error from server") is False

    def test_add_regex_insensitive(self):
        """Should add case-insensitive regex."""
        filter_config = SyslogFilter()
        filter_config.add_regex(r"error", case_insensitive=True)
        assert filter_config.matches_text("ERROR: failed") is True
        assert filter_config.matches_text("Error occurred") is True

    def test_start_after(self):
        """Should skip lines until start_after is seen."""
        filter_config = SyslogFilter(start_after="BEGIN")

        assert filter_config.matches_text("early message") is False
        assert filter_config.matches_text("BEGIN marker") is True
        assert filter_config.matches_text("after message") is True

    def test_filter_entries(self, entry):
        """Should filter and format entries."""
        entries = [entry]
        formatter = SyslogFormatter(use_color=False)
        filter_config = SyslogFilter()

        results = list(filter_config.filter_entries(iter(entries), formatter))
        assert len(results) == 1
        assert results[0][0] is entry
        assert "springboard" in results[0][1]


class TestSyslogFormatter:
    """Tests for SyslogFormatter."""

    @pytest.fixture
    def entry(self):
        """Create test entry."""
        return SyslogEntry(
            timestamp=datetime.datetime(2024, 1, 15, 10, 30, 45),
            level=SyslogLevel.ERROR,
            pid=42,
            filename="/usr/bin/myprocess",
            message="Something failed",
            image_name="/lib/libtest.dylib",
            image_offset=0xABCD,
            label=SyslogLabel("com.test", "main"),
        )

    def test_format_json(self, entry):
        """Should produce valid JSON."""
        formatter = SyslogFormatter()
        json_str = formatter.format_json(entry)

        parsed = json.loads(json_str)
        assert parsed["level"] == "ERROR"
        assert parsed["pid"] == 42
        assert parsed["message"] == "Something failed"

    def test_format_text_no_color(self, entry):
        """Should format without colors."""
        formatter = SyslogFormatter(use_color=False)
        text = formatter.format_text(entry, color=False)

        assert "2024-01-15 10:30:45" in text
        assert "myprocess" in text
        assert "42" in text
        assert "ERROR" in text
        assert "Something failed" in text

    def test_format_text_with_label(self, entry):
        """Should include label when requested."""
        formatter = SyslogFormatter(include_label=True, use_color=False)
        text = formatter.format_text(entry, color=False)

        assert "[com.test][main]" in text

    def test_format_text_without_label(self, entry):
        """Should not include label by default."""
        formatter = SyslogFormatter(include_label=False, use_color=False)
        text = formatter.format_text(entry, color=False)

        assert "[com.test]" not in text

    def test_format_text_with_image_offset(self, entry):
        """Should include image offset when requested."""
        formatter = SyslogFormatter(include_image_offset=True, use_color=False)
        text = formatter.format_text(entry, color=False)

        assert "+0xabcd" in text

    def test_format_text_with_color(self, entry):
        """Should include ANSI codes when color enabled."""
        formatter = SyslogFormatter(use_color=True)
        text = formatter.format_text(entry, color=True)

        # Should contain ANSI escape sequences
        assert "\033[" in text

    def test_highlight_matches(self):
        """Should highlight matched text."""
        formatter = SyslogFormatter()
        text = "An error occurred in the system"
        highlighted = formatter.highlight_matches(text, ["error"], [], [])

        assert _Colors.BOLD in highlighted
        assert _Colors.UNDERLINE in highlighted

    def test_highlight_insensitive(self):
        """Should highlight case-insensitive matches."""
        formatter = SyslogFormatter()
        text = "An ERROR occurred"
        highlighted = formatter.highlight_matches(text, [], ["error"], [])

        assert _Colors.BOLD in highlighted


class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_values(self):
        """Should have text and json values."""
        assert OutputFormat.TEXT.value == "text"
        assert OutputFormat.JSON.value == "json"


class TestEmitEntry:
    """Tests for emit_entry function."""

    @pytest.fixture
    def entry(self):
        """Create test entry."""
        return SyslogEntry(
            timestamp=datetime.datetime(2024, 1, 15, 10, 30, 45),
            level=SyslogLevel.INFO,
            pid=100,
            filename="/usr/bin/test",
            message="test message",
        )

    def test_emit_text(self, entry):
        """Should emit text format."""
        output = []
        formatter = SyslogFormatter(use_color=False)
        filter_config = SyslogFilter()

        emit_entry(
            entry,
            formatter,
            filter_config,
            output_format=OutputFormat.TEXT,
            print_fn=output.append,
        )

        assert len(output) == 1
        assert "test message" in output[0]

    def test_emit_json(self, entry):
        """Should emit JSON format."""
        output = []
        formatter = SyslogFormatter()
        filter_config = SyslogFilter()

        emit_entry(
            entry,
            formatter,
            filter_config,
            output_format=OutputFormat.JSON,
            print_fn=output.append,
        )

        assert len(output) == 1
        parsed = json.loads(output[0])
        assert parsed["message"] == "test message"

    def test_emit_to_file(self, entry):
        """Should write to file in addition to stdout."""
        output = []
        file_output = StringIO()
        formatter = SyslogFormatter(use_color=False)
        filter_config = SyslogFilter()

        emit_entry(
            entry,
            formatter,
            filter_config,
            output_format=OutputFormat.TEXT,
            output_file=file_output,
            print_fn=output.append,
        )

        assert len(output) == 1
        file_content = file_output.getvalue()
        assert "test message" in file_content


class TestColorHelpers:
    """Tests for color helper functions."""

    def test_colorize(self):
        """Should wrap text with color codes."""
        result = _colorize("test", _Colors.RED)
        assert result.startswith(_Colors.RED)
        assert result.endswith(_Colors.RESET)
        assert "test" in result

    def test_bold_underline(self):
        """Should apply bold and underline."""
        result = _bold_underline("test")
        assert _Colors.BOLD in result
        assert _Colors.UNDERLINE in result
        assert "test" in result


class TestSyslogFilterIterator:
    """Tests for filter iteration."""

    def test_filter_entries_by_pid(self):
        """Should filter entries by PID."""
        entries = [
            SyslogEntry(
                timestamp=datetime.datetime.now(),
                level=SyslogLevel.INFO,
                pid=100,
                filename="a",
                message="msg1",
            ),
            SyslogEntry(
                timestamp=datetime.datetime.now(),
                level=SyslogLevel.INFO,
                pid=200,
                filename="b",
                message="msg2",
            ),
        ]

        filter_config = SyslogFilter(pid=100)
        formatter = SyslogFormatter(use_color=False)

        results = list(filter_config.filter_entries(iter(entries), formatter))
        assert len(results) == 1
        assert results[0][0].pid == 100

    def test_filter_entries_by_text(self):
        """Should filter entries by text content."""
        entries = [
            SyslogEntry(
                timestamp=datetime.datetime.now(),
                level=SyslogLevel.INFO,
                pid=1,
                filename="test",
                message="error occurred",
            ),
            SyslogEntry(
                timestamp=datetime.datetime.now(),
                level=SyslogLevel.INFO,
                pid=2,
                filename="test",
                message="all good",
            ),
        ]

        filter_config = SyslogFilter(match=["error"])
        formatter = SyslogFormatter(use_color=False)

        results = list(filter_config.filter_entries(iter(entries), formatter))
        assert len(results) == 1
        assert "error" in results[0][1]
