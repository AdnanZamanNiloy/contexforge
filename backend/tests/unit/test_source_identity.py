"""Source identity: the same source must always resolve to the same id.

Every type except GitHub used to be given a fresh ``uuid4()`` at ingest time, so
pasting the same article URL twice produced two sources with the same title,
both answering queries and neither distinguishable in the sidebar. These tests
pin the replacement behaviour, and in particular the cases where two spellings of
one document must collapse to one source.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.sources.identity import content_source_id, legacy_source_id_for, normalize_url, url_source_id


class TestNormalizeUrl:
    def test_lowercases_scheme_and_host(self) -> None:
        assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"

    def test_drops_the_fragment(self) -> None:
        # A fragment addresses a position inside a page, not a different page.
        assert normalize_url("https://example.com/a#section-2") == "https://example.com/a"

    def test_drops_a_default_port(self) -> None:
        assert normalize_url("https://example.com:443/a") == "https://example.com/a"
        assert normalize_url("http://example.com:80/a") == "http://example.com/a"

    def test_keeps_a_non_default_port(self) -> None:
        assert normalize_url("http://example.com:8080/a") == "http://example.com:8080/a"

    def test_drops_a_trailing_slash_except_at_the_root(self) -> None:
        assert normalize_url("https://example.com/a/") == "https://example.com/a"
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_sorts_query_parameters(self) -> None:
        # Shared links reorder query strings; the document is unchanged.
        assert normalize_url("https://e.com/a?b=2&a=1") == normalize_url("https://e.com/a?a=1&b=2")

    @pytest.mark.parametrize("param", ["utm_source", "utm_medium", "gclid", "fbclid", "mc_cid", "ref"])
    def test_drops_tracking_parameters(self, param: str) -> None:
        # Left in, a campaign tag makes every shared link a different document.
        assert normalize_url(f"https://e.com/a?{param}=x") == "https://e.com/a"

    def test_keeps_meaningful_query_parameters(self) -> None:
        assert normalize_url("https://e.com/a?id=7&page=2") == "https://e.com/a?id=7&page=2"

    def test_keeps_the_scheme(self) -> None:
        # http and https can serve different content; merging them silently would
        # be a worse bug than the rare duplicate this guards against.
        assert normalize_url("http://e.com/a") != normalize_url("https://e.com/a")

    def test_keeps_path_case(self) -> None:
        assert normalize_url("https://e.com/Page") != normalize_url("https://e.com/page")

    def test_survives_input_it_cannot_parse(self) -> None:
        # Identity must never be the reason an ingest fails.
        assert normalize_url("not a url") == "not a url"
        assert normalize_url("") == ""


class TestUrlSourceId:
    def test_is_stable_for_the_same_url(self) -> None:
        assert url_source_id("web", "https://example.com/a") == url_source_id("web", "https://example.com/a")

    def test_collapses_cosmetic_url_differences(self) -> None:
        canonical = url_source_id("web", "https://Example.com/a/?utm_source=x#top")
        assert url_source_id("web", "https://example.com/a") == canonical

    def test_distinguishes_different_documents(self) -> None:
        assert url_source_id("web", "https://example.com/a") != url_source_id("web", "https://example.com/b")

    def test_prefixes_with_the_type(self) -> None:
        assert url_source_id("web", "https://example.com/a").startswith("web:")

    def test_github_uses_the_readable_repo_form(self) -> None:
        assert url_source_id("github", "https://github.com/owner/name") == "repo:owner/name"
        assert url_source_id("github", "https://github.com/owner/name.git") == "repo:owner/name"
        assert url_source_id("github", "https://www.github.com/owner/name") == "repo:owner/name"

    def test_github_rejects_a_non_repository_url(self) -> None:
        with pytest.raises(ValueError, match="GitHub"):
            url_source_id("github", "https://example.com/a")

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
        ],
    )
    def test_every_youtube_url_shape_resolves_to_the_video(self, url: str) -> None:
        # The same video shared five different ways is one source, not five.
        assert url_source_id("youtube", url) == "youtube:dQw4w9WgXcQ"

    def test_youtube_falls_back_to_a_url_hash_when_unparseable(self) -> None:
        # A malformed YouTube URL is the loader's error to report precisely, not
        # a reason for identity to raise.
        source_id = url_source_id("youtube", "https://www.youtube.com/not-a-video")
        assert source_id.startswith("youtube:")


class TestContentSourceId:
    def test_identical_bytes_are_one_source(self) -> None:
        assert content_source_id("pdf", b"%PDF-1.7 same") == content_source_id("pdf", b"%PDF-1.7 same")

    def test_different_bytes_are_different_sources(self) -> None:
        # A genuinely revised document must not silently overwrite the old one.
        assert content_source_id("pdf", b"one") != content_source_id("pdf", b"two")

    def test_the_same_bytes_under_two_names_is_one_source(self) -> None:
        assert content_source_id("docx", b"body") == content_source_id("docx", b"body")

    def test_type_is_part_of_the_identity(self) -> None:
        assert content_source_id("pdf", b"x") != content_source_id("docx", b"x")

    def test_text_ignores_line_endings_and_outer_whitespace(self) -> None:
        # Pasting the same text from two editors should not fork the source.
        assert content_source_id("text", "hello\r\nworld") == content_source_id("text", "  hello\nworld\n")


class TestLegacyAdoption:
    INFO: ClassVar[list[dict]] = [
        {"source_id": "e9e7200a-1", "type": "web", "url": "https://en.wikipedia.org/wiki/SUST"},
        {"source_id": "4b1de1b1-2", "type": "web", "url": "https://en.wikipedia.org/wiki/MBSTU"},
        {"source_id": "repo:owner/name", "type": "github", "url": ""},
    ]

    def test_finds_a_legacy_source_with_the_same_url(self) -> None:
        found = legacy_source_id_for(self.INFO, source_type="web", url="https://en.wikipedia.org/wiki/SUST")
        assert found == "e9e7200a-1"

    def test_matches_through_cosmetic_url_differences(self) -> None:
        # This is the upgrade repair path: an existing UUID source is adopted
        # rather than duplicated by the new deterministic id.
        found = legacy_source_id_for(
            self.INFO,
            source_type="web",
            url="HTTPS://en.wikipedia.org/wiki/SUST/?utm_source=chat#top",
        )
        assert found == "e9e7200a-1"

    def test_does_not_match_a_different_document(self) -> None:
        assert legacy_source_id_for(self.INFO, source_type="web", url="https://en.wikipedia.org/wiki/Other") is None

    def test_does_not_match_across_types(self) -> None:
        # A GitHub entry with no URL must not be adopted for a web ingest.
        assert legacy_source_id_for(self.INFO, source_type="web", url="") is None

    def test_tolerates_an_empty_list(self) -> None:
        assert legacy_source_id_for([], source_type="web", url="https://example.com") is None
