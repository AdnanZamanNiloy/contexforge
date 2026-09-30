import pytest

from core.orchestrator import _STRUCTURE_MAX_WORDS, _is_structure_question
from core.retrieval.reranker import _MAX_CHUNKS_PER_SOURCE, Reranker, _diversify
from core.types import Chunk, RetrievedChunk


class FakeModel:
    def predict(self, pairs):
        return [float(len(pair[1])) for pair in pairs]


@pytest.mark.asyncio
async def test_reranker_uses_scores(monkeypatch) -> None:
    reranker = Reranker()

    def fake_load_model():
        reranker._model = FakeModel()

    monkeypatch.setattr(reranker, "_load_model_sync", fake_load_model)

    candidates = [
        RetrievedChunk(chunk=Chunk(chunk_id="c1", text="short", metadata={}), score=0.1),
        RetrievedChunk(chunk=Chunk(chunk_id="c2", text="much longer", metadata={}), score=0.2),
    ]
    results, mean_confidence = await reranker.rerank("query", candidates, top_k=1)
    assert results[0].chunk.chunk_id == "c2"
    assert results[0].rank == 1
    assert mean_confidence > 0


def _chunk(cid: str, sid: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(chunk_id=cid, text=f"{cid} text", source_id=sid),
        score=0.1,
    )


def test_diversify_keeps_every_source_when_one_dominates() -> None:
    """A dominant source cannot crowd a second source out of the top-k."""
    # 6 chunks from "doc-a" score highest, 1 chunk from "doc-b" scores lowest.
    scored = [(_chunk(f"a{i}", "doc-a"), 0.9 - 0.1 * i) for i in range(6)] + [(_chunk("b1", "doc-b"), 0.05)]
    top_k = 5

    result = _diversify(scored, top_k)

    assert len(result) == top_k
    # doc-b's single chunk must survive despite the relevance gap.
    assert any(item[0].chunk.source_id == "doc-b" for item in result)


def test_diversify_preserves_relevance_order_for_single_source() -> None:
    """A single-source candidate list is returned in raw relevance order."""
    scored = [
        (_chunk("a1", "doc-a"), 0.9),
        (_chunk("a2", "doc-a"), 0.8),
        (_chunk("a3", "doc-a"), 0.7),
        (_chunk("a4", "doc-a"), 0.6),
    ]
    result = _diversify(scored, top_k=3)
    assert [item[0].chunk.chunk_id for item in result] == ["a1", "a2", "a3"]


def test_diversify_caps_any_one_source() -> None:
    """No single source exceeds the per-source cap in a mixed pool."""
    scored = [(_chunk(f"a{i}", "doc-a"), 0.95 - 0.01 * i) for i in range(20)] + [
        (_chunk(f"b{i}", "doc-b"), 0.4 - 0.01 * i) for i in range(10)
    ]
    result = _diversify(scored, top_k=8)

    src_a = sum(1 for item in result if item[0].chunk.source_id == "doc-a")
    src_b = sum(1 for item in result if item[0].chunk.source_id == "doc-b")
    assert src_a <= _MAX_CHUNKS_PER_SOURCE
    assert src_b >= 1


def test_diversify_keeps_top_k_when_candidates_fit() -> None:
    """When candidates fit in top_k they are all returned."""
    scored = [
        (_chunk("a1", "doc-a"), 0.9),
        (_chunk("b1", "doc-b"), 0.8),
    ]
    assert _diversify(scored, top_k=5) == scored


def test_diversify_caps_a_single_source_at_the_requested_ceiling() -> None:
    """The per-source ceiling applies even when there is nothing to diversify.

    This is what makes the context depth work for one selected document. The cap
    used to be skipped for a single group on the grounds that diversification was
    unnecessary, so a wider depth changed nothing at all and the buttons looked
    broken.
    """
    scored = [(_chunk(f"a{i}", "doc-a"), 0.9 - 0.01 * i) for i in range(20)]

    assert len(_diversify(scored, top_k=20, max_per_source=4)) == 4
    assert len(_diversify(scored, top_k=20, max_per_source=12)) == 12


