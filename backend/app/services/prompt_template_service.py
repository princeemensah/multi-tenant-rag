"""Centralized prompt templates for the agent pipeline."""
from __future__ import annotations

from textwrap import dedent
from typing import Iterable, List, Optional


class PromptTemplateService:
    """Utility container for agent prompt templates."""

    FORMAT_INSTRUCTIONS = {
        "bullet_list": "Format the response as a bulleted list containing only the requested items.",
        "bullet_list_queries": "Return only the follow-up queries as bullet points, no prose.",
        "json_intent": dedent(
            """
            Respond with valid JSON using this schema:
            {
              "intent": "informational | analytical | action | clarify",
              "confidence": float between 0 and 1,
              "reasoning": "short explanation",
              "entities": ["key noun phrases"],
              "requested_action": "action verb phrase if intent == action else null"
            }
            """
        ).strip(),
    }

    AGENT_ROLES = {
        "decomposer": dedent(
            """
            You are a research planner who breaks complex questions into precise follow-up queries.
            """
        ).strip(),
        "synthesizer": dedent(
            """
            You combine evidence from multiple documents into a cohesive, well-structured answer with citations.
            """
        ).strip(),
        "rag_assistant": dedent(
            """
            You are a document-grounded assistant. Base every answer on the provided context and cite sources.
            """
        ).strip(),
    }

    SYSTEM_MESSAGES = {
        "rag": dedent(
            """
            You are a helpful assistant. Review the supplied context and clearly cite the supporting source for each fact.
            If the context lacks relevant information, say so explicitly.
            """
        ).strip(),
        "citation_focus": dedent(
            """
            You must attribute every factual statement to a specific context source using [Source X] notation.
            Distinguish clearly between contextual evidence and general knowledge.
            """
        ).strip(),
    }

    INTENT_ANALYSIS = {
        "classification": dedent(
            """
            Analyze the following query before answering it:

            Query: {query}

            1. Determine the user's intent category.
            2. List the key entities or concepts.
            3. Identify any implied actions or objectives.
            4. Explain your reasoning briefly.

            {format_instructions}
            """
        ).strip(),
    }

    DECOMPOSITION = {
        "document_search": dedent(
            """
            {role}

            Original Query: {query}

            Break this query into 2-4 focused subquestions. Each subquestion should be self-contained,
            target a specific aspect of the original query, and maximise relevance for document retrieval.

            {format_instructions}
            """
        ).strip(),
        "informed_decomposition": dedent(
            """
            {role}

            Original Query: {query}

            Initial Summary:
            {initial_summary}

            Context Snippets:
            {context_snippets}

            Suggest 2-3 follow-up questions that would close remaining gaps, resolve ambiguities, or surface
            alternative perspectives. Avoid duplicating information already covered.

            {format_instructions}
            """
        ).strip(),
    }

    SYNTHESIS = {
        "standard": dedent(
            """
            {role}

            Original Query: {query}

            Findings:
            {findings}

            Write a concise, well-structured answer that integrates the findings, cites sources with [Source X],
            and notes unresolved gaps or conflicting evidence.
            """
        ).strip(),
    }

    ACTION_PLANNING = dedent(
        """
        You are an assistant that maps user requests to internal tools. Delimiters: ```

        User Query:
        ```
        {query}
        ```

        Available tools:
        - create_task(title, description?, priority?, due_date?, assignee?)
        - get_open_tasks()
        - summarize_incidents(timeframe_days?)

        Respond with JSON using this schema:
        {
          "tool": "create_task | get_open_tasks | summarize_incidents | none",
          "arguments": {"key": "value"}
        }

        Only choose tools that directly satisfy the request. If no tool applies, return "none".
        """
    ).strip()

    CHAT_TITLE = dedent(
        """
        You are naming a conversational transcript. Use 3-6 words, Title Case, no punctuation at the end.

        Transcript:
        {transcript}

        Title:
        """
    ).strip()

    @classmethod
    def get_format_instruction(cls, key: str) -> str:
        return cls.FORMAT_INSTRUCTIONS.get(key, "")

    @classmethod
    def get_role(cls, key: str) -> str:
        return cls.AGENT_ROLES.get(key, cls.AGENT_ROLES["rag_assistant"])

    @classmethod
    def get_system_message(cls, key: str) -> str:
        return cls.SYSTEM_MESSAGES.get(key, cls.SYSTEM_MESSAGES["rag"])

    @classmethod
    def intent_prompt(cls, query: str) -> str:
        return cls.INTENT_ANALYSIS["classification"].format(
            query=query,
            format_instructions=cls.get_format_instruction("json_intent"),
        )

    @classmethod
    def decomposition_prompt(cls, query: str, *, informed: bool = False, **kwargs: str) -> str:
        if informed:
            return cls.DECOMPOSITION["informed_decomposition"].format(
                role=cls.get_role("decomposer"),
                query=query,
                initial_summary=kwargs.get("initial_summary", ""),
                context_snippets=kwargs.get("context_snippets", ""),
                format_instructions=cls.get_format_instruction("bullet_list_queries"),
            )
        return cls.DECOMPOSITION["document_search"].format(
            role=cls.get_role("decomposer"),
            query=query,
            format_instructions=cls.get_format_instruction("bullet_list_queries"),
        )

    @classmethod
    def synthesis_prompt(cls, query: str, findings: str) -> str:
        return cls.SYNTHESIS["standard"].format(
            role=cls.get_role("synthesizer"),
            query=query,
            findings=findings,
        )

    @classmethod
    def action_planner_prompt(cls, query: str) -> str:
        return cls.ACTION_PLANNING.format(query=query)

    @classmethod
    def chat_title_prompt(
        cls,
        messages: Iterable[dict[str, str] | object],
        *,
        limit: int = 12,
    ) -> str:
        if isinstance(messages, str):
            recent = [{"role": "user", "content": messages}]
        else:
            recent = list(messages)[-limit:]
        if not recent:
            return cls.CHAT_TITLE.format(transcript="User: Conversation start")

        lines: List[str] = []
        for message in recent:
            role = getattr(message, "role", None) or (
                message.get("role") if isinstance(message, dict) else "user"
            )
            content = getattr(message, "content", None) or (
                message.get("content") if isinstance(message, dict) else ""
            )
            content = str(content).strip()
            if not content:
                continue
            lines.append(f"{role.capitalize()}: {content}")

        transcript = "\n".join(lines) if lines else "User: Conversation start"
        return cls.CHAT_TITLE.format(transcript=transcript)

    @classmethod
    def format_context(
        cls,
        contexts: Iterable[dict[str, object]],
        *,
        limit: int = 3,
        max_length: Optional[int] = None,
    ) -> str:
        sorted_contexts = sorted(contexts, key=lambda item: item.get("score", 0.0), reverse=True)[:limit]
        parts: List[str] = []
        for index, ctx in enumerate(sorted_contexts, start=1):
            title = ctx.get("document_title") or ctx.get("source") or "Unknown"
            snippet = ctx.get("text") or ctx.get("content") or ""
            snippet = str(snippet).strip()
            if not snippet:
                continue
            if max_length and len(snippet) > max_length:
                snippet = snippet[: max_length - 3].rstrip() + "..."
            parts.append(f"[Source {index}] {title}\n{snippet}")
        return "\n\n".join(parts)

    @classmethod
    def format_conversation(
        cls,
        conversation: Optional[Iterable[dict[str, str]]],
        query: str,
        *,
        limit: int = 3,
    ) -> str:
        if not conversation:
            return query

        recent_messages = list(conversation)[-limit:]
        lines: List[str] = ["Previous conversation:"]
        for message in recent_messages:
            role = message.get("role", "user")
            if role == "system":
                continue
            content = message.get("content", "").strip()
            if not content:
                continue
            lines.append(f"{role.capitalize()}: {content}")

        if len(lines) == 1:
            return query

        transcript = "\n".join(lines)
        return f"{transcript}\n\nConsidering the conversation above, answer this follow-up question: {query}"
