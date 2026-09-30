from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import replace

from app.config.settings import settings
from core.chunking.code_chunker import CodeChunker
from core.chunking.text_chunker import TextChunker
from core.generation.citations import parse_citations
from core.generation.grounding import GroundingReport, check_grounding
from core.generation.prompt_builder import PromptBuilder
from core.interfaces.embedder import Embedder
from core.interfaces.llm import LLM
from core.processing.cleaner import TextCleaner
from core.processing.deduplicator import Deduplicator
from core.processing.metadata_extractor import MetadataExtractor
from core.retrieval.hybrid_retriever import HybridRetriever
from core.retrieval.hyde import HydeQueryExpander
from core.retrieval.reranker import Reranker
from core.storage.bm25_index import BM25Index
from core.storage.faiss_store import FaissStore

# Import ConfidenceMetrics alongside existing types
from core.types import (
    Chunk,
    ConfidenceMetrics,
    Document,
    GenerationResult,
    RerankedChunk,
)
from observability.tracer import observe

__all__ = ["Orchestrator"]

logger = logging.getLogger(__name__)

# Punctuation stripped when tokenizing a question for the heuristics below.
_NON_WORD = re.compile(r"[^0-9a-z\u0980-\u09ff]+")

# Phrases that signal a generic "tell me about / summarize" intent.  These are
# poor lexical matches against specific document chunks, so HyDE expansion is
# worth the extra LLM call for them.
_VAGUE_INTENT_MARKERS = (
    "tell me about",
    "what is this",
    "what's this",
    "summarize",
    "summary",
    "overview",
    "describe",
    "about this",
    "what can you tell me about",
    "explain this",
)


def _word_tokens(text: str) -> list[str]:
    """Lowercase word tokens, used by the question heuristics.

    The character class keeps Latin and Bengali letters so a Bengali question
    is tokenized on real word boundaries rather than split into punctuation.
    """
    cleaned = _NON_WORD.sub(" ", text.lower())
    return [tok for tok in cleaned.split() if tok]


def _is_vague_query(question: str) -> bool:
    """Heuristic: is *question* generic enough to benefit from HyDE?

    Returns True for short questions (<= 3 words) or ones containing generic
    intent markers such as "tell me about" or "summarize".  Specific questions
    (with dates, names, numbers, or a concrete subject) are not flagged.
    """
    q = question.strip().lower()
    if not q:
        return False
    if len(q.split()) <= 3:
        return True
    return any(marker in q for marker in _VAGUE_INTENT_MARKERS)


# Short social/greeting utterances that carry no information request.  These
# should never hit the retrieval pipeline: answering them from general
# knowledge keeps the response instant and keeps irrelevant KB chunks from
# being attached as "sources".
_CHITCHAT_TOKENS = {
    "hello",
    "hi",
    "hey",
    "yo",
    "hiya",
    "howdy",
    "sup",
    "hola",
    "greetings",
    "hii",
    "hiii",
    "thanks",
    "thank",
    "thx",
    "ty",
    "ok",
    "okay",
    "good",
    "morning",
    "afternoon",
    "evening",
    "bye",
    "goodbye",
    "cheers",
    "welcome",
    "please",
    "sure",
    "yes",
    "yeah",
    "cool",
    "there",
    "how",
    "are",
    "you",
    "doing",
    "guys",
    "everyone",
}


def _is_chitchat(question: str) -> bool:
    """Heuristic: is *question* a greeting/social utterance (no KB intent)?

    Returns True only for very short utterances made up entirely of
    greeting/filler tokens.  Anything with a content word (a name, a topic, a
    verb like "summarize", a plural like "projects") is not treated as chitchat,
    so queries such as "hello, summarize the projects" still hit retrieval.
    """
    q = question.strip().lower()
    if not q:
        return False
    tokens = [tok.strip(".,!? ") for tok in q.replace("/", " ").split()]
    tokens = [tok for tok in tokens if tok]
    if not tokens:
        return True
    if len(tokens) > 3:
        return False
    return all(tok in _CHITCHAT_TOKENS for tok in tokens)