def test_diversify_widening_the_ceiling_never_reads_less() -> None:
    """A wider depth must not return fewer chunks than a narrower one."""
    scored = [(_chunk(f"a{i}", "doc-a"), 0.9 - 0.01 * i) for i in range(20)]

    narrow = _diversify(scored, top_k=25, max_per_source=5)
    wide = _diversify(scored, top_k=25, max_per_source=12)

    assert len(narrow) < len(wide)
    # Both are prefixes of the same relevance order, so widening only adds.
    assert [i[0].chunk.chunk_id for i in narrow] == [i[0].chunk.chunk_id for i in wide][: len(narrow)]


def test_diversify_still_reports_every_source_in_a_mixed_pool() -> None:
    """Raising the ceiling must not undo coverage for multi-source questions."""
    scored = [(_chunk(f"a{i}", "doc-a"), 0.95 - 0.01 * i) for i in range(20)] + [
        (_chunk(f"b{i}", "doc-b"), 0.4 - 0.01 * i) for i in range(10)
    ]

    result = _diversify(scored, top_k=14, max_per_source=12)

    assert any(item[0].chunk.source_id == "doc-b" for item in result)
    assert sum(1 for item in result if item[0].chunk.source_id == "doc-a") <= 12


@pytest.mark.asyncio
async def test_rerank_passes_the_per_source_cap_through(monkeypatch) -> None:
    """The orchestrator's depth limit has to reach the selection, not just the UI."""
    reranker = Reranker()
    monkeypatch.setattr(reranker, "_load_model_sync", lambda: setattr(reranker, "_model", FakeModel()))

    candidates = [_chunk(f"a{i}", "doc-a") for i in range(10)]

    narrow, _ = await reranker.rerank("query", candidates, top_k=10, per_source_cap=3)
    wide, _ = await reranker.rerank("query", candidates, top_k=10, per_source_cap=8)

    assert len(narrow) == 3
    assert len(wide) == 8


@pytest.mark.asyncio
async def test_reranker_surfaces_second_source(monkeypatch) -> None:
    """The pipeline reranker surfaces a weaker second source in the top-k."""
    reranker = Reranker()

    def fake_load_model():
        reranker._model = FakeModel()

    monkeypatch.setattr(reranker, "_load_model_sync", fake_load_model)

    # FakeModel scores by text length: longer text → higher score.
    candidates = [
        RetrievedChunk(
            chunk=Chunk(chunk_id=f"a{i}", text="x" * (100 - i), source_id="doc-a"),
            score=0.1,
        )
        for i in range(5)
    ] + [
        RetrievedChunk(
            chunk=Chunk(chunk_id="b1", text="short but distinct source", source_id="doc-b"),
            score=0.1,
        )
    ]
    top_k = 4
    results, _ = await reranker.rerank("query", candidates, top_k=top_k)
    selected_sources = {r.chunk.source_id for r in results}
    assert "doc-b" in selected_sources


def test_rerank_token_budget_is_capped(monkeypatch) -> None:
    """Reranking runs on every request, so its token budget is a latency tax.

    Scoring 20 full 512-token chunks measured ~2.2s per query, roughly a
    quarter of the whole request. The cap is what keeps that down, so it is
    asserted here rather than left to a comment nobody re-reads.
    """
    from app.config.settings import settings

    assert settings.RERANK_MAX_LENGTH > 0, "a zero budget would score nothing"
    assert settings.RERANK_MAX_LENGTH <= 512, (
        "512 is the tokenizer default and is the slow path this cap exists to avoid; "
        "if a larger budget is genuinely needed, re-measure first"
    )

    captured: dict[str, int] = {}

    class FakeCrossEncoder:
        def __init__(self, model_name, *, max_length):
            captured["model"] = model_name
            captured["max_length"] = max_length

    import sys
    import types

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.CrossEncoder = FakeCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    reranker = Reranker()
    reranker._load_model_sync()

    assert captured["model"] == settings.RERANK_MODEL
    assert captured["max_length"] == settings.RERANK_MAX_LENGTH, (
        "the configured budget must reach the tokenizer, otherwise the cap is "
        "declared in settings but never applied and rerank stays slow"
    )


