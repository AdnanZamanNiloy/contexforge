from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import List

from app.config.settings import settings
from core.types import Chunk, RetrievedChunk
from observability.tracer import observe

__all__ = ["BM25Index"]

logger = logging.getLogger(__name__)

_FTS5_SPECIAL = re.compile(r'["\'\(\)\*\:\^]')


def _sanitise_query(query: str) -> str:

    sanitised = _FTS5_SPECIAL.sub(" ", query)
    return re.sub(r"\s{2,}", " ", sanitised).strip()


class BM25Index:
  
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path: Path = Path(db_path or settings.BM25_DB_PATH)
        self._conn: sqlite3.Connection | None = None
        self._init_lock = asyncio.Lock()
        self._initialized = False

   

    @observe(name="bm25_add")
    async def add(self, chunks: List[Chunk]) -> None:

        if not isinstance(chunks, list) or not chunks:
            logger.debug("bm25_add called with empty chunk list — nothing to do.")
            return

        await self._ensure_initialized()
        await asyncio.to_thread(self._add_sync, chunks)

    @observe(name="bm25_search")
    async def search(self, query: str, top_k: int) -> List[RetrievedChunk]:
       
        if not isinstance(query, str) or not query.strip():
            raise ValueError("BM25Index.search received an empty query")
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")

        await self._ensure_initialized()
        return await asyncio.to_thread(self._search_sync, query, top_k)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("BM25Index SQLite connection closed.")

    

    def _init_sync(self) -> None:
        
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)

        #  WAL mode: readers don't block writers, commits are faster
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL") 
        self._conn.execute("PRAGMA mmap_size=134217728")  # 128 MB memory map

        self._conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks
            USING fts5(
                chunk_id UNINDEXED,
                text,
                metadata UNINDEXED,
                source_id UNINDEXED,
                tokenize='porter unicode61'
            )
            """
        )
        self._conn.commit()
        logger.debug("BM25Index initialised at %s (WAL mode).", self._db_path)


    def _add_sync(self, chunks: List[Chunk]) -> None:
        
        rows = [
            (
                chunk.chunk_id,
                chunk.text,
                json.dumps(chunk.metadata, separators=(",", ":")),
                chunk.source_id or "",
            )
            for chunk in chunks
        ]

        with self._conn: 
            existing_ids = {
                row[0]
                for row in self._conn.execute(
                    f"SELECT chunk_id FROM chunks WHERE chunk_id IN "
                    f"({','.join('?' * len(rows))})",
                    [r[0] for r in rows],
                ).fetchall()
            }
            new_rows = [r for r in rows if r[0] not in existing_ids]
            if not new_rows:
                logger.debug("All %d chunk(s) already indexed — skipped.", len(rows))
                return
            self._conn.executemany(
                "INSERT INTO chunks (chunk_id, text, metadata, source_id) VALUES (?, ?, ?, ?)",
                new_rows,
            )
        logger.debug(
            "BM25Index: inserted %d new chunk(s), skipped %d duplicate(s).",
            len(new_rows),
            len(rows) - len(new_rows),
        )



    def _search_sync(self, query: str, top_k: int) -> List[RetrievedChunk]:
        safe_query = _sanitise_query(query)
        if not safe_query:
            logger.warning(
                "BM25 query '%s' reduced to empty string after sanitisation — "
                "returning no results.", query
            )
            return []

        cursor = self._conn.execute(
            """
            SELECT chunk_id, text, metadata, source_id, bm25(chunks) AS score
            FROM chunks
            WHERE chunks MATCH ?
            ORDER BY score          -- bm25() is negative; lower = better match
            LIMIT ?
            """,
            (safe_query, top_k),
        )

        results: List[RetrievedChunk] = []
        for chunk_id, text, metadata_raw, source_id, score in cursor.fetchall():
            try:
                metadata = json.loads(metadata_raw) if metadata_raw else {}
            except json.JSONDecodeError:
                logger.warning(
                    "Corrupt metadata for chunk '%s' — using empty dict.", chunk_id
                )
                metadata = {}

            chunk = Chunk(
                chunk_id=chunk_id,
                text=text,
                metadata=metadata,
                source_id=source_id or None,
            )
            results.append(RetrievedChunk(chunk=chunk, score=float(-score)))

        logger.debug(
            "BM25 search for '%s' returned %d result(s).", query, len(results)
        )
        return results

 
    async def _ensure_initialized(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._init_sync)
            self._initialized = True