# Words that make a query refer to the loaded source(s) themselves rather than
# to an external topic.  A query like "tell me about source" is a request for an
# overview of the corpus; "tell me about quantum physics" is not.
_CORPUS_REF_MARKERS = (
    "source",
    "this",
    "document",
    "what's in",
    "in here",
    "these",
    "file",
    "content",
    "about it",
    "details about",
    "overview",
    "on it",
    "of this",
)

# Overview/summary requests about the corpus are inherently low-relevance to the
# cross-encoder, so they are allowed a focus-based confidence boost without
# meeting the per-chunk relevance gate.  Off-topic questions about a named
# external subject still require real relevance.
_CORPUS_OVERVIEW_MAX_WORDS = 8


def _is_corpus_overview(question: str) -> bool:
    """Heuristic: is *question* an overview/summary request about the corpus?

    Returns True for short questions that refer to the loaded content itself
    ("tell me about source", "summarize this", "give me details about it").
    Questions naming an external topic are not treated as corpus overviews.
    """
    q = question.strip().lower()
    if not q:
        return False
    if len(q.split()) > _CORPUS_OVERVIEW_MAX_WORDS:
        return False
    return any(marker in q for marker in _CORPUS_REF_MARKERS)


# Questions answered by the set of indexed files rather than by any single
# passage. Retrieval ranks chunks, so these can only be answered from whichever
# handful survived the top-k — which is why a structure question needs the
# manifest instead.
_STRUCTURE_MARKERS = (
    "file structure",
    "folder structure",
    "directory structure",
    "directory tree",
    "file tree",
    "project structure",
    "repo structure",
    "repository structure",
    "code structure",
    "list the files",
    "list all files",
    "what files",
    "which files",
    "all files",
    "folder layout",
    "file layout",
    "what folders",
    "which folders",
    "directories",
    "how is it organised",
    "how is it organized",
)

# A structure question is about the corpus as a whole, so it is exempt from the
# short-question limit that _is_corpus_overview applies.
_STRUCTURE_MAX_WORDS = 14


