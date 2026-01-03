"""Provider-agnostic LLM service for RAG responses."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from fastapi import HTTPException
from app.config import settings

try:  # Optional OpenAI dependency
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - dependency optional
    AsyncOpenAI = None  # type: ignore

try:  # Optional Anthropic dependency
    from anthropic import AsyncAnthropic
except Exception:  # pragma: no cover
    AsyncAnthropic = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Unified language model response."""

    content: str
    usage: Dict[str, int]
    model: str
    provider: str
    finish_reason: str
    metadata: Dict[str, Any]


class BaseProvider:
    """Common interface all providers implement."""

    name: str = "unknown"

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        raise NotImplementedError

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        raise NotImplementedError

    def get_available_models(self) -> List[str]:
        return []


class OpenAIProvider(BaseProvider):
    """Async OpenAI chat completions wrapper."""

    name = "openai"

    def __init__(self, api_key: str) -> None:
        if AsyncOpenAI is None:
            raise RuntimeError("openai package not installed")
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
        metadata = {"response_id": response.id}
        return LLMResponse(
            content=choice.message.content or "",
            usage=usage,
            model=response.model,
            provider=self.name,
            finish_reason=choice.finish_reason or "stop",
            metadata=metadata,
        )

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        stream = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async def iterator() -> AsyncGenerator[str, None]:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        return iterator()

    def get_available_models(self) -> List[str]:
        return [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1-mini",
            "gpt-3.5-turbo",
        ]


class AnthropicProvider(BaseProvider):
    """Anthropic Claude integration."""

    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        if AsyncAnthropic is None:
            raise RuntimeError("anthropic package not installed")
        self.client = AsyncAnthropic(api_key=api_key)

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        system_prompt = ""
        normalized: List[Dict[str, str]] = []
        for message in messages:
            if message.get("role") == "system":
                system_prompt = message.get("content", "")
            else:
                normalized.append(message)

        response = await self.client.messages.create(
            model=model,
            system=system_prompt,
            messages=normalized,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }
        return LLMResponse(
            content=response.content[0].text if response.content else "",
            usage=usage,
            model=response.model,
            provider=self.name,
            finish_reason=response.stop_reason or "stop",
            metadata={"response_id": response.id},
        )

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        system_prompt = ""
        normalized: List[Dict[str, str]] = []
        for message in messages:
            if message.get("role") == "system":
                system_prompt = message.get("content", "")
            else:
                normalized.append(message)

        stream = self.client.messages.stream(
            model=model,
            system=system_prompt,
            messages=normalized,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        async def iterator() -> AsyncGenerator[str, None]:
            async with stream as event_stream:
                async for text in event_stream.text_stream:
                    yield text

        return iterator()

    def get_available_models(self) -> List[str]:
        return [
            "claude-3-haiku-20240307",
            "claude-3-sonnet-20240229",
            "claude-3-opus-20240229",
        ]


class FallbackProvider(BaseProvider):
    """Deterministic fallback when no provider is configured."""

    name = "fallback"

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        answer = "Unable to reach an external language model."
        return LLMResponse(
            content=answer,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            model=model,
            provider=self.name,
            finish_reason="fallback",
            metadata={},
        )

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        async def iterator() -> AsyncGenerator[str, None]:
            yield "Unable to reach an external language model."

        return iterator()


class LLMService:
    """Facade for orchestrating RAG prompts across providers."""

    def __init__(self) -> None:
        self.providers: Dict[str, BaseProvider] = {}
        self._initialize_providers()
        self.default_provider = settings.default_llm_provider or next(iter(self.providers))

    def _resolve_model(self, provider: BaseProvider, requested: Optional[str]) -> str:
        if requested:
            return requested
        options = provider.get_available_models()
        return options[0] if options else "default"

    def _initialize_providers(self) -> None:
        if settings.openai_api_key:
            try:
                self.providers["openai"] = OpenAIProvider(settings.openai_api_key)
                logger.info("OpenAI provider initialized")
            except Exception as exc:  # pragma: no cover - init failures logged
                logger.warning("Failed to initialise OpenAI provider", extra={"error": str(exc)})

        if settings.anthropic_api_key:
            try:
                self.providers["anthropic"] = AnthropicProvider(settings.anthropic_api_key)
                logger.info("Anthropic provider initialized")
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to initialise Anthropic provider", extra={"error": str(exc)})

        if not self.providers:
            logger.warning("No external LLM providers configured; using fallback")
        self.providers.setdefault("fallback", FallbackProvider())

    def get_provider(self, name: Optional[str]) -> BaseProvider:
        provider_name = name or self.default_provider
        if provider_name not in self.providers:
            raise HTTPException(status_code=400, detail=f"Unsupported LLM provider '{provider_name}'")  # type: ignore[name-defined]
        return self.providers[provider_name]

    def build_rag_messages(
        self,
        query: str,
        context_documents: List[Dict[str, Any]],
        system_prompt: Optional[str],
    ) -> List[Dict[str, str]]:
        prompt = system_prompt or (
            "You are a helpful assistant. Base every answer on the supplied context. "
            "If the context is insufficient, state that limitation explicitly."
        )

        context_sections: List[str] = []
        for index, document in enumerate(context_documents, 1):
            source = document.get("source") or "Unknown"
            text = document.get("text") or ""
            context_sections.append(f"[Document {index} - {source}]\n{text}")
        context_block = "\n\n".join(context_sections)

        if context_block:
            user_content = f"Question: {query}\n\nContext:\n{context_block}"
        else:
            user_content = f"Question: {query}\n\nContext: <none>"

        return [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]

    async def generate_rag_response(
        self,
        *,
        query: str,
        context_documents: List[Dict[str, Any]],
        provider: Optional[str],
        model: Optional[str],
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> Union[LLMResponse, AsyncGenerator[str, None]]:
        llm_provider = self.get_provider(provider)
        messages = self.build_rag_messages(query, context_documents, system_prompt)

        selected_model = self._resolve_model(llm_provider, model)

        if stream:
            return llm_provider.generate_stream(
                messages,
                model=selected_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        return await llm_provider.generate_response(
            messages,
            model=selected_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def generate_text_response(
        self,
        *,
        prompt: str,
        provider: Optional[str],
        model: Optional[str],
        system_prompt: Optional[str],
        temperature: float = 0.2,
        max_tokens: int = 400,
    ) -> LLMResponse:
        llm_provider = self.get_provider(provider)
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        selected_model = self._resolve_model(llm_provider, model)
        return await llm_provider.generate_response(
            messages,
            model=selected_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def get_available_providers(self) -> List[str]:
        return list(self.providers.keys())

    def get_provider_models(self, provider: str) -> List[str]:
        if provider not in self.providers:
            return []
        return self.providers[provider].get_available_models()
