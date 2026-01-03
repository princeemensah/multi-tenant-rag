"""Intent classification for routing user queries."""
from __future__ import annotations

import json
import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.services.llm_service import LLMService
from app.services.prompt_template_service import PromptTemplateService


class IntentType(str, Enum):
    INFORMATIONAL = "informational"
    ANALYTICAL = "analytical"
    ACTION = "action"
    CLARIFY = "clarify"


class IntentResult(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    entities: List[str] = Field(default_factory=list)
    requested_action: Optional[str] = None
    raw_response: Optional[str] = None


class IntentClassifier:
    """LLM-backed intent classifier with rule-based fallback."""

    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    async def classify(
        self,
        query: str,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> IntentResult:
        prompt = PromptTemplateService.intent_prompt(query)
        system_prompt = (
            "You are an operations assistant that analyses queries before routing them to tools. "
            "Always emit valid JSON matching the requested schema."
        )

        try:
            llm_response = await self.llm_service.generate_text_response(
                prompt=prompt,
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                temperature=0.0,
                max_tokens=300,
            )
            parsed = self._parse_response(llm_response.content)
            if parsed:
                parsed.raw_response = llm_response.content.strip()
                return parsed
        except Exception:
            # Fall back to heuristic rules below
            pass

        return self._heuristic_fallback(query)

    def _parse_response(self, payload: str) -> Optional[IntentResult]:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            # Attempt to extract JSON fragment if the model wrapped it in prose
            match = re.search(r"\{.*\}", payload, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

        intent_value = str(data.get("intent", "")).lower().strip()
        try:
            intent_enum = IntentType(intent_value)
        except ValueError:
            intent_enum = IntentType.INFORMATIONAL

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(confidence, 1.0))
        reasoning = str(data.get("reasoning", "")).strip()
        entities: List[str] = []
        raw_entities = data.get("entities", [])
        if isinstance(raw_entities, list):
            entities = [str(item).strip() for item in raw_entities if str(item).strip()]
        requested_action = data.get("requested_action")
        if isinstance(requested_action, str):
            requested_action = requested_action.strip() or None
        else:
            requested_action = None

        return IntentResult(
            intent=intent_enum,
            confidence=confidence,
            reasoning=reasoning,
            entities=entities,
            requested_action=requested_action,
        )

    def _heuristic_fallback(self, query: str) -> IntentResult:
        lowered = query.lower()
        action_keywords = ["create", "open", "schedule", "assign", "escalate", "log a task"]
        analytical_keywords = ["compare", "trend", "analysis", "impact", "metric", "root cause"]
        clarify_keywords = ["what do you mean", "clarify", "can you explain", "not sure"]

        intent = IntentType.INFORMATIONAL
        confidence = 0.3

        if any(keyword in lowered for keyword in clarify_keywords):
            intent = IntentType.CLARIFY
            confidence = 0.6
        elif any(keyword in lowered for keyword in action_keywords):
            intent = IntentType.ACTION
            confidence = 0.6
        elif any(keyword in lowered for keyword in analytical_keywords):
            intent = IntentType.ANALYTICAL
            confidence = 0.5

        return IntentResult(intent=intent, confidence=confidence, reasoning="heuristic fallback", entities=[])
