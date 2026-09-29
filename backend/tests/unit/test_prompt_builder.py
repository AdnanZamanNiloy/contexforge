from __future__ import annotations

from core.generation.prompt_builder import PromptBuilder
from core.types import Chunk


class TestSourceLabels:
    """Each passage must be labelled with the file it came from.

    Regression: the context was built from chunk text alone, so the model was
    never shown a single file path. A question like "give me the repo file
    structure" was then unanswerable, and the model said so truthfully - the
    paths existed in chunk metadata and were simply not passed through. That
    answer was wrong from the user's point of view and correct from the model's,
    which is the worst kind of bug to diagnose from the outside.
    """

    def test_a_chunk_path_reaches_the_prompt(self) -> None:
        chunks = [
            Chunk(
                chunk_id="c1",
                text="from fastapi import FastAPI",
                metadata={"path": "backend/app.py"},
            )
        ]
        built = PromptBuilder().build("give me repo file structure", chunks)
        assert "backend/app.py" in built.user_prompt

    def test_paths_are_ordered_by_precedence(self) -> None:
        # Mirrors how the Sources panel resolves a title, so the label the model
        # reasons about and the one the reader sees agree.
        chunks = [
            Chunk(chunk_id="c1", text="x", metadata={"path": "a/b.py", "title": "ignored"}),
        ]
        built = PromptBuilder().build("q", chunks)
        assert "a/b.py" in built.user_prompt
        assert "ignored" not in built.user_prompt

    def test_title_is_used_when_there_is_no_path(self) -> None:
        chunks = [Chunk(chunk_id="c1", text="x", metadata={"title": "Annual Report"})]
        assert "Annual Report" in PromptBuilder().build("q", chunks).user_prompt

    def test_source_id_is_the_last_resort(self) -> None:
        chunks = [Chunk(chunk_id="c1", text="x", metadata={}, source_id="repo:acme/thing")]
        built = PromptBuilder().build("q", chunks)
        assert "repo:acme/thing" in built.user_prompt

    def test_an_unidentifiable_chunk_gets_no_placeholder(self) -> None:
        # A placeholder the model could quote back is worse than no label.
        chunks = [Chunk(chunk_id="c1", text="body text", metadata={}, source_id=None)]
        built = PromptBuilder().build("q", chunks)
        assert "file:" not in built.user_prompt
        assert "body text" in built.user_prompt

    def test_every_passage_is_labelled_and_numbered(self) -> None:
        chunks = [
            Chunk(chunk_id="c1", text="one", metadata={"path": "a.py"}),
            Chunk(chunk_id="c2", text="two", metadata={"path": "b.py"}),
            Chunk(chunk_id="c3", text="three", metadata={}),
        ]
        prompt = PromptBuilder().build("q", chunks).user_prompt
        assert "[1] file: a.py" in prompt
        assert "[2] file: b.py" in prompt
        assert "[3] three" in prompt, "an unlabelled passage still gets its number"

    def test_numbering_matches_citation_marker_order(self) -> None:
        # [n] must point at the nth source in the response, or every citation
        # resolves to the wrong file.
        chunks = [
            Chunk(chunk_id=f"c{i}", text=f"body {i}", metadata={"path": f"f{i}.py"})
            for i in range(1, 4)
        ]
        prompt = PromptBuilder().build("q", chunks).user_prompt
        for i, chunk in enumerate(chunks, start=1):
            marker = f"[{i}] file: {chunk.metadata['path']}"
            assert marker in prompt
            assert prompt.index(marker) < prompt.index(f"body {i}")


class TestFileManifest:
    """A structure question must be answerable from the whole index.

    Retrieval ranks chunks, so the top-k alone can only name the files that
    happened to rank. On a 19-file repository a five-chunk top-k showed a
    backend directory holding one file, which is both incomplete and wrong.
    """

    def test_a_manifest_is_attached_to_the_prompt(self) -> None:
        chunks = [Chunk(chunk_id="c1", text="body", metadata={"path": "a.py"})]
        paths = ["a.py", "backend/app.py", "backend/requirements.txt"]
        prompt = PromptBuilder().build("give me repo file structure", chunks, file_manifest=paths).user_prompt
        assert "FILE MANIFEST" in prompt
        for path in paths:
            assert path in prompt

    def test_no_manifest_means_no_manifest_block(self) -> None:
        chunks = [Chunk(chunk_id="c1", text="body", metadata={"path": "a.py"})]
        assert "FILE MANIFEST" not in PromptBuilder().build("q", chunks).user_prompt
        assert "FILE MANIFEST" not in PromptBuilder().build("q", chunks, file_manifest=[]).user_prompt

    def test_the_listing_is_separated_from_the_passages(self) -> None:
        # It must be visibly distinct so the model treats it as an inventory
        # rather than as evidence to reason from.
        chunks = [Chunk(chunk_id="c1", text="passage body", metadata={"path": "a.py"})]
        prompt = PromptBuilder().build("q", chunks, file_manifest=["a.py", "b.py"]).user_prompt
        manifest_at = prompt.index("FILE MANIFEST")
        passage_at = prompt.index("passage body")
        assert passage_at < manifest_at, "passages come first; the listing follows"
        assert "```" in prompt[manifest_at:], "the listing is fenced"

    def test_manifest_lists_files_with_no_retrieved_passage(self) -> None:
        chunks = [Chunk(chunk_id="c1", text="body", metadata={"path": "a.py"})]
        prompt = PromptBuilder().build("q", chunks, file_manifest=["a.py", "never-retrieved.py"]).user_prompt
        assert "never-retrieved.py" in prompt
