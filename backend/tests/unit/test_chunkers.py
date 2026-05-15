import pytest

from core.chunking.code_chunker import CodeChunker
from core.chunking.text_chunker import TextChunker
from core.types import Document


def test_text_chunker_splits_with_overlap():
    chunker = TextChunker(chunk_size=3, chunk_overlap=1)
    doc = Document(document_id="doc-1", text="one two three four five six seven eight", metadata={})
    chunks = chunker.chunk_documents([doc])
    assert [chunk.text for chunk in chunks] == [
        "one two three",
        "three four five",
        "five six seven",
        "seven eight",
    ]


def test_code_chunker_extracts_python_symbols():
    code = """
class Example:
    def greet(self, name):
        return f"hi {name}"


def add(a, b):
    return a + b
"""
    doc = Document(document_id="repo:file.py", text=code, metadata={"path": "file.py"})
    chunker = CodeChunker()
    chunks = chunker.chunk_documents([doc])
    symbols = {chunk.metadata.get("symbol") for chunk in chunks}
    assert symbols == {"Example", "greet", "add"}