def _is_structure_question(question: str) -> bool:
    """Heuristic: does *question* ask for the project's file layout?

    Deliberately narrower than it could be. Attaching a manifest to an ordinary
    question wastes tokens and invites the model to describe the listing rather
    than answer, so this matches phrasing that genuinely wants a tree.
    """
    q = question.strip().lower()
    if not q or len(q.split()) > _STRUCTURE_MAX_WORDS:
        return False
    return any(marker in q for marker in _STRUCTURE_MARKERS)


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

    async def swap_llm(self, llm: LLM) -> None:
        """Replace the active LLM used for generation.

        Called by the Model Hub when the served LLM / LLM chain changes so a
        serving switch takes effect on the running pipeline immediately, without
        a process restart.  The previous LLM is *not* closed here — it may be
        the shared env-driven fallback chain that other components (e.g. HyDE)
        still reference.
        """
        self._llm = llm
        logger.info("Orchestrator: active LLM swapped to %s.", type(llm).__name__)

    async def swap_embedder(self, embedder: Embedder) -> None:
        """Replace the active embedder used for ingestion and query embedding."""
        self._embedder = embedder
        logger.info("Orchestrator: active embedder swapped to %s.", type(embedder).__name__)

    @observe(name="ingest_index")
    async def ingest(
        self,
        documents: list[Document],
        use_code_chunker: bool = False,
        skip_preprocessing: bool = False,
    ) -> int:
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

        # Embedding runs after the deduplicator has already recorded these
        # fingerprints in *_preprocess*.  If any step below fails we abandon the
        # batch, so clear the deduplicator too — otherwise the retry would see
        # every document as "seen" and silently index nothing.
        try:
            embeddings = await self._embedder.embed_texts(
                [chunk.text for chunk in chunks],
                input_type="document",
            )
            await self._faiss.add(chunks, embeddings)
            await self._bm25.add(chunks)
        except Exception:
            self._deduplicator.reset()
            raise

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "ingest: %d document(s) → %d chunk(s) indexed in %.1f ms.",
            len(documents),
            len(chunks),
            elapsed,
        )
        return len(chunks)

    async def _preprocess(self, documents: list[Document]) -> list[Document]:
        """Run clean → metadata extract → deduplicate in sequence."""

        cleaned = await self._cleaner.clean(documents)
        enriched = await self._metadata_extractor.extract(cleaned)
        deduplicated = await self._deduplicator.deduplicate(enriched)
        logger.debug(
            "_preprocess: %d in → %d out (%d deduped).",
            len(documents),
            len(deduplicated),
            len(documents) - len(deduplicated),
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
                source_id,
                faiss_removed,
                bm25_removed,
                source_still_in_faiss,
                remaining_bm25_count,
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
            source_id,
            faiss_removed,
            bm25_removed,
            elapsed,
        )

        if errors:
            logger.warning(
                "delete_source: partial failure for source_id=%s — %s",
                source_id,
                "; ".join(errors),
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
        except Exception:
            logger.exception("clear_all: FAISS clear failed")

        try:
            bm25_count = await self._bm25.clear_all()
        except Exception:
            logger.exception("clear_all: BM25 clear failed")

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
            faiss_count,
            bm25_count,
            elapsed,
        )
        return {"faiss_chunks_removed": faiss_count, "bm25_chunks_removed": bm25_count}

    @observe(name="retrieve_context")
    async def retrieve_context(
        self,
        question: str,
        top_k_retrieval: int | None = None,
        top_k_rerank: int | None = None,
        use_hyde: bool | None = None,
        source_id: str | None = None,
        source_ids: set[str] | list[str] | None = None,
        use_knowledge_base: bool = True,
        # Return type now includes mean_confidence from the reranker
    ) -> tuple[list[RerankedChunk], dict[str, float], float]:
        """Expand query, embed, retrieve, and rerank.

        Returns:
            Tuple of (reranked chunks, timing breakdown, mean_confidence).
            *mean_confidence* is the sigmoid-normalised average of top-k
            reranker scores, floored at 0.35.  On reranker failure it falls
            back to 0.35 so the frontend never shows zero.
        """
        timings: dict[str, float] = {}

        # No source selected: answer from general knowledge rather than the
        # corpus, so an unscoped chat never surfaces a source the user did not
        # choose.
        if not use_knowledge_base:
            logger.debug(
                "retrieve_context: knowledge base disabled — skipping retrieval for question=%r",
                question,
            )
            return [], {}, 0.0

        # Chitchat / greeting: no information demand on the KB, so bypass the
        # whole retrieval pipeline.  The answer is produced from general
        # knowledge with an empty source list and Weak confidence.
        if _is_chitchat(question):
            logger.debug("retrieve_context: chitchat — skipping retrieval for question=%r", question)
            return [], {}, 0.0

        # HyDE expansion ------------------------------------------------
        t = time.perf_counter()

        effective_hyde = self._resolve_hyde(use_hyde, question)
        hyde_question = question
        if effective_hyde:
            if self._hyde is not None:
                hyde_question = await self._hyde.expand(question)
                if hyde_question != question:
                    logger.debug(
                        "retrieve_context: HyDE expanded %d-char question to %d-char hypothesis (auto mode=%s).",
                        len(question),
                        len(hyde_question),
                        use_hyde,
                    )
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
        k_rerank = top_k_rerank if top_k_rerank is not None else settings.TOP_K_RERANK
        # When the query is scoped to a selection of sources (the project
        # workspace picks one or many), exclude every other source's chunks so
        # the answer is grounded only in the selected sources.  The exclusion
        # set is the store's full source list minus the selection.
        exclude_source_ids = await self._source_exclude_set(source_id, source_ids)
        # Use the (possibly HyDE-expanded) query text for the BM25 + dense
        # legs too, so expansion is consistent across the whole pipeline.
        retrieved = await self._hybrid.retrieve(
            hyde_question,
            query_vector,
            k_retrieve,
            exclude_source_ids=exclude_source_ids,
        )
        timings["retrieve_ms"] = (time.perf_counter() - t) * 1000

        # Reranking -----------------------------------------------------
        t = time.perf_counter()

        # Wrap reranker call so a failure degrades gracefully
        try:
            # Reranker now returns (chunks, mean_confidence).  Use the
            # HyDE-expanded query so scoring matches what was retrieved.
            reranked, mean_confidence = await self._reranker.rerank(
                hyde_question,
                retrieved,
                k_rerank,
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

        # Coverage-aware confidence ------------------------------------
        # A content-bearing query whose answer surfaces the whole relevant
        # source is fully grounded even when per-chunk relevance is modest
        # (e.g. "summarize this resume" over a single small source).  Boost the
        # confidence in that case so a complete answer never reads as "Weak".
        display_confidence = await self._apply_confidence(
            question,
            reranked,
            mean_confidence,
        )

        logger.debug(
            "retrieve_context: retrieved=%d reranked=%d confidence=%.4f "
            "hyde=%.1fms embed=%.1fms retrieve=%.1fms rerank=%.1fms",
            len(retrieved),
            len(reranked),
            display_confidence,
            timings["hyde_ms"],
            timings["embed_ms"],
            timings["retrieve_ms"],
            timings["rerank_ms"],
        )
        return reranked, timings, display_confidence

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

    # A content-bearing query whose retrieved chunks are concentrated in a single
    # source ("tell me about source", "summarize this") identifies its target
    # source unambiguously, so the resulting overview is well-grounded even when
    # the cross-encoder's per-chunk relevance is only modest.  Confidence is
    # boosted to a tier matching how dominant the single source is in the
    # retrieved set.  The boost is gated by a minimum relevance so an off-topic
    # query (low per-chunk score) never reads as confident, and chitchat never
    # retrieves at all.
    # Focus tiers: (minimum focus ratio, confidence to report)
    _FOCUS_TIERS = (
        (0.90, 0.85),  # a single source dominates → Excellent
        (0.70, 0.65),  # clearly one source → Strong
        (0.55, 0.45),  # one source leads → Moderate
    )
    # Per-chunk relevance (reranker best score) must reach this before a focus
    # boost is applied — below it the query is treated as off-topic/no-match.
    _FOCUS_RELEVANCE_GATE = 0.20
    # Corpus-overview requests ("summarize this", "tell me about the source")
    # are scored low by the cross-encoder for a legitimate reason: a generic
    # request matches no particular passage strongly, even when the answer is
    # well grounded. They therefore get a lower floor than ordinary questions.
    #
    # They used to bypass the gate entirely, which was the actual defect: a
    # near-total non-match (best chunk 0.07 on a generic "what does this
    # repository do") was reported as 0.85 "Excellent" purely because
    # retrieval happened to stay inside one source. Concentration says *which*
    # source was read; it says nothing about whether the question was answered,
    # so it must never manufacture confidence on its own.
    _OVERVIEW_RELEVANCE_GATE = 0.12
    # Confidence is multiplied down by up to this fraction when the answer
    # asserts figures that appear nowhere in the retrieved text, scaled by the
    # share of unsupported claims. An answer whose every checkable claim is
    # invented should not read as moderately supported.
    _UNGROUNDED_PENALTY = 0.75
    # Floor after an ungrounded penalty. Kept equal to the reranker's display
    # floor so an ungrounded answer reads as "Weak" rather than as near-zero,
    # which the UI would render as a bug.
    _MIN_CONFIDENCE_AFTER_UNGROUNDED = 0.15

    async def _source_exclude_set(
        self,
        source_id: str | None,
        source_ids: set[str] | list[str] | None = None,
    ) -> set[str] | None:
        """Return source_ids to exclude so retrieval is scoped to the selection.

        With neither argument no filtering is applied.  ``source_id`` scopes to a
        single source and ``source_ids`` scopes to a chosen set (the project
        workspace selects one or many).  In both cases every currently-indexed
        source *outside* the selection is excluded, so the hybrid retrieval only
        ever returns chunks belonging to the selected sources.

        The known-source list is loaded from disk first.  Reading it in-memory
        without loading would return an empty set at the start of a process,
        which reads as "no sources to exclude" and silently drops the scope —
        the exact cause of a selected source being ignored on the first query.
        """
        if source_ids:
            selected = {sid.strip() for sid in source_ids if sid and sid.strip()}
        elif source_id and source_id.strip():
            selected = {source_id.strip()}
        else:
            return None
        if not selected:
            return None
        try:
            known = await self._faiss.get_source_ids_async()
        except Exception:  # pragma: no cover - defensive
            return None
        return {sid for sid in known if sid and sid not in selected}

    @staticmethod
    def _resolve_hyde(use_hyde: bool | None, question: str) -> bool:
        """Decide whether to run HyDE for this query.

        Precedence:
          1. Explicit ``use_hyde`` request flag (if not None).
          2. Global ``settings.USE_HYDE`` (if enabled).
          3. Auto mode (default): enable HyDE only for vague/generic queries
             so specific questions stay fast.
        """
        if use_hyde is not None:
            return use_hyde
        if settings.USE_HYDE:
            return True
        return _is_vague_query(question)

    async def _apply_confidence(
        self,
        question: str,
        reranked: list[RerankedChunk],
        base: float,
    ) -> float:
        """Return the confidence to report to the client.

        *base* is the reranker's per-chunk relevance confidence.  When a real,
        content-bearing query (never chitchat) is answered from a retrieved set
        concentrated in a single source, the answer is unambiguously about that
        source, so the confidence is raised to the matching focus tier (if that
        beats the per-chunk relevance).  A query that barely matches the source
        (base below ``_FOCUS_RELEVANCE_GATE``) or draws from several sources is
        left at its per-chunk relevance.
        """
        if not reranked or _is_chitchat(question):
            return base
        # Gate on the best *actual* chunk score, not on *base*.
        #
        # *base* comes from the reranker already lifted to its display floor, so
        # it can never fall below 0.15 and a gate set under that value is
        # unreachable — a genuine non-match would be read as merely "meets the
        # gate" and then boosted. The top chunk score is the un-floored
        # relevance signal, and it is what the gate was always meant to express.
        relevance = max(c.score for c in reranked)
        # A generic request about the corpus ("summarize this") gets a lower
        # floor than a specific question, because the cross-encoder scores such
        # a request low against raw article chunks even when the answer is well
        # grounded. That is a relaxation, not an exemption: below this, nothing
        # in the retrieved set addressed the question, and no amount of source
        # concentration makes the answer well supported.
        gate = self._OVERVIEW_RELEVANCE_GATE if _is_corpus_overview(question) else self._FOCUS_RELEVANCE_GATE
        if relevance < gate:
            return base

        source_counts: dict[str, int] = {}
        for c in reranked:
            sid = c.chunk.source_id
            if sid:
                source_counts[sid] = source_counts.get(sid, 0) + 1
        if not source_counts:
            return base

        dominant = max(source_counts, key=source_counts.get)
        focus = source_counts[dominant] / len(reranked)

        best = base
        for min_focus, tier_confidence in Orchestrator._FOCUS_TIERS:
            if focus >= min_focus and tier_confidence > best:
                best = tier_confidence
        logger.debug(
            "_apply_confidence: focus=%.3f dominant=%s chunks=%d total=%d base=%.4f relevance=%.4f → %.4f",
            focus,
            dominant,
            source_counts[dominant],
            len(reranked),
            base,
            relevance,
            best,
        )
        return best

    @staticmethod
    def _build_confidence(
        reranked: list[RerankedChunk],
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

    # Confidence at or below this level earns an explanation in the UI. Above it
    # the number speaks for itself and a caption would only be noise.
    _LOW_CONFIDENCE_CEILING = 0.40
    # A question of this many words or fewer is treated as carrying no topic of
    # its own; "give me details about it" is four words and one pronoun.
    _UNSPECIFIED_MAX_WORDS = 6
    _UNSPECIFIED_PRONOUNS = frozenset(
        {
            "it",
            "its",
            "this",
            "that",
            "these",
            "those",
            "them",
            "they",
            "their",
            "he",
            "him",
            "his",
            "she",
            "her",
            "hers",
        }
    )

    def _low_confidence_reason(
        self,
        question: str,
        reranked: list[RerankedChunk],
        confidence: float,
        *,
        ungrounded_claims: int | None = None,
    ) -> str | None:
        """Explain a low confidence score in terms the user can act on.

        A bare percentage is unactionable: "15%" does not say whether the
        question, the selection or the pipeline is at fault, so users tend to
        conclude the tool is broken. Each branch names a cause and the next
        action, ordered so the most specific explanation wins.

        Args:
            question:           The question as asked.
            reranked:           Chunks the reranker returned.
            confidence:         The final, post-penalty confidence.
            ungrounded_claims:  Count of checkable claims absent from the
                                retrieved text, or ``None`` if grounding was
                                never evaluated.

        Returns:
            A short sentence, or ``None`` when confidence is healthy.
        """
        if confidence > self._LOW_CONFIDENCE_CEILING:
            return None
        if ungrounded_claims:
            return (
                f"{ungrounded_claims} specific detail"
                f"{'s' if ungrounded_claims != 1 else ''} in this answer "
                "could not be found in your sources, so the score was reduced."
            )
        if not reranked:
            return "No passages matched this question, so the answer carries no source support."
        if self._is_underspecified_question(question):
            return (
                "This question has no topic words of its own, so it was matched "
                "against your sources blind. Name the subject to search for it "
                "properly."
            )
        return (
            "The retrieved passages did not closely match this question. "
            "Try naming the specific detail you need, or select a different source."
        )

    @staticmethod
    def _is_underspecified_question(question: str) -> bool:
        """Whether a question leans on a pronoun instead of naming its subject.

        "give me details about it" is short and built on a pronoun, so there is
        nothing for the retriever to match on. Longer questions, or ones that
        name a subject ("what did JUST do in 2008?"), are left alone.
        """
        words = _word_tokens(question)
        if not words or len(words) > Orchestrator._UNSPECIFIED_MAX_WORDS:
            return False
        return any(w in Orchestrator._UNSPECIFIED_PRONOUNS for w in words)

    def _grounded_confidence(
        self,
        confidence: float,
        answer: str,
        reranked: list[RerankedChunk],
        *,
        report: GroundingReport | None = None,
    ) -> float:
        """Reduce confidence when the answer asserts unsupported figures.

        Retrieval confidence describes how well the chunks matched the
        *question*; it says nothing about whether the *answer* is supported by
        them. This closes that gap: a figure, percentage, version or date in the
        answer that appears nowhere in the retrieved text is an invented
        specific, and no amount of good retrieval makes it trustworthy.

        The penalty scales with the share of unsupported claims rather than
        being all-or-nothing, so a single stray number does not erase an
        otherwise well-grounded answer. Answers with nothing checkable (a
        refusal, or a purely qualitative answer) are left alone.

        Args:
            confidence: Confidence from the retrieval side.
            answer:     Generated answer text.
            reranked:   Chunks the answer was supposed to come from.
            report:     Precomputed grounding report, so a caller that also
                        needs the unsupported-claim count does not pay for a
                        second scan of the same text.
        """
        if not reranked:
            return confidence
        # Full chunk text, never text_preview: a figure commonly sits past the
        # first 200 characters of its chunk, and checking the preview would
        # flag a correctly-sourced number as invented.
        if report is None:
            report = check_grounding(answer, [c.chunk.text for c in reranked])
        if report.is_grounded:
            return confidence

        penalty = 1.0 - report.support_ratio
        adjusted = confidence * (1.0 - self._UNGROUNDED_PENALTY * penalty)
        logger.warning(
            "grounding: %d of %d checkable claims unsupported %s — confidence %.4f -> %.4f",
            len(report.unsupported),
            report.checked,
            list(report.unsupported),
            confidence,
            adjusted,
        )
        return max(adjusted, self._MIN_CONFIDENCE_AFTER_UNGROUNDED)

    async def file_manifest(
        self,
        *,
        source_ids: set[str] | list[str] | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """Return the file paths indexed for the given sources.

        Scoped deliberately: in a workspace holding several repositories an
        unscoped listing would present every repo's files as one project.
        """
        cap = limit if limit is not None else settings.FILE_MANIFEST_MAX_PATHS
        selected = {s for s in (source_ids or []) if s}
        if not selected:
            return []
        return await self._bm25.list_source_paths(source_ids=selected, limit=cap)

    @observe(name="generate_answer")
    async def generate_answer(
        self,
        question: str,
        chunks: list[Chunk],
        file_manifest: list[str] | None = None,
    ) -> str:
        """Generate a complete answer from *chunks* for *question*."""
        built = self._prompt_builder.build(question, chunks, file_manifest=file_manifest)
        return await self._llm.generate(
            built.user_prompt,
            system_prompt=built.system_prompt,
        )

    @observe(name="stream_answer")
    async def stream_answer(
        self,
        question: str,
        chunks: list[Chunk],
        file_manifest: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Stream answer tokens for *question* grounded in *chunks*."""
        built = self._prompt_builder.build(question, chunks, file_manifest=file_manifest)
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
        source_id: str | None = None,
        source_ids: set[str] | list[str] | None = None,
        file_manifest: list[str] | None = None,
        use_knowledge_base: bool = True,
    ) -> GenerationResult:
        """Full RAG pipeline: retrieve → generate → return with sources and confidence.

        ``use_knowledge_base=False`` skips retrieval entirely and answers from
        the model's general knowledge, returning no sources.  Used when the user
        has not selected any source to ground the answer in.
        """

        if use_knowledge_base:
            # Unpack the new 3-tuple from retrieve_context
            reranked, timings, mean_confidence = await self.retrieve_context(
                question,
                top_k_retrieval=top_k_retrieval,
                top_k_rerank=top_k_rerank,
                use_hyde=use_hyde,
                source_id=source_id,
                source_ids=source_ids,
            )
        else:
            reranked, timings, mean_confidence = [], {}, 0.0
        # Time the LLM generation so it shows up in the latency breakdown
        # (previously the biggest cost was invisible to the client).
        t = time.perf_counter()
        answer_text = await self.generate_answer(
            question,
            [item.chunk for item in reranked],
            file_manifest=file_manifest,
        )
        timings["generate_ms"] = (time.perf_counter() - t) * 1000
        timings["total_ms"] = sum(v for v in timings.values() if isinstance(v, (int, float)))
        # Build ConfidenceMetrics and attach to GenerationResult
        reported = self._build_confidence(reranked, mean_confidence)
        # Retrieval confidence is about the question, not the answer. Verify the
        # answer's own checkable claims before reporting it as trustworthy.
        # The report is computed once and reused for the explanation below, so
        # the penalty and the message can never disagree about what was found.
        grounding = check_grounding(answer_text, [item.chunk.text for item in reranked]) if reranked else None
        adjusted = self._grounded_confidence(
            reported.answer_confidence,
            answer_text,
            reranked,
            report=grounding,
        )
        # Rebuilt so the coverage label tracks the adjusted number instead of
        # continuing to say "Excellent" over a penalised confidence.
        confidence = self._build_confidence(reranked, adjusted)
        reason = self._low_confidence_reason(
            question,
            reranked,
            confidence.answer_confidence,
            ungrounded_claims=0 if grounding is None or grounding.is_grounded else len(grounding.unsupported),
        )
        if reason is not None:
            confidence = replace(confidence, low_confidence_reason=reason)

        # Validate citation markers against the sources actually retrieved, and
        # return the rewritten answer. A model asked to cite can cite a passage
        # that was never supplied; a dead reference that looks authoritative is
        # worse than no citation, so out-of-range markers are stripped here
        # rather than shipped.
        citations = parse_citations(answer_text, len(reranked))
        if citations.discarded:
            logger.warning(
                "citations: dropped %d out-of-range marker(s) %s — the model cited a passage that was not retrieved",
                len(citations.discarded),
                list(citations.discarded),
            )

        return GenerationResult(
            answer=citations.text,
            sources=reranked,
            latency_ms=timings,
            confidence=confidence,
        )