class TestFileLevelCoverage:
    """A single repository is one source_id, so source-level diversification
    silently does nothing for the most common case.

    Measured before the fix: on a 25-chunk repo, four of five top-k slots went
    to copies of the same SVG and the model was left able to describe only a
    license and an icon. The file is the unit that should not be crowded out.
    """

    def _scored(self, paths):
        return [
            (
                RetrievedChunk(
                    chunk=Chunk(
                        chunk_id=f"c{i}",
                        text=f"body {i}",
                        metadata={"path": p},
                        source_id="repo:acme/thing",
                    ),
                    score=1.0,
                ),
                1.0 - i * 0.01,
            )
            for i, p in enumerate(paths)
        ]

    def test_repeated_files_cannot_fill_every_slot(self) -> None:
        scored = self._scored(
            [
                "LICENSE",
                "frontend/src/logo.svg",
                "frontend/src/logo.svg",
                "frontend/src/logo.svg",
                "frontend/src/logo.svg",
                "backend/app.py",
                "README.md",
            ]
        )
        chosen = _diversify(scored, 5)
        paths = [c[0].chunk.metadata["path"] for c in chosen]

        # Every distinct file in the candidate set is represented. The one
        # surplus slot goes to a second chunk of a file already within
        # _MAX_CHUNKS_PER_SOURCE, which is intended.
        assert set(paths) == {"LICENSE", "frontend/src/logo.svg", "backend/app.py", "README.md"}
        assert paths.count("frontend/src/logo.svg") < 4, "one file should no longer take four of five slots"

    def test_a_single_repeated_file_still_yields_its_best_chunks(self) -> None:
        # With nothing else to show, coverage must not starve a legitimate
        # multi-chunk answer from the one relevant file.
        scored = self._scored(["a.py", "a.py", "a.py"])
        chosen = _diversify(scored, 2)
        assert len(chosen) == 2
        assert all(c[0].chunk.metadata["path"] == "a.py" for c in chosen)

    def test_chunks_without_a_path_still_group_by_source(self) -> None:
        scored = [
            (
                RetrievedChunk(
                    chunk=Chunk(chunk_id=f"c{i}", text="x", source_id="src-a" if i < 3 else "src-b"),
                    score=1.0 - i * 0.01,
                ),
                1.0 - i * 0.01,
            )
            for i in range(5)
        ]
        chosen = _diversify(scored, 2)
        assert {c[0].chunk.source_id for c in chosen} == {"src-a", "src-b"}

    def test_result_is_still_ranked_best_first(self) -> None:
        scored = self._scored(["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"])
        chosen = _diversify(scored, 4)
        scores = [c[1] for c in chosen]
        assert scores == sorted(scores, reverse=True)


class TestStructureQuestionDetection:
    """The manifest is attached only where it helps.

    Attaching a file listing to an ordinary question wastes tokens and invites
    the model to describe the listing instead of answering, so the detector has
    to stay narrow.
    """

    @pytest.mark.parametrize(
        "question",
        [
            "give me repo file structure",
            "what files are in this repo",
            "show the folder structure",
            "list all files",
            "which files does it have",
            "project structure please",
        ],
    )
    def test_structure_questions_are_detected(self, question: str) -> None:
        assert _is_structure_question(question) is True

    @pytest.mark.parametrize(
        "question",
        [
            "what accuracy does the model report",
            "how do I run the app",
            "list the dependencies of this project",
            "explain the structure of the JSON payload the API returns",
        ],
    )
    def test_ordinary_questions_are_not_detected(self, question: str) -> None:
        assert _is_structure_question(question) is False

    def test_a_long_question_is_not_a_structure_question(self) -> None:
        # A sprawling question that happens to contain "file structure" is
        # asking for more than a tree, and handing it a manifest would push the
        # model toward describing the listing instead of answering.
        long_q = (
            "please tell me about the file structure of this repository and "
            "also explain how the machine learning model works, what the "
            "accuracy figures are, and where the training happens"
        )
        assert len(long_q.split()) > _STRUCTURE_MAX_WORDS
        assert _is_structure_question(long_q) is False
