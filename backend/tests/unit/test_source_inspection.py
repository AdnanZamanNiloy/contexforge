"""Unit tests for the per-source inspection builders.

``build_source_detail`` and ``build_source_content`` turn a source's indexed
chunks into what the source detail view shows. They are pure functions over
already-stored data, so these tests need no vector store, no loader and no
provider — only chunk objects shaped like the ones FAISS returns.

The behaviour worth pinning is the awkward parts: chunk ordering for multi-file
sources, the repr-encoded metadata these loaders emit, and the honesty of the
"no text extracted" signal.
"""

from __future__ import annotations

from types import MappingProxyType

from app.sources.inspection import (
    MAX_CONTENT_CHUNKS,
    build_source_content,
    build_source_detail,
)


def _chunk(chunk_id, text, **metadata):
    """A stand-in for the FAISS Chunk dataclass."""
    return type(
        "FakeChunk",
        (),
        {
            "chunk_id": chunk_id,
            "text": text,
            "metadata": MappingProxyType(dict(metadata)),
            "source_id": metadata.get("source_id", "s1"),
        },
    )()


def _web_chunks():
    return [
        _chunk(
            "s1:0",
            "Universe page text.",
            source_id="s1",
            title="A university",
            source="web",
            source_type="web",
            url="https://example.org/uni",
            language="en",
            keywords="['university', 'students']",
            named_entities="[{'text': 'Other', 'label': 'REGEX'}]",
            chunk_index=0,
        ),
        _chunk(
            "s1:1",
            "Ranking table follows.",
            source_id="s1",
            title="A university",
            source="web",
            source_type="web",
            url="https://example.org/uni",
            language="en",
            keywords="['university']",
            named_entities="[{'text': 'Other', 'label': 'REGEX'}]",
            chunk_index=1,
        ),
    ]


class TestBuildSourceDetail:
    def test_summarises_a_web_source(self):
        detail = build_source_detail(_web_chunks(), source_id="s1", derived_title="A university")

        assert detail.source_id == "s1"
        assert detail.source_type == "web"
        assert detail.url == "https://example.org/uni"
        assert detail.language == "en"
        assert detail.chunk_count == 2
        assert detail.char_count == len("Universe page text.") + len("Ranking table follows.")

    def test_a_rename_wins_but_the_derived_title_is_kept(self):
        detail = build_source_detail(
            _web_chunks(),
            source_id="s1",
            derived_title="A university",
            title_override="My uni notes",
        )

        assert detail.title == "My uni notes"
        assert detail.derived_title == "A university"
        assert detail.renamed is True

    def test_a_matching_override_is_not_reported_as_renamed(self):
        detail = build_source_detail(
            _web_chunks(),
            source_id="s1",
            derived_title="A university",
            title_override="A university",
        )

        assert detail.renamed is False

    def test_decodes_repr_encoded_keywords_and_entities(self):
        detail = build_source_detail(_web_chunks(), source_id="s1", derived_title="A university")

        assert detail.keywords == ["university", "students"]
        assert detail.named_entities == [{"text": "Other", "label": "REGEX"}]

    def test_survives_unparseable_metadata(self):
        chunks = [
            _chunk(
                "s1:0",
                "text",
                title="Doc",
                source_type="pdf",
                keywords="not valid at all {",
                named_entities="[{'text': 'X', 'label':",
            )
        ]

        detail = build_source_detail(chunks, source_id="s1", derived_title="Doc")

        # Best-effort enrichment degrades to empty; the detail view still works.
        assert detail.keywords == []
        assert detail.named_entities == []

    def test_reports_pdf_page_counts_and_scanned_state(self):
        chunks = [
            _chunk(
                "s1:0",
                "Invoice body",
                title="PAYMENT RECEIPT",
                source_type="pdf",
                filename="invoice.pdf",
                page_count="2",
                non_empty_pages="0",
                is_scanned="True",
            )
        ]

        detail = build_source_detail(chunks, source_id="s1", derived_title="PAYMENT RECEIPT")

        assert detail.page_count == 2
        assert detail.non_empty_pages == 0
        assert detail.is_scanned is True

    def test_scanned_pdf_is_visible_as_zero_extractable_text(self):
        # The whole point of the view: a scan that extracted nothing must be
        # obvious, not an empty-looking source that still answers questions.
        chunks = [
            _chunk(
                "s1:0",
                "",
                title="Scanned contract",
                source_type="pdf",
                page_count="4",
                non_empty_pages="0",
                is_scanned="True",
            )
        ]

        detail = build_source_detail(chunks, source_id="s1", derived_title="Scanned contract")

        assert detail.char_count == 0
        assert detail.chunk_count == 1
        assert detail.is_scanned is True

    def test_collects_unique_file_paths_for_a_repository(self):
        chunks = [
            _chunk(
                "s1:a:0", "one", title="MIT", source_type="github", repo="owner/name", path="LICENSE", chunk_index=0
            ),
            _chunk(
                "s1:a:1", "two", title="MIT", source_type="github", repo="owner/name", path="LICENSE", chunk_index=1
            ),
            _chunk(
                "s1:b:0", "three", title="MIT", source_type="github", repo="owner/name", path="README.md", chunk_index=0
            ),
        ]

        detail = build_source_detail(chunks, source_id="s1", derived_title="owner/name")

        assert detail.file_paths == ["LICENSE", "README.md"]

    def test_reports_the_original_upload_as_unavailable(self):
        # ContextForge indexes uploads without retaining the bytes, so the view
        # must say so rather than offering a download that cannot work.
        detail = build_source_detail(_web_chunks(), source_id="s1", derived_title="A university")

        assert detail.file_available is False

    def test_handles_a_source_with_no_chunks(self):
        detail = build_source_detail([], source_id="s1", derived_title="Nothing")

        assert detail.chunk_count == 0
        assert detail.char_count == 0
        assert detail.keywords == []
        assert detail.source_type == "unknown"


