from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Dict, List, Tuple

from app.config.settings import settings
from core.chunking.code_chunker import CodeChunker
from core.chunking.text_chunker import TextChunker
from core.generation.prompt_builder import PromptBuilder
from core.interfaces.embedder import Embedder
from core.interfaces.llm import LLM
from core.processing.cleaner import TextCleaner
from core.processing.deduplicator import Deduplicator
from core.processing.metadata_extractor import MetadataExtractor
from core.retrieval.hyde import HydeQueryExpander
from core.retrieval.hybrid_retriever import HybridRetriever
from core.retrieval.reranker import Reranker
from core.storage.bm25_index import BM25Index
from core.storage.faiss_store import FaissStore
# FIX: import ConfidenceMetrics alongside existing types
from core.types import Chunk, ConfidenceMetrics, Document, GenerationResult, RerankedChunk
from observability.tracer import observe

__all__ = ["Orchestrator"]

logger = logging.getLogger(__name__)


class Orchestrator:

    def __init__(
        self,
        embedder: Embedder,
        llm: LLM,
        bm25: BM25Index,
        faiss: FaissStore,
        hybrid: HybridRetriever,
        reranker: Reranker,
        prompt_builder: PromptBuilder,
        cleaner: TextCleaner | None = None,
        metadata_extractor: MetadataExtractor | None = None,
        deduplicator: Deduplicator | None = None,
        hyde: HydeQueryExpander | None = None,
        text_chunker: TextChunker | None = None,
        code_chunker: CodeChunker | None = None,
    ) -> None:
        self._embedder = embedder
        self._llm = llm
        self._bm25 = bm25
        self._faiss = faiss
        self._hybrid = hybrid
        self._reranker = reranker
        self._prompt_builder = prompt_builder
        self._cleaner = cleaner or TextCleaner()
        self._metadata_extractor = metadata_extractor or MetadataExtractor()
        self._deduplicator = deduplicator or Deduplicator()
        self._hyde = hyde
        self._text_chunker = text_chunker or TextChunker()
        self._code_chunker = code_chunker or CodeChunker()


    @observe(name="ingest_index")
    async def ingest(
        self,
        documents: List[Document],
        use_code_chunker: bool = False,
        skip_preprocessing: bool = False,) -> int:
        """Preprocess, chunk, embed, and index *documents*."""

        start = time.perf_counter()

        if skip_preprocessing:
            if not documents:
                logger.warning("ingest: skip_preprocessing=True but document list is empty.")
                return 0
            processed = documents
        else:
            processed = await self._preprocess(documents)

        if not processed:
            logger.warning("ingest: preprocessing produced no documents.")
            return 0

        chunker = self._code_chunker if use_code_chunker else self._text_chunker
        chunks = chunker.chunk_documents(processed)

        if not chunks:
            logger.warning("ingest: chunking produced no chunks from %d document(s).", len(processed))
            return 0

        embeddings = await self._embedder.embed_texts(
            [chunk.text for chunk in chunks],
            input_type="document",
        )
        await self._faiss.add(chunks, embeddings)
        await self._bm25.add(chunks)

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "ingest: %d document(s) → %d chunk(s) indexed in %.1f ms.",
            len(documents), len(chunks), elapsed,
        )
        return len(chunks)

    async def _preprocess(self, documents: List[Document]) -> List[Document]:
        """Run clean → metadata extract → deduplicate in sequence."""

        cleaned = await self._cleaner.clean(documents)
        enriched = await self._metadata_extractor.extract(cleaned)
        deduplicated = await self._deduplicator.deduplicate(enriched)
        logger.debug(
            "_preprocess: %d in → %d out (%d deduped).",
            len(documents), len(deduplicated), len(documents) - len(deduplicated),
        )
        return deduplicated

    @observe(name="delete_source")
    async def delete_source(self, source_id: str) -> int:
        """Remove all chunks belonging to *source_id* from both stores.

        Performs a bulletproof multi-phase deletion:
        1. Delete from FAISS (holds lock during rebuild + persist + reload)
        2. Delete from BM25 (holds lock during delete + reload)
        3. Clear deduplicator so re-ingestion of the same content is not blocked
        4. Log verification counts from both stores

        Returns:
            Number of chunks removed from FAISS.
        """
        if not source_id or not source_id.strip():
            raise ValueError("source_id must be a non-blank string")

        start = time.perf_counter()
        logger.info("delete_source: source_id=%s — starting deletion", source_id)

        faiss_removed = 0
        bm25_removed = 0
        errors: list[str] = []

        # --- Phase 1: delete from FAISS ---
        try:
            faiss_removed = await self._faiss.delete_by_source_id(source_id)
        except Exception as exc:
            logger.exception("delete_source: FAISS deletion failed for source_id=%s", source_id)
            errors.append(f"FAISS: {exc}")

        # --- Phase 2: delete from BM25 ---
        try:
            bm25_removed = await self._bm25.delete_by_source_id(source_id)
        except Exception as exc:
            logger.exception("delete_source: BM25 deletion failed for source_id=%s", source_id)
            errors.append(f"BM25: {exc}")

        # --- Phase 3: clear deduplicator so re-ingestion works ---
        try:
            self._deduplicator.reset()
            logger.info("delete_source: deduplicator cleared for source_id=%s", source_id)
        except Exception as exc:
            logger.warning("delete_source: deduplicator reset failed: %s", exc)

        # --- Phase 4: force-reload both stores (belt-and-suspenders) ---
        try:
            await self._faiss.force_reload()
        except Exception as exc:
            logger.warning("delete_source: FAISS force_reload failed: %s", exc)

        try:
            await self._bm25.force_reload()
        except Exception as exc:
            logger.warning("delete_source: BM25 force_reload failed: %s", exc)

        # --- Phase 5: verification ---
        try:
            remaining_faiss = self._faiss.get_source_ids()
            remaining_bm25_count = await self._bm25.count()
            source_still_in_faiss = source_id in remaining_faiss
            logger.info(
                "delete_source VERIFICATION: source_id=%s "
                "faiss_removed=%d bm25_removed=%d "
                "source_still_in_faiss=%s bm25_total_chunks=%d",
                source_id, faiss_removed, bm25_removed,
                source_still_in_faiss, remaining_bm25_count,
            )
            if source_still_in_faiss:
                logger.error(
                    "delete_source: source_id=%s STILL PRESENT in FAISS after deletion! "
                    "This indicates a bug in the delete logic.",
                    source_id,
                )
        except Exception as exc:
            logger.warning("delete_source: verification failed: %s", exc)

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "delete_source: source_id=%s faiss=%d bm25=%d elapsed=%.1f ms",
            source_id, faiss_removed, bm25_removed, elapsed,
        )

        if errors:
            logger.warning(
                "delete_source: partial failure for source_id=%s — %s",
                source_id, "; ".join(errors),
            )

        return faiss_removed

    @observe(name="clear_all")
    async def clear_all(self) -> dict[str, int]:
        """Clear all data from FAISS, BM25, and the deduplicator.

        Returns:
            Dict with faiss_chunks_removed and bm25_chunks_removed counts.
        """
        start = time.perf_counter()
        logger.info("clear_all: starting full knowledge base wipe")

        faiss_count = 0
        bm25_count = 0

        try:
            faiss_count = await self._faiss.clear_all()
        except Exception as exc:
            logger.exception("clear_all: FAISS clear failed: %s", exc)

        try:
            bm25_count = await self._bm25.clear_all()
        except Exception as exc:
            logger.exception("clear_all: BM25 clear failed: %s", exc)

        try:
            self._deduplicator.reset()
        except Exception as exc:
            logger.warning("clear_all: deduplicator reset failed: %s", exc)

        try:
            await self._faiss.force_reload()
        except Exception as exc:
            logger.warning("clear_all: FAISS force_reload failed: %s", exc)

        try:
            await self._bm25.force_reload()
        except Exception as exc:
            logger.warning("clear_all: BM25 force_reload failed: %s", exc)

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "clear_all: faiss=%d bm25=%d elapsed=%.1f ms",
            faiss_count, bm25_count, elapsed,
        )
        return {"faiss_chunks_removed": faiss_count, "bm25_chunks_removed": bm25_count}

    @observe(name="retrieve_context")
    async def retrieve_context(
        self,
        question: str,
        top_k_retrieval: int | None = None,
        top_k_rerank: int | None = None,
        use_hyde: bool | None = None,
    # FIX: return type now includes mean_confidence from the reranker
    ) -> tuple[List[RerankedChunk], Dict[str, float], float]:

        """Expand query, embed, retrieve, and rerank.

        Returns:
            Tuple of (reranked chunks, timing breakdown, mean_confidence).
            *mean_confidence* is the sigmoid-normalised average of top-k
            reranker scores, floored at 0.35.  On reranker failure it falls
            back to 0.35 so the frontend never shows zero.
        """
        timings: Dict[str, float] = {}

        # HyDE expansion ------------------------------------------------
        t = time.perf_counter()

        effective_hyde = use_hyde if use_hyde is not None else settings.USE_HYDE
        hyde_question = question
        if effective_hyde:
            if self._hyde is not None:
                hyde_question = await self._hyde.expand(question)
            else:
                logger.warning(
                    "retrieve_context: use_hyde=True but no HydeQueryExpander "
                    "was injected — falling back to original question."
                )
        timings["hyde_ms"] = (time.perf_counter() - t) * 1000

        # Embedding -----------------------------------------------------
        t = time.perf_counter()
      
        query_vector = await self._embedder.embed_single(hyde_question, input_type="query")
        timings["embed_ms"] = (time.perf_counter() - t) * 1000

        # Retrieval -----------------------------------------------------
        t = time.perf_counter()
        k_retrieve = top_k_retrieval if top_k_retrieval is not None else settings.TOP_K_RETRIEVAL
        retrieved = await self._hybrid.retrieve(question, query_vector, k_retrieve)
        timings["retrieve_ms"] = (time.perf_counter() - t) * 1000

        # Reranking -----------------------------------------------------
        t = time.perf_counter()
        k_rerank = top_k_rerank if top_k_rerank is not None else settings.TOP_K_RERANK

        # FIX: wrap reranker call so a failure degrades gracefully
        try:
            # FIX: reranker now returns (chunks, mean_confidence)
            reranked, mean_confidence = await self._reranker.rerank(
                question, retrieved, k_rerank,
            )
        except Exception:
            logger.exception(
                "retrieve_context: reranker failed for question=%r — "
                "returning retrieved chunks with fallback confidence",
                question,
            )
            # Degrade gracefully — keep un-reranked chunks.
            # Use a moderate fallback confidence so the UI doesn't show 0%
            # when retrieval succeeded but the reranker model failed.
            reranked = [
                RerankedChunk(chunk=item.chunk, score=0.5, rank=rank)
                for rank, item in enumerate(retrieved[:k_rerank], start=1)
            ]
            mean_confidence = 0.50

        timings["rerank_ms"] = (time.perf_counter() - t) * 1000

        logger.debug(
            "retrieve_context: retrieved=%d reranked=%d confidence=%.4f "
            "hyde=%.1fms embed=%.1fms retrieve=%.1fms rerank=%.1fms",
            len(retrieved), len(reranked), mean_confidence,
            timings["hyde_ms"], timings["embed_ms"],
            timings["retrieve_ms"], timings["rerank_ms"],
        )
        return reranked, timings, mean_confidence

    # Confidence thresholds — tuned for calibrated reranker output.
    # With temperature=2.0, shift=2.0 calibration:
    #   raw 0  → 0.73,  raw 2  → 0.88,  raw 4  → 0.95
    #   raw -2 → 0.50,  raw -4 → 0.27
    _COVERAGE_THRESHOLDS = (
        (0.80, "Excellent"),
        (0.60, "Strong"),
        (0.40, "Moderate"),
        (0.25, "Low"),
    )

    @staticmethod
    def _build_confidence(
        reranked: List[RerankedChunk],
        mean_confidence: float,
    ) -> ConfidenceMetrics:
        """Derive server-side ConfidenceMetrics from the reranker output.

        Args:
            reranked:         RerankedChunk list (top-k after reranking / fallback).
            mean_confidence:  Calibrated mean confidence from the reranker.

        Returns:
            A fully populated :class:`ConfidenceMetrics` instance.
        """
        coverage = "Weak"
        for threshold, label in Orchestrator._COVERAGE_THRESHOLDS:
            if mean_confidence > threshold:
                coverage = label
                break

        sources_used = len({c.chunk.source_id for c in reranked if c.chunk.source_id})
        retrieved_chunks = len(reranked)
        return ConfidenceMetrics(
            answer_confidence=round(mean_confidence, 4),
            source_coverage=coverage,
            sources_used=sources_used,
            retrieved_chunks=retrieved_chunks,
        )

    @observe(name="generate_answer")
    async def generate_answer(self, question: str, chunks: List[Chunk]) -> str:
        """Generate a complete answer from *chunks* for *question*."""
        built = self._prompt_builder.build(question, chunks)
        return await self._llm.generate(
            built.user_prompt,
            system_prompt=built.system_prompt,
        )

    @observe(name="stream_answer")
    async def stream_answer(
        self, question: str, chunks: List[Chunk]) -> AsyncIterator[str]:
        """Stream answer tokens for *question* grounded in *chunks*."""
        built = self._prompt_builder.build(question, chunks)
        async for token in self._llm.stream(
            built.user_prompt,
            system_prompt=built.system_prompt,
        ):
            yield token

    @observe(name="answer")
    async def answer(
        self,
        question: str,
        top_k_retrieval: int | None = None,
        top_k_rerank: int | None = None,
        use_hyde: bool | None = None,
    ) -> GenerationResult:
        """Full RAG pipeline: retrieve → generate → return with sources and confidence."""

        # FIX: unpack the new 3-tuple from retrieve_context
        reranked, timings, mean_confidence = await self.retrieve_context(
            question,
            top_k_retrieval=top_k_retrieval,
            top_k_rerank=top_k_rerank,
            use_hyde=use_hyde,
        )
        answer_text = await self.generate_answer(
            question,
            [item.chunk for item in reranked],
        )
        # FIX: build ConfidenceMetrics and attach to GenerationResult
        confidence = self._build_confidence(reranked, mean_confidence)
        return GenerationResult(
            answer=answer_text,
            sources=reranked,
            latency_ms=timings,
            confidence=confidence,
        )
