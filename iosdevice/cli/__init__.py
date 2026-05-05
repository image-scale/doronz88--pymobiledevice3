"""CLI module for syslog commands."""

from .syslog import (
    SyslogEntry,
    SyslogLevel,
    SyslogLabel,
    SyslogFilter,
    SyslogFormatter,
    OutputFormat,
)

__all__ = [
    "SyslogEntry",
    "SyslogLevel",
    "SyslogLabel",
    "SyslogFilter",
    "SyslogFormatter",
    "OutputFormat",
]
