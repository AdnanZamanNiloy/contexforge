from pathlib import Path

import pytest

from core.embedding.voyage_embedder import VoyageEmbedder


@pytest.mark.asyncio
async def test_voyage_embedder_uses_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    embedder = VoyageEmbedder(cache_path=cache_path, api_key="test-key")
    calls = {"count": 0}

    async def fake_embed_batch(texts, input_type):
        calls["count"] += 1
        return [[float(len(texts[0]))]]

    embedder._embed_batch = fake_embed_batch  # type: ignore[assignment]

    vectors_1 = await embedder.embed_texts(["hello"], input_type="document")
    vectors_2 = await embedder.embed_texts(["hello"], input_type="document")

    assert vectors_1 == vectors_2
    assert calls["count"] == 1
    assert cache_path.exists()


def test_voyage_embedder_requires_a_key() -> None:
    """A missing key must fail by name, not borrow one from the environment.

    The key used to fall back to `VOYAGE_API_KEY`, so a Model Hub row with no
    saved key still worked — against a credential the UI never showed, which
    made a misconfigured install look correctly configured.
    """
    with pytest.raises(ValueError, match="Model Hub"):
        VoyageEmbedder()
