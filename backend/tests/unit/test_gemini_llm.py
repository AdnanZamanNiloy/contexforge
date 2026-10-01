"""The Gemini provider must take its key from the Model Hub, and only there.

``GeminiLLM`` used to read ``settings.GOOGLE_API_KEY`` directly, so a Model Hub
row with no saved key still authenticated — against an environment credential
the UI never displayed. A user who deleted a key in the app, or added a model
without one, saw requests succeed and had no way to know which credential was
paying for them.
"""

from __future__ import annotations

import pytest

from core.generation.gemini_llm import GeminiLLM


def test_gemini_requires_a_key() -> None:
    """A missing key is a named failure, not a silent borrow."""
    with pytest.raises(ValueError, match="Model Hub"):
        GeminiLLM(model="gemini-flash-latest")


def test_gemini_accepts_a_hub_key() -> None:
    llm = GeminiLLM(model="gemini-flash-latest", api_key="hub-supplied-key")

    assert llm._model == "gemini-flash-latest"


def test_gemini_error_names_where_to_fix_it() -> None:
    """The message has to tell the user where the key belongs, not just that it is absent."""
    with pytest.raises(ValueError) as excinfo:
        GeminiLLM()

    message = str(excinfo.value)
    assert "Google API key" in message
    assert "Model Center" in message
