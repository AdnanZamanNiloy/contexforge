import pytest

from core.retrieval.hyde import HydeQueryExpander


class FakeLLM:
    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        return "expanded"

    async def stream(self, prompt: str, system_prompt: str | None = None):
        yield "expanded"


@pytest.mark.asyncio
async def test_hyde_expander_uses_llm():
    expander = HydeQueryExpander(FakeLLM())
    result = await expander.expand("question")
    assert result == "expanded"
