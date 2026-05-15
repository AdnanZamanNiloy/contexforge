from __future__ import annotations

import asyncio
import logging
import re
from typing import List

import httpx

from app.config.settings import settings
from .base_loader import BaseLoader
from core.types import Document
from observability.tracer import observe


logger = logging.getLogger(__name__)


class GitHubLoader(BaseLoader):
    @observe(name="load_github")
    async def load(self, source: str | bytes, source_id: str) -> List[Document]:
        if not isinstance(source, str):
            raise ValueError("GitHubLoader expects a repo URL string")
        owner, repo = self._parse_repo(source)
        async with httpx.AsyncClient(timeout=30.0) as client:
            repo_data = await self._fetch_repo(client, owner, repo)
            branch = repo_data.get("default_branch", "main")
            tree = await self._fetch_tree(client, owner, repo, branch)
            file_paths = self._filter_paths(tree)
            documents: List[Document] = []
            for path in file_paths[: settings.MAX_GITHUB_FILES]:
                content = await self._fetch_raw(client, owner, repo, branch, path)
                if self._is_binary_content(content):
                    continue
                text = content.decode("utf-8", errors="ignore")
                metadata = {"path": path, "repo": f"{owner}/{repo}", "source_id": source_id}
                doc_id = f"{source_id}:{path}"
                documents.append(Document(document_id=doc_id, text=text, metadata=metadata, source_type="github"))
            return documents

    async def _fetch_repo(self, client: httpx.AsyncClient, owner: str, repo: str) -> dict:
        response = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
        response.raise_for_status()
        return response.json()

    async def _fetch_tree(
        self, client: httpx.AsyncClient, owner: str, repo: str, branch: str
    ) -> List[dict]:
        response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("tree", [])

    async def _fetch_raw(
        self, client: httpx.AsyncClient, owner: str, repo: str, branch: str, path: str
    ) -> bytes:
        response = await client.get(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}")
        response.raise_for_status()
        return response.content

    def _filter_paths(self, tree: List[dict]) -> List[str]:
        files: List[str] = []
        for node in tree:
            if node.get("type") != "blob":
                continue
            path = node.get("path", "")
            if self._is_lock_file(path) or self._is_binary_extension(path):
                continue
            files.append(path)
        return files

    @staticmethod
    def _parse_repo(url: str) -> tuple[str, str]:
        match = re.match(r"https?://github.com/([^/]+)/([^/]+)", url)
        if not match:
            raise ValueError("Invalid GitHub repository URL")
        return match.group(1), match.group(2).replace(".git", "")

    @staticmethod
    def _is_lock_file(path: str) -> bool:
        lock_files = {
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            "poetry.lock",
            "Pipfile.lock",
            "Gemfile.lock",
        }
        return path.split("/")[-1] in lock_files

    @staticmethod
    def _is_binary_extension(path: str) -> bool:
        binary_exts = {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".pdf",
            ".zip",
            ".exe",
            ".bin",
            ".so",
            ".dylib",
            ".dll",
            ".mp3",
            ".mp4",
            ".mov",
        }
        return any(path.lower().endswith(ext) for ext in binary_exts)

    @staticmethod
    def _is_binary_content(content: bytes) -> bool:
        return b"\x00" in content
