"""Context window management."""

from typing import Any

from claxcode.config import settings


def estimate_tokens(text: str) -> int:
    """Very rough token estimation (1 token ~= 4 chars for English/CJK mix)."""
    return len(text) // 3 + 1


class ContextManager:
    """Manages conversation history with compression support."""

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt
        self.messages: list[dict[str, Any]] = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self._maybe_compress()

    def add_tool_result(self, tool_call_id: str, name: str, output: str) -> None:
        """Add a tool result message (OpenAI format)."""
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": output,
            }
        )
        self._maybe_compress()

    def add_assistant_tool_calls(self, tool_calls: list[dict[str, Any]]) -> None:
        self.messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls,
            }
        )
        self._maybe_compress()

    def get_messages(self) -> list[dict[str, Any]]:
        return self.messages.copy()

    def _total_tokens(self) -> int:
        text = "\n".join(str(m.get("content", "")) for m in self.messages)
        return estimate_tokens(text) + estimate_tokens(self.system_prompt)

    def _maybe_compress(self) -> None:
        threshold = int(settings.max_context_tokens * settings.context_compression_threshold)
        while self._total_tokens() > threshold and len(self.messages) > 3:
            self.messages.pop(1)  # keep system at index 0

    def clear(self) -> None:
        self.messages = []
        if self.system_prompt:
            self.messages.append({"role": "system", "content": self.system_prompt})
