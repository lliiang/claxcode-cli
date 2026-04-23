"""Lifecycle hooks (stub for Phase 5)."""

from typing import Any, Callable


class HookManager:
    """Register and execute lifecycle hooks."""

    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {}

    def register(self, event: str, callback: Callable) -> None:
        self._hooks.setdefault(event, []).append(callback)

    async def trigger(self, event: str, **kwargs: Any) -> None:
        for cb in self._hooks.get(event, []):
            await cb(**kwargs)
