"""Security & Quality scan.

The rules are the correctness boundary here, because the failure mode that
matters is a scanner that cries wolf: a report full of placeholders and
docstring examples gets muted, and then the one real leaked key goes unread too.
So a large share of these tests are about what the scan must *not* report.
"""

from __future__ import annotations

import json

import pytest

from app.security.code import (
    _looks_like_test,
    _prose_lines,
    _redact,
    ast_grep_binary,
    scan_code,
)
from app.security.cves import clean_version, fixed_of, severity_of
from app.security.models import severity_rank, worst
from app.security.rules import CODE_RULES, SECRET_PATTERNS, TEXT_RULES, language_of
from app.security.service import SecurityError, SecurityService, quality_gates
from app.security.storage import SecurityStore

requires_engine = pytest.mark.skipif(
    ast_grep_binary() is None, reason="ast-grep is not installed; the pattern scan cannot run"
)


# --------------------------------------------------------------------------- #
# Rule table sanity
# --------------------------------------------------------------------------- #


def test_every_rule_is_uniquely_identified():
    # Ids key the report and the de-duplication, so a collision would merge two
    # unrelated rules into one row.
    ids = [rule.id for rule in CODE_RULES] + [rule.id for rule in TEXT_RULES] + [r.id for r in SECRET_PATTERNS]
    assert len(ids) == len(set(ids))


def test_every_rule_declares_a_known_severity_and_category():
    from app.security.models import CODE_CATEGORIES, SEVERITIES

    categories = set(CODE_CATEGORIES) | {"Vulnerable dependency"}
    for rule in (*CODE_RULES, *TEXT_RULES, *SECRET_PATTERNS):
        assert rule.severity in SEVERITIES, rule.id
        assert rule.category in categories, rule.id


def test_every_code_rule_names_a_language_ast_grep_knows():
    known = {"python", "javascript", "typescript", "go", "java", "ruby", "php", "rust", "c", "cpp"}
    for rule in CODE_RULES:
        assert set(rule.languages) <= known, rule.id
        assert rule.languages, rule.id


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("app/main.py", "python"),
        ("src/index.tsx", "javascript"),
        ("main.go", "go"),
        ("Api.java", "java"),
        ("README.md", None),
        ("styles.css", None),
        ("data.json", None),
    ],
)
def test_language_detection_per_extension(path, expected):
    assert language_of(path) == expected


# --------------------------------------------------------------------------- #
# Code patterns
# --------------------------------------------------------------------------- #


@requires_engine
@pytest.mark.asyncio
async def test_finds_a_real_call_but_not_the_same_word_in_prose():
    # The whole reason this is ast-grep and not a regex: the comment and the
    # string are not code, and reporting them would be the first reason to stop
    # reading the report.
    result = await scan_code(
        {"app/run.py": ('# never call eval on user input\nEXAMPLE = "eval(x)"\ndef run(cmd):\n    return eval(cmd)\n')}
    )
    locations = [(f.location, f.line) for f in result.findings if f.id == "dynamic-eval"]
    assert locations == [("app/run.py", 4)]


@requires_engine
@pytest.mark.asyncio
async def test_finds_the_patterns_it_should_across_languages():
    result = await scan_code(
        {
            "app/a.py": "import os\nos.system(cmd)\n",
            "app/b.js": "eval(x);\nnew Function(y);\nchild_process.exec(z);\n",
        }
    )
    found = {f.id for f in result.findings}
    assert {"python-os-system", "dynamic-eval", "js-function-constructor", "node-child-process-exec"} <= found


@requires_engine
@pytest.mark.asyncio
async def test_does_not_flag_a_strong_hash_as_weak():
    # `hashlib.$HASH(...)` matches sha256 as readily as md5, and calling sha256 a
    # weak hash would be simply wrong.
    result = await scan_code({"app/h.py": "import hashlib\na = hashlib.sha256(b'x')\nb = hashlib.md5(b'x')\n"})
    weak = [f for f in result.findings if f.id == "python-weak-hash"]
    assert [f.line for f in weak] == [3]


