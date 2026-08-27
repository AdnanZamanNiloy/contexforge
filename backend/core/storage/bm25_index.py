from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
from pathlib import Path

from app.config.settings import settings
from core.types import Chunk, RetrievedChunk
from observability.tracer import observe

__all__ = ["BM25Index"]

logger = logging.getLogger(__name__)

_FTS5_SPECIAL = re.compile(r"[^\w\s]+")


def _safe_unlink_db(path: str) -> None:
    """Best-effort file removal for SQLite DB files."""
    import os

    try:
        os.unlink(path)
    except OSError:
        pass


def _sanitise_query(query: str) -> str:
    # FTS5 MATCH treats punctuation as query operators.  Strip everything that
    # is not a word character or whitespace so natural-language questions
    # (which routinely contain '?', '!', '.', commas, etc.) don't raise
    # "fts5: syntax error near ...".
    sanitised = _FTS5_SPECIAL.sub(" ", query)
    return re.sub(r"\s{2,}", " ", sanitised).strip()


class BM25Index:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path: Path = Path(db_path or settings.BM25_DB_PATH)
        self._conn: sqlite3.Connection | None = None
        self._init_lock = asyncio.Lock()
        self._initialized = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @observe(name="bm25_add")
    async def add(self, chunks: list[Chunk]) -> None:
        if not isinstance(chunks, list) or not chunks:
            logger.debug("bm25_add called with empty chunk list — nothing to do.")
            return

        await self._ensure_initialized()
        await asyncio.to_thread(self._add_sync, chunks)

    @observe(name="bm25_search")
    async def search(self, query: str, top_k: int, exclude_source_ids: set[str] | None = None) -> list[RetrievedChunk]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("BM25Index.search received an empty query")
        if top_k <= 0:
            raise ValueError(f"top_k must be a positive integer, got {top_k}")

        await self._ensure_initialized()
        return await asyncio.to_thread(self._search_sync, query, top_k, exclude_source_ids)

    @observe(name="bm25_delete_by_source")
    async def delete_by_source_id(self, source_id: str) -> int:
        """Delete all chunks belonging to *source_id* from the FTS5 index.

        Holds the init lock for the entire delete-reload cycle to prevent
        concurrent searches from reading stale state.

        Returns:
            Number of chunks deleted.
        """
        if not source_id:
            raise ValueError("source_id must not be empty")

        async with self._init_lock:
            if not self._initialized:
                await asyncio.to_thread(self._init_sync)
                self._initialized = True

            count = await asyncio.to_thread(self._delete_by_source_id_sync, source_id)

            # Force re-init so in-memory connection state is fresh
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self._conn = None
            self._initialized = False
            await asyncio.to_thread(self._init_sync)
            self._initialized = True

            # Verify deletion
            verify_count = await asyncio.to_thread(self._count_sync)
            logger.info(
                "delete_by_source_id: source_id=%s deleted=%d remaining=%d",
                source_id,
                count,
                verify_count,
            )
            return count

    async def force_reload(self) -> None:
        """Close and discard the current connection so the next operation
        re-opens the database from scratch.

        Call this after an external modification to guarantee the singleton
        reflects the on-disk truth.
        """
        async with self._init_lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self._conn = None
            self._initialized = False
            logger.info("BM25Index: force_reload — connection discarded.")

    async def clear_all(self) -> int:
        """Delete every chunk from the store.

        Returns:
            Number of chunks that were removed.
        """
        await self._ensure_initialized()
        return await asyncio.to_thread(self._clear_all_sync)

    async def count(self) -> int:
        """Return the total number of chunks in the index."""
        await self._ensure_initialized()
        return await asyncio.to_thread(self._count_sync)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("BM25Index SQLite connection closed.")

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _init_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)

        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA mmap_size=134217728")  # 128 MB

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

    def _delete_by_source_id_sync(self, source_id: str) -> int:
        """Synchronous DELETE + VACUUM against SQLite FTS5."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM chunks WHERE source_id = ?", (source_id,))
        count = cursor.fetchone()[0]

        if count == 0:
            logger.info("delete_by_source_id: no chunks found for source_id=%s.", source_id)
            return 0

        with self._conn:
            self._conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
        # VACUUM must run outside the transaction; SQLite rejects it from
        # within a transaction ("cannot VACUUM from within a transaction").
        self._conn.execute("VACUUM")

        logger.info(
            "delete_by_source_id: deleted %d chunk(s) for source_id=%s, VACUUM complete.",
            count,
            source_id,
        )
        return count

    def _clear_all_sync(self) -> int:
        """Drop the FTS5 table, recreate it, and delete the DB file."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM chunks")
        count = cursor.fetchone()[0]

        # Drop and recreate the FTS5 table for a guaranteed clean state
        with self._conn:
            self._conn.execute("DROP TABLE IF EXISTS chunks")
            self._conn.execute(
                """
                CREATE VIRTUAL TABLE chunks
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

        # Also delete the DB file so nothing persists across restarts
        self.close()

        # `close()` nulls the connection but leaves _initialized=True;
        # clear the flag so the next operation re-initialises a fresh DB instead
        # of crashing on a None connection.
        self._initialized = False

        _safe_unlink_db(str(self._db_path))
        _safe_unlink_db(str(self._db_path) + "-wal")
        _safe_unlink_db(str(self._db_path) + "-shm")

        logger.info("clear_all: dropped and recreated chunks table, deleted DB files. Was %d rows.", count)
        return count

    def _count_sync(self) -> int:
        cursor = self._conn.execute("SELECT COUNT(*) FROM chunks")
        return cursor.fetchone()[0]

    def _add_sync(self, chunks: list[Chunk]) -> None:
        rows = [
            (
                chunk.chunk_id,
                chunk.text,
                json.dumps(dict(chunk.metadata), separators=(",", ":")),
                chunk.source_id or "",
            )
            for chunk in chunks
        ]

        with self._conn:
            existing_ids = {
                row[0]
                for row in self._conn.execute(
                    f"SELECT chunk_id FROM chunks WHERE chunk_id IN ({','.join('?' * len(rows))})",
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

    def _search_sync(self, query: str, top_k: int, exclude_source_ids: set[str] | None = None) -> list[RetrievedChunk]:
        safe_query = _sanitise_query(query)
        if not safe_query:
            logger.warning("BM25 query '%s' reduced to empty string after sanitisation — returning no results.", query)
            return []

        cursor = self._conn.execute(
            """
            SELECT chunk_id, text, metadata, source_id, bm25(chunks) AS score
            FROM chunks
            WHERE chunks MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (safe_query, top_k),
        )

        results: list[RetrievedChunk] = []
        for chunk_id, text, metadata_raw, source_id, score in cursor.fetchall():
            # Scoped retrieval: drop chunks from sources we are told to exclude.
            if exclude_source_ids and source_id and source_id in exclude_source_ids:
                continue
            try:
                metadata = json.loads(metadata_raw) if metadata_raw else {}
            except json.JSONDecodeError:
                logger.warning("Corrupt metadata for chunk '%s' — using empty dict.", chunk_id)
                metadata = {}

            chunk = Chunk(
                chunk_id=chunk_id,
                text=text,
                metadata=metadata,
                source_id=source_id or None,
            )
            results.append(RetrievedChunk(chunk=chunk, score=float(-score)))

        logger.debug("BM25 search for '%s' returned %d result(s).", query, len(results))
        return results

    async def _ensure_initialized(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._init_sync)
            self._initialized = True
