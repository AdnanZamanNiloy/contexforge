from __future__ import annotations

import ast
from typing import List

from core.chunking.text_chunker import TextChunker
from core.types import Chunk, Document
from observability.tracer import observe


class CodeChunker:
    def __init__(self) -> None:
        self._fallback = TextChunker()

    @observe(name="chunk_code")
    def chunk_documents(self, documents: List[Document]) -> List[Chunk]:
        chunks: List[Chunk] = []
        for doc in documents:
            path = str(doc.metadata.get("path", ""))
            if path.endswith(".py"):
                chunks.extend(self._chunk_python(doc))
            else:
                chunks.extend(self._fallback.chunk_documents([doc]))
        return chunks

    def _chunk_python(self, doc: Document) -> List[Chunk]:
        try:
            tree = ast.parse(doc.text)
        except SyntaxError:
            return self._fallback.chunk_documents([doc])

        chunks: List[Chunk] = []
        index = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                segment = ast.get_source_segment(doc.text, node)
                if not segment:
                    continue
                name = getattr(node, "name", "")
                metadata = {**doc.metadata, "symbol": name}
                chunk_id = f"{doc.document_id}:{index}"
                chunks.append(Chunk(chunk_id=chunk_id, text=segment, metadata=metadata, source_id=doc.document_id))
                index += 1

        if not chunks:
            return self._fallback.chunk_documents([doc])
        return chunks