@requires_engine
@pytest.mark.asyncio
async def test_does_not_flag_a_test_file_asserting_a_disabled_check():
    result = await scan_code(
        {
            "tests/test_net.py": "def test_it():\n    requests.get(url, verify=False)\n",
            "app/net.py": "requests.get(url, verify=False)\n",
        }
    )
    assert [f.location for f in result.findings] == ["app/net.py"]


def test_test_path_detection():
    assert _looks_like_test("tests/test_thing.py")
    assert _looks_like_test("src/foo.test.ts")
    assert _looks_like_test("app/thing_spec.rb")
    assert not _looks_like_test("app/latest_thing.py")


# --------------------------------------------------------------------------- #
# Prose: docstrings and comments are not code
# --------------------------------------------------------------------------- #


def test_prose_lines_cover_docstrings_and_comments():
    source = '"""Doc.\n\n    DEBUG = True\n"""\n# DEBUG = True\nDEBUG = True\n'
    prose = _prose_lines(source, "settings.py")
    assert {1, 2, 3} <= prose  # the docstring
    assert 5 in prose  # the comment
    assert 6 not in prose  # the real assignment


def test_prose_lines_are_computed_only_for_python():
    # Guessing where another language's docstrings are would be worse than not
    # trying, so the filter is Python-only and other languages rely on confidence.
    assert _prose_lines("DEBUG = True\n", "config.js") == set()


def test_prose_lines_survive_an_unparseable_file():
    assert _prose_lines("def (:\n", "broken.py") == set()


@pytest.mark.asyncio
async def test_ignores_a_documented_example_but_reports_the_real_setting():
    # Flask's own config.py documents `DEBUG = True` in its module docstring.
    # Reporting that tells the reader nothing they could not read for themselves.
    source = (
        '"""Config.\n\nExample::\n\n    DEBUG = True\n    SECRET_KEY = "development key"\n"""\n'
        "# DEBUG = True\n"
        "DEBUG = True\n"
    )
    result = await scan_code({"settings.py": source})
    assert [f.line for f in result.findings] == [9]


# --------------------------------------------------------------------------- #
# Secrets
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_finds_a_credential_and_never_echoes_it():
    token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    result = await scan_code({"app/config.py": f'TOKEN = "{token}"\n'})
    finding = next(f for f in result.findings if f.id == "github-token")
    assert finding.source == "secret"
    # A report that quotes the credential has copied it somewhere new.
    assert token not in json.dumps(finding.to_dict())
    assert token[:4] in finding.snippet and "*" in finding.snippet


@pytest.mark.asyncio
async def test_does_not_report_an_example_key():
    result = await scan_code({"app/config.py": 'AWS = "AKIAIOSFODNN7EXAMPLE"\n'})
    assert not [f for f in result.findings if f.id == "aws-access-key"]


@pytest.mark.asyncio
async def test_does_not_report_a_name_used_as_a_value():
    # `app.secret_key = "secret_key"` and `password = "development"` are the two
    # most common false "leaks" in any codebase; neither is a generated value.
    result = await scan_code(
        {"app/a.py": 'app.secret_key = "secret_key"\npassword = "development"\napi_key = "changeme"\n'}
    )
    assert not [f for f in result.findings if f.source == "secret"]


@pytest.mark.asyncio
async def test_still_reports_a_real_secret_among_placeholders():
    result = await scan_code({"app/a.py": 'password = "changeme"\ntoken = "Xy7!kQ2mNp9vL4wR8"\n'})
    secrets = [f for f in result.findings if f.source == "secret"]
    assert len(secrets) == 1


@pytest.mark.asyncio
async def test_redaction_hides_short_values_entirely():
    assert _redact("short") == "*****"
    assert _redact("abcdefghijkl").startswith("abcd")


@pytest.mark.asyncio
async def test_a_secret_in_a_docstring_is_an_example():
    source = '"""Example::\n\n    token = "Xy7!kQ2mNp9vL4wR8"\n"""\n'
    result = await scan_code({"app/a.py": source})
    assert not [f for f in result.findings if f.source == "secret"]


