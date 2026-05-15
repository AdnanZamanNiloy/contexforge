from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Dict, List

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
from core.types import Chunk, Document, GenerationResult, RerankedChunk
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


    @observe(name="retrieve_context")
    async def retrieve_context(
        self,
        question: str,
        top_k_retrieval: int | None = None,
        top_k_rerank: int | None = None,
        use_hyde: bool | None = None,
    ) -> tuple[List[RerankedChunk], Dict[str, float]]:

        """Expand query, embed, retrieve, and rerank. Returns retrieved chunks and timing breakdown."""
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
        reranked = await self._reranker.rerank(question, retrieved, k_rerank)
        timings["rerank_ms"] = (time.perf_counter() - t) * 1000

        logger.debug(
            "retrieve_context: retrieved=%d reranked=%d "
            "hyde=%.1fms embed=%.1fms retrieve=%.1fms rerank=%.1fms",
            len(retrieved), len(reranked),
            timings["hyde_ms"], timings["embed_ms"],
            timings["retrieve_ms"], timings["rerank_ms"],
        )
        return reranked, timings

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
        """Full RAG pipeline: retrieve → generate → return with sources."""
        
        reranked, timings = await self.retrieve_context(
            question,
            top_k_retrieval=top_k_retrieval,
            top_k_rerank=top_k_rerank,
            use_hyde=use_hyde,
        )
        answer_text = await self.generate_answer(
            question,
            [item.chunk for item in reranked],
        )
        return GenerationResult(answer=answer_text, sources=reranked, latency_ms=timings)