class TestBuildSourceContent:
    def test_returns_every_chunk_when_under_the_cap(self):
        content = build_source_content(_web_chunks(), source_id="s1")

        assert content.chunk_count == 2
        assert content.total_chunks == 2
        assert content.truncated is False
        assert content.chunks[0].text == "Universe page text."

    def test_orders_multi_file_sources_by_path_then_position(self):
        # Every file restarts chunk numbering at 0, so sorting on the index
        # alone would interleave unrelated files. Paths sort lexicographically
        # ("README.md" before "backend/app.py", since uppercase sorts first),
        # and within one file the recorded position wins.
        chunks = [
            _chunk("s1:b:0", "readme", source_type="github", repo="o/n", path="README.md", chunk_index=0),
            _chunk("s1:a:1", "app part 2", source_type="github", repo="o/n", path="backend/app.py", chunk_index=1),
            _chunk("s1:a:0", "app part 1", source_type="github", repo="o/n", path="backend/app.py", chunk_index=0),
        ]

        content = build_source_content(chunks, source_id="s1")

        assert [c.text for c in content.chunks] == ["readme", "app part 1", "app part 2"]

    def test_caps_the_response_and_flags_truncation(self):
        chunks = [
            _chunk(f"s1:{i}", f"chunk {i}", source_type="web", title="Doc", chunk_index=i)
            for i in range(MAX_CONTENT_CHUNKS + 25)
        ]

        content = build_source_content(chunks, source_id="s1")

        assert content.chunk_count == MAX_CONTENT_CHUNKS
        assert content.total_chunks == MAX_CONTENT_CHUNKS + 25
        assert content.truncated is True

    def test_carries_the_path_and_index_onto_each_chunk(self):
        content = build_source_content(
            [
                _chunk(
                    "s1:a:7",
                    "text",
                    source_type="github",
                    repo="o/n",
                    path="backend/app.py",
                    chunk_index=7,
                )
            ],
            source_id="s1",
        )

        chunk = content.chunks[0]
        assert chunk.chunk_id == "s1:a:7"
        assert chunk.path == "backend/app.py"
        assert chunk.chunk_index == 7
