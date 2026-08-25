"""Unit tests for the git analysis layer."""
from __future__ import annotations

import pytest

from app.repository_intelligence.git import GitRepository, parse_repo_id


class TestParseRepoId:
    def test_url(self):
        assert parse_repo_id("https://github.com/owner/repo") == ("owner", "repo")

    def test_short_form(self):
        assert parse_repo_id("owner/name.git") == ("owner", "name")

    def test_invalid(self):
        with pytest.raises(Exception):
            parse_repo_id("not a repo")


class TestGitRepository:
    @pytest.mark.asyncio
    async def test_local_repo_derives_owner(self, single_commit_repo):
        git = GitRepository(str(single_commit_repo))
        assert git.owner == "local"
        assert git.name == "single"

    @pytest.mark.asyncio
    async def test_head_and_meta(self, git_repo):
        meta = await git_repo.repository_meta()
        head = await git_repo.head_commit()
        assert meta["sha"] == head
        assert meta["author"] == "daniel-w"

    @pytest.mark.asyncio
    async def test_commits_and_contributors(self, single_commit_repo):
        git = GitRepository(str(single_commit_repo))
        commits = await git.commits()
        assert len(commits) == 1
        contribs = await git.contributors()
        assert any(c["name"] == "daniel-w" for c in contribs)

    @pytest.mark.asyncio
    async def test_file_churn_counts(self, single_commit_repo):
        git = GitRepository(str(single_commit_repo))
        churn = await git.file_churn()
        assert any(c["name"] == "core/foo.py" and c["value"] == 1 for c in churn)

    @pytest.mark.asyncio
    async def test_ownership_shape(self, single_commit_repo):
        git = GitRepository(str(single_commit_repo))
        ow = await git.ownership()
        assert ow["authors"]
        assert ow["files"].get("core/foo.py")

    def test_close_keeps_local_dir(self, sample_repo):
        git = GitRepository(str(sample_repo))
        git.close()
        assert sample_repo.exists()