# --------------------------------------------------------------------------- #
# Text rules
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_reports_a_disabled_check_in_real_code():
    result = await scan_code({"app/net.py": "requests.get(url, verify=False)\n"})
    assert [f.id for f in result.findings] == ["tls-verify-disabled"]


# --------------------------------------------------------------------------- #
# Coverage and honest degradation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_reports_an_unavailable_engine_rather_than_a_clean_result(monkeypatch):
    # The single most damaging way this feature could fail: an absent scanner
    # and an absent problem look identical on screen.
    monkeypatch.setattr("app.security.code.ast_grep_binary", lambda: None)
    result = await scan_code({"app/a.py": "eval(x)\n"})
    assert result.engine == "unavailable"
    assert result.files_scanned == 0
    assert "ast-grep is not installed" in result.error

    # Secrets are still scanned: a leaked key should not depend on an optional
    # binary being installed.
    with_secret = await scan_code({"app/b.py": 'token = "Xy7!kQ2mNp9vL4wR8"\n'})
    assert [f.source for f in with_secret.findings] == ["secret"]


@pytest.mark.asyncio
async def test_reports_a_failed_rule_as_incomplete(monkeypatch):
    async def boom(*args, **kwargs):
        return [], ["dynamic-eval"]

    monkeypatch.setattr("app.security.code._run_engine", boom)
    result = await scan_code({"app/a.py": "eval(x)\n"})
    assert "could not run" in result.error


@pytest.mark.asyncio
async def test_counts_the_files_it_actually_read():
    result = await scan_code(
        {
            "app/a.py": "eval(x)\n",
            "app/b.js": "eval(y);\n",
            "docs/readme.md": "eval(z)\n",
            "node_modules/pkg/index.js": "eval(w);\n",
        }
    )
    # Markdown is not source, and a vendored tree is not the repository's code.
    assert result.files_available == 2
    assert sorted(result.languages) == ["javascript", "python"]


# --------------------------------------------------------------------------- #
# Dependency advisories
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.2.3", "1.2.3"),
        ("^1.2.3", "1.2.3"),
        ("~2.0", "2.0"),
        (">=3.1.0,<4.0.0", "3.1.0"),
        ("v1.2.3", "1.2.3"),
        ("1.2.3-rc1", "1.2.3-rc1"),
        ("latest", None),
        ("*", None),
        ("", None),
        (None, None),
        # A range passed on verbatim would match nothing at OSV and report a
        # clean dependency, which is worse than not asking at all.
        ("git+https://example.com/x.git", None),
        ("workspace:*", None),
    ],
)
def test_version_normalisation(raw, expected):
    assert clean_version(raw) == expected


def test_severity_prefers_the_reviewed_label():
    assert severity_of({"database_specific": {"severity": "CRITICAL"}}) == "critical"
    assert severity_of({"database_specific": {"severity": "MODERATE"}}) == "medium"


def test_severity_falls_back_to_the_cvss_vector():
    assert severity_of({"severity": [{"score": "CVSS:3.1/AV:N/AC:L/C:H/I:N/A:N"}]}) == "high"
    assert severity_of({"severity": [{"score": "CVSS:4.0/AV:L/AC:L/VC:L/VI:L/VA:N"}]}) == "medium"


def test_severity_stays_unknown_when_it_cannot_be_read():
    # An advisory that cannot be rated is not evidence of a problem, and not
    # evidence of safety either.
    assert severity_of({}) == "unknown"
    assert severity_of({"database_specific": {"severity": "WEIRD"}}) == "unknown"


def test_earliest_fixed_version_is_reported():
    record = {
        "affected": [
            {"ranges": [{"events": [{"introduced": "0"}, {"fixed": "12.3.0"}]}]},
            {"ranges": [{"events": [{"introduced": "0"}, {"fixed": "11.0.0"}]}]},
        ]
    }
    assert fixed_of(record) == "11.0.0"


