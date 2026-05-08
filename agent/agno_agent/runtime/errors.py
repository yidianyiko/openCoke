from __future__ import annotations


class UnknownToolError(Exception):
    """Raised when the model selects a capability tool that is not available."""
