from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.prompts import PromptTemplate

from app.config.settings import settings
from core.types import Chunk
from observability.tracer import observe

logger = logging.getLogger(__name__)


PROMPT_VERSION = "v2.0.0"
MAX_CHUNKS = 20

_ANSWER_TEMPLATE = PromptTemplate(
    template=("Below is the retrieved context relevant to the user's question.\n\n{context}\n\nQuestion: {question}\n"),
    input_variables=["context", "question"],
)

_GENERAL_TEMPLATE = PromptTemplate(
    template="Question: {question}\n",
    input_variables=["question"],
)


@dataclass(frozen=True)
class BuiltPrompt:
    user_prompt: str
    system_prompt: str
    prompt_version: str = PROMPT_VERSION


class PromptBuilder:
    def __init__(
        self,
        *,
        max_chunks: int = MAX_CHUNKS,
        template: PromptTemplate = _ANSWER_TEMPLATE,
    ) -> None:
        self._max_chunks = max_chunks
        self._template = template

    @observe(name="build_prompt")
    def build(self, question: str, chunks: list[Chunk]) -> BuiltPrompt:
        self._validate(question, chunks)

        effective_chunks = self._deduplicate(chunks)[: self._max_chunks]
        if len(effective_chunks) < len(chunks):
            logger.warning(
                "prompt_builder: truncated chunk list from %d → %d (max_chunks=%d, duplicates removed)",
                len(chunks),
                len(effective_chunks),
                self._max_chunks,
            )

        if not effective_chunks:
            user_prompt = _GENERAL_TEMPLATE.format(question=question)
            logger.debug(
                "prompt_builder: built general prompt | version=%s question_len=%d",
                PROMPT_VERSION,
                len(question),
            )
            return BuiltPrompt(
                user_prompt=user_prompt,
                system_prompt=settings.GENERAL_SYSTEM_PROMPT,
            )

        context = self._format_context(effective_chunks)
        user_prompt = self._template.format(context=context, question=question)

        logger.debug(
            "prompt_builder: built prompt | version=%s chunks=%d question_len=%d",
            PROMPT_VERSION,
            len(effective_chunks),
            len(question),
        )

        return BuiltPrompt(
            user_prompt=user_prompt,
            system_prompt=self._system_prompt_for_context(),
        )

    @staticmethod
    def _system_prompt_for_context() -> str:
        """The analyst prompt, plus citation rules when there is context to cite.

        Appended only when context is present: with no retrieved material there
        are no passage numbers, so asking for markers would invite the model to
        invent them.
        """
        if not settings.ENABLE_CITATIONS:
            return settings.ANSWER_SYSTEM_PROMPT
        return settings.ANSWER_SYSTEM_PROMPT + settings.CITATION_INSTRUCTIONS

    @staticmethod
    def _validate(question: str, chunks: list[Chunk] | None) -> None:
        if not question or not question.strip():
            raise ValueError("PromptBuilder.build: 'question' must not be empty.")
        if chunks is None:
            raise ValueError("PromptBuilder.build: 'chunks' must not be None.")

    @staticmethod
    def _deduplicate(chunks: list[Chunk]) -> list[Chunk]:

        seen: set[str] = set()
        unique: list[Chunk] = []
        for chunk in chunks:
            if chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                unique.append(chunk)
        return unique

    @staticmethod
    def _format_context(chunks: list[Chunk]) -> str:
        """Join chunks into a numbered context block.

        The numbers are what citation markers refer to, so they must be
        positional and stable: position *n* in this list is the *n*-th source in
        the response payload, which is the same order the reranker ranked them
        in. Any divergence here would make ``[1]`` point at the wrong source, so
        the caller must pass chunks in final display order.
        """
        if not chunks:
            return "(no context available)"
        return "\n\n".join(f"[{i}] {chunk.text}" for i, chunk in enumerate(chunks, start=1))

