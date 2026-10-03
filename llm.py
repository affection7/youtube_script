"""LLM provider interface so new providers can be added without touching agent logic.

DeepSeek is the only implemented provider for now. To add Gemini or NordRouter
later, implement a class with the same `chat` signature and register it in
`create_provider`.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol

DEFAULT_PROVIDER = "deepseek"

# Signature of the underlying transport: (api_key, payload, model) -> response dict.
ChatFunction = Callable[[str, dict, str], dict[str, Any]]


class LLMProvider(Protocol):
    """Minimal interface every provider must implement."""

    name: str

    def chat(self, api_key: str, payload: dict[str, Any], model: str) -> dict[str, Any]:
        """Send a chat completion request and return the raw provider response."""
        ...


class DeepSeekProvider:
    """DeepSeek provider backed by an OpenAI-compatible chat function."""

    name = "deepseek"

    def __init__(self, chat_function: ChatFunction):
        self._chat_function = chat_function

    def chat(self, api_key: str, payload: dict[str, Any], model: str) -> dict[str, Any]:
        return self._chat_function(api_key, payload, model)


def create_provider(name: str, deepseek_chat_function: ChatFunction) -> LLMProvider:
    """Build a provider by name; unknown names fail loudly instead of guessing."""
    normalized = (name or DEFAULT_PROVIDER).strip().lower()
    if normalized == "deepseek":
        return DeepSeekProvider(deepseek_chat_function)
    raise ValueError(f"Unsupported LLM provider: '{name}'. Supported: deepseek")
