"""Repository-grounded chat support for Repository Intelligence.

The ``/repository/{analysis_id}/ask`` endpoint answers questions about a single
GitHub repository.  Instead of searching the whole knowledge base (which may be
empty or contain unrelated sources), the repository is indexed on demand into
the RAG store under a deterministic ``source_id`` and the query is scoped to it.

Design rules:
  * ingestion is idempotent — a repository is only indexed once per source_id;
  * the repository is bounded-cloned with the same ``GitRepository`` used by
    analysis, so no repo code is ever executed;
  * chunks are tagged with repo-relative ``path`` so citations map to real files.
"""

from __future__ import annotations

import logging
from typing import Any

from core.types import Document

from .git import GitRepoError, GitRepository, parse_repo_id

__all__ = ["ensure_repo_indexed", "repo_source_id"]

logger = logging.getLogger(__name__)


def repo_source_id(full_name: str) -> str:
    """Return the deterministic source_id a repository is indexed under."""
    return f"repo:{full_name}"


async def ensure_repo_indexed(
    orchestrator: Any,
    repo_url: str,
    branch: str | None = None,
) -> str:
    """Index *repo_url* into the RAG store and return its source_id.

    If the repository is already indexed (its source_id is present in the FAISS
    store) this is a no-op.  Otherwise the repo is cloned, its source files are
    chunked with the code chunker, and the chunks are embedded + indexed.

    Args:
        orchestrator: The RAG pipeline (``core.orchestrator.Orchestrator``).
        repo_url:     GitHub repository URL.
        branch:       Branch to clone; repo default when ``None``.

    Returns:
        The deterministic ``source_id`` for the repository.
    """
    full_name = _full_name(repo_url)
    source_id = repo_source_id(full_name)

    if _is_indexed(orchestrator, source_id):
        logger.info("repo chat: %s already indexed (source_id=%s)", full_name, source_id)
        return source_id

    logger.info("repo chat: indexing %s into the RAG store (source_id=%s)", full_name, source_id)
    git = GitRepository(repo_url, branch)
    try:
        await git.clone()
        root = git.workdir
        # Local import to keep the analysis module decoupled from the graph builder.
        from .graph import discover_files

        documents: list[Document] = []
        for fp in discover_files(root):
            try:
                rel = str(fp.relative_to(root))
                text = fp.read_text(errors="ignore")
            except OSError:
                continue
            if not text.strip():
                continue
            metadata = {
                "path": rel,
                "repo": full_name,
                "branch": branch or "",
                "source_id": source_id,
                "url": repo_url,
            }
            documents.append(
                Document(
                    document_id=f"{source_id}:{rel}",
                    text=text,
                    metadata=metadata,
                    source_type="github",
                )
            )
        if documents:
            n_chunks = await orchestrator.ingest(documents, use_code_chunker=True)
            if _is_indexed(orchestrator, source_id):
                logger.info(
                    "repo chat: indexed %d chunk(s) from %d doc(s) for %s (source_id=%s)",
                    n_chunks,
                    len(documents),
                    full_name,
                    source_id,
                )
            else:
                logger.warning(
                    "repo chat: ingest returned %d chunk(s) but %s has no indexed chunks "
                    "(source_id=%s); embed/index step likely failed.",
                    n_chunks,
                    full_name,
                    source_id,
                )
        else:
            logger.warning("repo chat: no analysable source files for %s", full_name)
        return source_id
    finally:
        git.close()


def _full_name(repo_url: str) -> str:
    try:
        owner, name = parse_repo_id(repo_url)
    except GitRepoError:
        return repo_url.strip("/").replace("https://", "").replace("http://", "")
    return f"{owner}/{name}"


def _is_indexed(orchestrator: Any, source_id: str) -> bool:
    """Return True when *source_id* already has chunks in the RAG store."""
    try:
        return source_id in orchestrator._faiss.get_source_ids()
    except Exception:  # pragma: no cover - defensive
        return False
