"""LLMProvider Protocol defining the interface for LLM provider adapters."""

from trace.infrastructure.llm.config import LLMConfig, ModelConfig
from trace.infrastructure.llm.response import LLMResponse
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol defining the required operations for an LLM provider adapter."""

    async def complete(
        self,
        prompt: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        """Send a prompt to the LLM and return the completion response.

        Args:
            prompt: Text prompt to complete.
            model: Model configuration specifying default, fallback, and role models.
            config: LLM provider connection configuration.

        Returns:
            An LLMResponse instance indicating success or specific failure state.
            Never raises exceptions to callers.
        """
        ...

    async def embed(
        self,
        text: str,
        model: ModelConfig,
        config: LLMConfig,
    ) -> LLMResponse:
        """Generate vector embeddings for the provided text.

        Args:
            text: Text to generate vector embeddings for.
            model: Model configuration specifying default and fallback models.
            config: LLM provider connection configuration.

        Returns:
            An LLMResponse instance with embedding content or specific failure state.
            Never raises exceptions to callers.
        """
        ...
