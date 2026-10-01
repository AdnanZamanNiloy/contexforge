"""Ingestion must be idempotent: the same source replaces, never duplicates.

These cover the behaviour rather than the id scheme itself (which
``test_source_identity`` pins). The ordering guarantee matters most: a loader is
where ingestion normally fails — a dead link, a rate limit, a PDF that will not
parse — and if the existing chunks were deleted first, "that URL did not work"
would become "that source is gone".
"""

from __future__ import annotations

import pytest

from app.schemas.ingest import IngestRequest
from app.services.ingest_service import IngestService
from core.types import Document


class _RecordingOrchestrator:
    """Records the call order so the load/delete/index sequence can be asserted."""

    def __init__(self, *, existing: list[dict] | None = None) -> None:
        self.calls: list[str] = []
        self._infos = existing or []

    async def get_source_info(self) -> list[dict]:
        self.calls.append("get_source_info")
        return list(self._infos)

    async def delete_source(self, source_id: str) -> int:
        self.calls.append(f"delete_source:{source_id}")
        return 1

    async def ingest(self, documents, use_code_chunker: bool = False) -> int:
        self.calls.append("ingest")
        return len(documents)


class _StubLoader:
    """Loader that records being called and can be made to fail."""

    def __init__(self, orchestrator_calls: list[str], *, fail: bool = False) -> None:
        self._calls = orchestrator_calls
        self._fail = fail

    async def load(self, source, source_id, metadata=None, filename=None) -> list[Document]:
        self._calls.append("load")
        if self._fail:
            raise RuntimeError("upstream is down")
        return [Document(document_id=f"d-{source_id}", text=f"body of {source}", metadata=metadata or {})]


def _service(orchestrator: _RecordingOrchestrator, *, fail: bool = False) -> tuple[IngestService, list[str]]:
    calls = orchestrator.calls
    return IngestService(orchestrator, {"web": _StubLoader(calls, fail=fail)}), calls


class TestIngestSourceReplaces:
    @pytest.mark.asyncio
    async def test_a_first_ingest_does_not_delete_anything(self) -> None:
        orch = _RecordingOrchestrator(existing=[])
        service, _ = _service(orch)

        source_id, chunks, replaced = await service.ingest_source(
            IngestRequest(source_type="web", source="https://example.com/a")
        )

        assert replaced is False
        assert chunks == 1
        assert source_id.startswith("web:")
        assert not any(c.startswith("delete_source") for c in orch.calls)

    @pytest.mark.asyncio
    async def test_re_ingesting_the_same_url_replaces_in_place(self) -> None:
        # The bug: a fresh uuid4 each time, so the same article became two sources.
        orch = _RecordingOrchestrator()
        service, _ = _service(orch)

        first_id, _, _ = await service.ingest_source(IngestRequest(source_type="web", source="https://example.com/a"))
        # The store now reports that source as present.
        orch._infos = [{"source_id": first_id, "type": "web", "url": "https://example.com/a"}]
        orch.calls.clear()

        second_id, _, replaced = await service.ingest_source(
            IngestRequest(source_type="web", source="https://example.com/a")
        )

        assert second_id == first_id, "the same URL must resolve to the same source id"
        assert replaced is True
        assert f"delete_source:{first_id}" in orch.calls

    @pytest.mark.asyncio
    async def test_load_happens_before_the_existing_chunks_are_deleted(self) -> None:
        orch = _RecordingOrchestrator()
        service, _ = _service(orch)

        first_id, _, _ = await service.ingest_source(IngestRequest(source_type="web", source="https://example.com/a"))
        orch._infos = [{"source_id": first_id, "type": "web", "url": "https://example.com/a"}]
        orch.calls.clear()

        await service.ingest_source(IngestRequest(source_type="web", source="https://example.com/a"))

        assert orch.calls.index("load") < orch.calls.index(f"delete_source:{first_id}")
        assert orch.calls.index(f"delete_source:{first_id}") < orch.calls.index("ingest")

    @pytest.mark.asyncio
    async def test_a_loader_failure_leaves_the_existing_source_intact(self) -> None:
        # The whole point of loading first: a bad URL must not cost the user the
        # copy they already had.
        orch = _RecordingOrchestrator()
        good, _ = _service(orch)
        first_id, _, _ = await good.ingest_source(IngestRequest(source_type="web", source="https://example.com/a"))
        orch._infos = [{"source_id": first_id, "type": "web", "url": "https://example.com/a"}]
        orch.calls.clear()

        failing, _ = _service(orch, fail=True)
        with pytest.raises(RuntimeError, match="upstream is down"):
            await failing.ingest_source(IngestRequest(source_type="web", source="https://example.com/a"))

        assert not any(c.startswith("delete_source") for c in orch.calls)

    @pytest.mark.asyncio
    async def test_a_legacy_uuid_source_is_adopted_rather_than_duplicated(self) -> None:
        # The upgrade repair path. An existing source carries a random uuid, so a
        # deterministic id would not match it; adopting keeps one source instead
        # of leaving a copy behind on the first re-ingest after the upgrade.
        legacy = {"source_id": "e9e7200a-legacy", "type": "web", "url": "https://example.com/a"}
        orch = _RecordingOrchestrator(existing=[legacy])
        service, _ = _service(orch)

        source_id, _, replaced = await service.ingest_source(
            IngestRequest(source_type="web", source="https://example.com/a")
        )

        assert source_id == "e9e7200a-legacy"
        assert replaced is True
        assert "delete_source:e9e7200a-legacy" in orch.calls

    @pytest.mark.asyncio
    async def test_a_different_url_is_not_adopted(self) -> None:
        orch = _RecordingOrchestrator(existing=[{"source_id": "other", "type": "web", "url": "https://example.com/b"}])
        service, _ = _service(orch)

        source_id, _, replaced = await service.ingest_source(
            IngestRequest(source_type="web", source="https://example.com/a")
        )

        assert source_id != "other"
        assert replaced is False


class TestIngestFileReplaces:
    @pytest.mark.asyncio
    async def test_re_uploading_identical_bytes_replaces(self) -> None:
        orch = _RecordingOrchestrator()
        service = IngestService(orch, {"pdf": _StubLoader(orch.calls)})

        first_id, _, _ = await service.ingest_file("pdf", b"%PDF-1.7 same", "report.pdf")
        orch._infos = [{"source_id": first_id, "type": "pdf", "url": ""}]
        orch.calls.clear()

        second_id, _, replaced = await service.ingest_file("pdf", b"%PDF-1.7 same", "renamed.pdf")

        assert second_id == first_id
        assert replaced is True
        assert f"delete_source:{first_id}" in orch.calls

    @pytest.mark.asyncio
    async def test_different_bytes_are_a_separate_source(self) -> None:
        # A genuinely revised document must not silently overwrite the original.
        orch = _RecordingOrchestrator()
        service = IngestService(orch, {"pdf": _StubLoader(orch.calls)})

        first_id, _, _ = await service.ingest_file("pdf", b"version one", "a.pdf")
        orch._infos = [{"source_id": first_id, "type": "pdf", "url": ""}]
        orch.calls.clear()

        second_id, _, replaced = await service.ingest_file("pdf", b"version two", "a.pdf")

        assert second_id != first_id
        assert replaced is False
        assert not any(c.startswith("delete_source") for c in orch.calls)
