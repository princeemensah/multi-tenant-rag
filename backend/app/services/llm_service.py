"""LLM service placeholder."""
from typing import List


class LLMService:
    """Abstraction over LLM providers."""

    def get_available_providers(self) -> List[str]:
        return []
