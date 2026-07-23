"""Tool system for ClaxCode."""

import importlib
import pkgutil

from claxcode.tools.base import Tool  # noqa: F401
from claxcode.tools.registry import registry, tool  # noqa: F401

_EXCLUDED = {"base", "registry", "__init__"}

# Auto-discover and register all built-in tools
for _mod_info in pkgutil.iter_modules(__path__):
    if _mod_info.name not in _EXCLUDED:
        importlib.import_module(f"claxcode.tools.{_mod_info.name}")
