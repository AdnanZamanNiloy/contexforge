from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from langchain_core.prompts import PromptTemplate

from app.config.settings import settings
from core.types import Chunk
from observability.tracer import observe

logger = logging.getLogger(__name__)


PROMPT_VERSION = "v1.0.0"
MAX_CHUNKS = 20

_ANSWER_TEMPLATE = PromptTemplate(
    template=(
        "You are a helpful assistant. Answer the question using ONLY the "
        "context provided below. If the answer cannot be found in the context, "
        "say so explicitly rather than guessing.\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}\n"
    ),
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
    def build(self, question: str, chunks: List[Chunk]) -> BuiltPrompt:
        self._validate(question, chunks)

        effective_chunks = self._deduplicate(chunks)[: self._max_chunks]
        if len(effective_chunks) < len(chunks):
            logger.warning(
                "prompt_builder: truncated chunk list from %d → %d "
                "(max_chunks=%d, duplicates removed)",
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
            system_prompt=settings.ANSWER_SYSTEM_PROMPT,
        )


    @staticmethod
    def _validate(question: str, chunks: Optional[List[Chunk]]) -> None:
        if not question or not question.strip():
            raise ValueError("PromptBuilder.build: 'question' must not be empty.")
        if chunks is None:
            raise ValueError("PromptBuilder.build: 'chunks' must not be None.")

    @staticmethod
    def _deduplicate(chunks: List[Chunk]) -> List[Chunk]:
  
        seen: set[str] = set()
        unique: List[Chunk] = []
        for chunk in chunks:
            if chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                unique.append(chunk)
        return unique

    @staticmethod
    def _format_context(chunks: List[Chunk]) -> str:

        if not chunks:
            return "(no context available)"
        return "\n\n".join(f"[{chunk.chunk_id}] {chunk.text}" for chunk in chunks)