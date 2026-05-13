"""Tool system for ClaxCode."""

# Import all tool modules to trigger @tool registration
from claxcode.tools import file_operations, search, execution, web, code_intelligence, admin, browser, ssh  # noqa: F401
from claxcode.tools.registry import registry

__all__ = ["registry"]