def test_finding_ordering_and_ranking():
    assert worst(["low", "high", "medium"]) == "high"
    assert worst([]) == "unknown"
    assert severity_rank("critical") < severity_rank("high") < severity_rank("unknown")


# --------------------------------------------------------------------------- #
# Quality gates
# --------------------------------------------------------------------------- #


def test_gates_report_a_bare_repository_honestly():
    gates = {g["id"]: g for g in quality_gates(["README.md", "app.py"], ["app.py"])}
    assert gates["ci"]["state"] == "warn"
    assert gates["lockfile"]["state"] == "warn"
    assert gates["licence"]["state"] == "info"


def test_gates_recognise_ci_a_lockfile_and_a_licence():
    gates = {
        g["id"]: g
        for g in quality_gates(
            [".github/workflows/ci.yml", "poetry.lock", "LICENSE", "tests/test_a.py"], ["tests/test_a.py"]
        )
    }
    assert all(gates[key]["state"] == "ok" for key in ("ci", "lockfile", "licence", "tests"))


def test_a_gate_is_an_observation_not_a_finding():
    # Quality gates are facts about a project, not defects someone introduced,
    # so they are never counted as findings or given a severity.
    for gate in quality_gates(["README.md"], []):
        assert "severity" not in gate
        assert gate["state"] in ("ok", "warn", "info")


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #


class _Chunk:
    def __init__(self, text: str, path: str, symbol: str = "") -> None:
        self.text = text
        self.metadata = {"path": path, "symbol": symbol, "repo": "acme/widgets"}


def _service(tmp_path) -> SecurityService:
    return SecurityService(store=SecurityStore(db_path=tmp_path / "security.db"), faiss=object())


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_scan_reports_its_own_blind_spot(tmp_path, monkeypatch):
    # A scanner that does not mention what it cannot see gets trusted for the
    # cases it cannot see.
    chunks = [_Chunk("import os\nos.system(cmd)\n", "app/run.py")]

    class _Faiss:
        async def get_chunks_by_source_id(self, source_id):
            return chunks

    service = SecurityService(store=SecurityStore(db_path=tmp_path / "s.db"), faiss=_Faiss())

    async def no_advisories(deps, cache=None):
        from app.security.cves import AdvisoryResult

        return AdvisoryResult(outcomes=[], checked=0, vulnerable=0, unchecked=0)

    monkeypatch.setattr("app.security.service.check_dependencies", no_advisories)
    result = await service.scan("p1", "repo:acme/widgets", refresh=True)
    assert result["limitations"], "a scan must state its limitations"
    assert any("helper in another file" in note for note in result["limitations"])
    assert result["code"]["finding_count"] >= 1


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_scan_serves_a_cached_result(tmp_path):
    from app.security.cves import AdvisoryResult

    class _Faiss:
        async def get_chunks_by_source_id(self, source_id):
            return [_Chunk("x = 1\n", "app/a.py")]

    service = SecurityService(store=SecurityStore(db_path=tmp_path / "s.db"), faiss=_Faiss())

    async def no_advisories(deps, cache=None):
        return AdvisoryResult(outcomes=[], checked=0, vulnerable=0, unchecked=0)

    import app.security.service as module

    original = module.check_dependencies
    module.check_dependencies = no_advisories
    try:
        first = await service.scan("p1", "repo:acme/widgets", refresh=True)
        second = await service.scan("p1", "repo:acme/widgets")
    finally:
        module.check_dependencies = original
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["fingerprint"] == first["fingerprint"]


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_scan_without_indexed_files_raises(tmp_path):
    class _Faiss:
        async def get_chunks_by_source_id(self, source_id):
            return []

    service = SecurityService(store=SecurityStore(db_path=tmp_path / "s.db"), faiss=_Faiss())
    with pytest.raises(SecurityError, match="no indexed files"):
        await service.scan("p1", "repo:acme/widgets")


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_get_returns_none_before_a_scan(tmp_path):
    assert await _service(tmp_path).get("unknown") is None
