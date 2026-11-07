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

    def add_message(self, role: str, content: str, reasoning_content: str = "") -> None:
        message = {"role": role, "content": content}
        if reasoning_content:
            message["reasoning_content"] = reasoning_content
        self.messages.append(message)
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

    def add_assistant_tool_calls(
        self, tool_calls: list[dict[str, Any]], reasoning_content: str = ""
    ) -> None:
        message: dict[str, Any] = {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
        }
        if reasoning_content:
            message["reasoning_content"] = reasoning_content
        self.messages.append(message)
        self._maybe_compress()

    def get_messages(self) -> list[dict[str, Any]]:
        return self.messages.copy()

    def _total_tokens(self) -> int:
        text = "\n".join(str(m.get("content", "")) for m in self.messages)
        return estimate_tokens(text) + estimate_tokens(self.system_prompt)

    def over_threshold(self) -> bool:
        """Whether the estimated token count exceeds the compression threshold."""
        threshold = int(settings.max_context_tokens * settings.context_compression_threshold)
        return self._total_tokens() > threshold

    def pop_oldest(self, count: int) -> list[dict[str, Any]]:
        """Remove and return up to `count` oldest non-system messages.

        Orphaned tool results at the cut boundary are dropped as well —
        providers reject a tool result without its assistant tool call.
        """
        end = min(1 + count, len(self.messages))
        removed = self.messages[1:end]
        del self.messages[1:end]
        while len(self.messages) > 1 and self.messages[1].get("role") == "tool":
            removed.append(self.messages.pop(1))
        return removed

    def insert_summary(self, summary: str) -> None:
        """Insert a compression summary right after the system prompt."""
        self.messages.insert(1, {"role": "system", "content": summary})

    def restore(self, messages: list[dict[str, Any]]) -> None:
        """Restore persisted messages after the system prompt.

        Leading tool results are dropped — without their assistant tool call
        (e.g. lost to compression in a previous session) providers reject them.
        Trailing assistant tool_calls without matching tool results are also
        dropped, e.g. when a previous run crashed between tool_calls and results.
        """
        self.messages.extend(messages)
        while len(self.messages) > 1 and self.messages[1].get("role") == "tool":
            self.messages.pop(1)

        i = 1
        while i < len(self.messages):
            msg = self.messages[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                needed = {tc["id"] for tc in msg["tool_calls"]}
                j = i + 1
                found: set[str] = set()
                while j < len(self.messages) and self.messages[j].get("role") == "tool":
                    found.add(self.messages[j].get("tool_call_id"))
                    j += 1
                if needed != found:
                    # Drop the orphan assistant and any trailing tool messages.
                    del self.messages[i:j]
                    continue
            i += 1

    def _maybe_compress(self) -> None:
        """Emergency fallback: hard-drop oldest messages while over the threshold."""
        while self.over_threshold() and len(self.messages) > 3:
            self.messages.pop(1)  # keep system at index 0
        while len(self.messages) > 1 and self.messages[1].get("role") == "tool":
            self.messages.pop(1)

    def clear(self) -> None:
        self.messages = []
        if self.system_prompt:
            self.messages.append({"role": "system", "content": self.system_prompt})
