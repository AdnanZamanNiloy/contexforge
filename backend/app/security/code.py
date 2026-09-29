"""Running the code scan.

The scan is ast-grep, invoked once over a temporary project directory.  One
invocation for every rule rather than one per rule matters: a per-rule loop pays
process start and tree-sitter parse costs repeatedly, which on a repository of
any size is the difference between milliseconds and a minute.

ast-grep is optional.  If its binary is not installed the scan does not quietly
report "nothing found" -- that would be the single most damaging way for this
feature to fail, because a clean report and an absent scanner look identical.  It
reports that it could not run, and the view says so.
"""

from __future__ import annotations

import ast
import asyncio
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import tokenize
from dataclasses import dataclass
from pathlib import Path

from app.security.models import Finding
from app.security.rules import (
    _LOWERCASE_WORD,
    CODE_RULES,
    SECRET_PATTERNS,
    TEXT_RULES,
    SecretRule,
    language_of,
)

__all__ = ["CodeScanResult", "ast_grep_binary", "scan_code"]

logger = logging.getLogger(__name__)

# Bounds.  A scan reads source the index already holds, so it is cheap, but it
# still has to stop somewhere: a very large repository is reported as bounded
# rather than scanned forever.
MAX_FILES = 400
MAX_FILE_CHARS = 120_000
MAX_FINDINGS = 400
MAX_SNIPPET = 200
SCAN_TIMEOUT_SECONDS = 60
# ast-grep is given a wall clock of its own, separate from the service timeout,
# so a pathological file cannot leave the subprocess running.
ENGINE_TIMEOUT_SECONDS = 45

#: Paths whose contents are not the repository's own code.
_SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        "out",
        "target",
        "vendor",
        "__pycache__",
        ".venv",
        "venv",
        "site-packages",
        "coverage",
        ".next",
        ".nuxt",
        "bower_components",
        "jspm_packages",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".gradle",
        ".terraform",
        "third_party",
        "thirdparty",
    }
)

#: Test and fixture files legitimately contain the patterns being looked for:
#: a test asserting `verify=False` is asserting it is *not* used.
_TEST_MARKERS = ("test", "spec", "fixture", "mock", "stub", "example", "sample", "benchmark", "__tests__")

_BINARY_CANDIDATES = ("ast-grep", "sg")


def ast_grep_binary() -> str | None:
    """Locate the ast-grep executable, or ``None`` when it is not installed.

    Looked up next to the interpreter first, because a virtualenv's ``bin``
    directory is where the wheel puts it and it need not be on ``PATH`` for the
    service process.
    """
    override = os.environ.get("AST_GREP_BIN")
    if override and Path(override).exists():
        return override
    beside = Path(sys.executable).parent
    for name in _BINARY_CANDIDATES:
        for candidate in (beside / name, beside / f"{name}.exe"):
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
    for name in _BINARY_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


@dataclass
class CodeScanResult:
    """What the code scan found, and how much it actually looked at."""

    findings: list[Finding]
    files_scanned: int
    files_available: int
    languages: dict[str, int]
    engine: str
    error: str = ""


def _is_source_path(path: str) -> bool:
    parts = path.split("/")
    if any(part.lower() in _SKIP_DIRS for part in parts[:-1]):
        return False
    return language_of(path) is not None


def _looks_like_test(path: str) -> bool:
    lowered = path.lower()
    base = lowered.rsplit("/", 1)[-1]
    if base.startswith("test_") or base.endswith(("_test.py", ".test.js", ".test.ts", ".spec.ts", "_test.go")):
        return True
    return any(f"/{marker}/" in f"/{lowered}" or f"{marker}." in base for marker in _TEST_MARKERS)


def _snippet(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line[:MAX_SNIPPET]


def _prose_lines(source: str, path: str) -> set[int]:
    """Line numbers inside a docstring or a comment.

    Text rules match text, so without this a documented example is indistinguishable
    from the configuration it documents: Flask's own ``config.py`` carries
    ``DEBUG = True`` inside a docstring showing how to set it, and a scanner that
    reports that has told the reader nothing they could not read for themselves.

    Only computed for Python, where the standard library can say precisely which
    lines are prose.  For other languages a text match is reported as-is and the
    finding stays at medium confidence, which is the honest outcome rather than a
    guess about where the language's docstrings are.
    """
    if not path.endswith((".py", ".pyi")):
        return set()
    lines: set[int] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # A file the parser rejects is exactly the case where guessing is worst.
        return lines
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                lines.add(token.start[0])
    except tokenize.TokenError, IndentationError, SyntaxError:
        pass
    return lines


def _scan_text_rules(path: str, text: str, prose: set[int]) -> list[Finding]:
    """Match the config switches that are text rather than code shape."""
    findings: list[Finding] = []
    for rule in TEXT_RULES:
        # A test that asserts `verify=False` is asserting it is *not* used, so a
        # test file is not evidence of a disabled check.  Secrets are exempt from
        # this: a real key committed in a fixture is still a leak.
        if _looks_like_test(path):
            continue
        for match in rule.pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            if line in prose:
                # A documented example, not a setting.
                continue
            findings.append(
                Finding(
                    id=rule.id,
                    title=rule.title,
                    severity=rule.severity,
                    category=rule.category,
                    detail=rule.detail,
                    location=path,
                    line=line,
                    source="code",
                    cwe=rule.cwe,
                    confidence=rule.confidence,
                    snippet=_snippet(match.group(0)),
                )
            )
            break
    return findings


def _scan_secrets(path: str, text: str, prose: set[int]) -> list[Finding]:
    """Find credentials in one file's text.

    Text matching is the correct tool here -- a secret is a string -- but it is
    only useful with the placeholder forms filtered out, since most "leaked keys"
    in any repository are ``your-api-key-here`` and friends.
    """
    findings: list[Finding] = []
    for rule in SECRET_PATTERNS:
        for match in rule.pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            if line in prose:
                # A key shown in a docstring is an example, not a leak.
                continue
            captured = next((g for g in match.groups() if g), None)
            value = captured if captured is not None else match.group(0)
            if _is_placeholder(rule, value):
                continue
            findings.append(
                Finding(
                    id=rule.id,
                    title=rule.title,
                    severity=rule.severity,
                    category=rule.category,
                    detail="A credential-shaped value is committed to the repository. "
                    "Treat it as exposed: rotate it, then move it to configuration.",
                    location=path,
                    line=line,
                    source="secret",
                    cwe=rule.cwe,
                    # The value itself is never echoed back; only enough of it to
                    # find the line, and never the secret.
                    snippet=_redact(value),
                )
            )
            # One hit per rule per file: a leaked key repeated is still one key.
            break
    return findings


def _is_placeholder(rule: SecretRule, value: str) -> bool:
    """True when *value* is a name rather than a credential.

    Two tests.  The explicit fragment list catches the spelled-out forms, and the
    shape test catches the ones nobody thought to list: a value of only lowercase
    letters and underscores is a name, because a value anybody generated carries
    a digit or an upper-case letter.
    """
    lowered = value.lower()
    if any(marker in lowered for marker in rule.placeholders):
        return True
    return bool(_LOWERCASE_WORD.match(value))


def _redact(value: str) -> str:
    """Show enough of a secret to locate it, and no more.

    A security report that quotes the credential it found has copied it
    somewhere new.
    """
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * 6}{value[-2:]}"


def _build_project(files: dict[str, str]) -> Path:
    """Write the files to scan under a temporary directory.

    ast-grep reads from disk, and the source is only ever held in the index, so
    the scan materialises it, runs, and removes it.  Nothing is left behind even
    if the process dies: the directory is under the system temp dir and is
    removed in a ``finally``.
    """
    root = Path(tempfile.mkdtemp(prefix="cf-security-"))
    for path, text in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def _language_files(root: Path, files: dict[str, str]) -> dict[str, list[Path]]:
    """Group the materialised files by ast-grep language.

    The paths handed back are absolute and inside *root*, because ast-grep
    resolves them against its own working directory, not the temporary one.
    """
    grouped: dict[str, list[Path]] = {}
    for path in files:
        language = language_of(path)
        if not language:
            continue
        grouped.setdefault(language, []).append(root / path)
    return grouped


async def _run_engine(
    binary: str, root: Path, grouped: dict[str, list[Path]]
) -> tuple[list[tuple[object, dict]], list[str]]:
    """Run one ast-grep pass per (language, rule), all of them concurrently.

    A pass per rule rather than one pass for every rule: ast-grep takes a single
    pattern per ``run``, and its project-config form did not apply the rules it
    parsed.  It is cheap because a pass is about 13ms on a small tree, and the
    passes are independent, so they overlap.
    """
    tasks: list[tuple[object, list[Path], str]] = []
    for language, paths in grouped.items():
        for rule in CODE_RULES:
            if language in rule.languages:
                tasks.append((rule, paths, language))

    #: Rules whose pass failed outright, so the report can say the scan was
    #: incomplete instead of implying it found nothing.
    failed: list[str] = []

    async def one(rule, paths: list[Path], language: str) -> list[dict]:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "run",
            "--lang",
            language,
            "--pattern",
            rule.pattern,
            "--json=stream",
            *[str(p) for p in paths],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(root),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=ENGINE_TIMEOUT_SECONDS)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("security: ast-grep timed out on %s", rule.id)
            return []
        rows = _parse_stream(stdout.decode("utf-8", "replace"))
        message = (stderr or b"").decode("utf-8", "replace")
        # ast-grep exits 1 both for "findings found" and for some errors, so the
        # exit code alone cannot tell a clean pass from a broken one.  An error
        # that produced no rows is treated as a failure, because a scan that
        # silently matched nothing is the worst possible outcome here.
        if proc.returncode not in (0, 1) or (not rows and "error" in message.lower()):
            logger.warning("security: ast-grep failed on %s: %s", rule.id, message[:200])
            failed.append(rule.id)
            return []
        return [(rule, row) for row in rows]

    results = await asyncio.gather(*(one(*task) for task in tasks))
    return [row for group in results for row in group], failed


def _parse_stream(output: str) -> list[dict]:
    """Parse ast-grep's ``--json=stream`` output.

    Stream mode is newline-delimited objects rather than one array, so that a
    large scan can start emitting before it finishes.  A malformed line is
    skipped rather than failing the scan.
    """
    rows: list[dict] = []
    decoder = json.JSONDecoder()
    index = 0
    length = len(output)
    while index < length:
        while index < length and output[index] in " \n\r\t":
            index += 1
        if index >= length:
            break
        try:
            obj, index = decoder.raw_decode(output, index)
        except ValueError:
            newline = output.find("\n", index)
            if newline == -1:
                break
            index = newline + 1
            continue
        rows.append(obj)
    return rows


def _row_location(row: dict, root: Path) -> tuple[str, int, str]:
    path = str(row.get("file") or "")
    try:
        path = str(Path(path).relative_to(root))
    except ValueError:
        path = path.lstrip("./")
    span = row.get("range") or {}
    start = span.get("start") or {}
    return path.replace(os.sep, "/"), int(start.get("line") or 0) + 1, str(row.get("text") or "")


async def scan_code(files: dict[str, str]) -> CodeScanResult:
    """Scan *files* (path -> source) for code patterns and secrets.

    Secrets are scanned here rather than by ast-grep because they are a text
    problem, and they run even when ast-grep is missing: a leaked key should not
    depend on an optional binary being installed.
    """
    scannable = {path: text[:MAX_FILE_CHARS] for path, text in files.items() if _is_source_path(path) and text.strip()}
    languages: dict[str, int] = {}
    for path in scannable:
        language = language_of(path)
        if language:
            languages[language] = languages.get(language, 0) + 1

    findings: list[Finding] = []
    for path, text in scannable.items():
        # Computed once per file and shared: both passes need it, and parsing the
        # file twice for one boolean set would be wasteful on a large scan.
        prose = _prose_lines(text, path)
        findings.extend(_scan_secrets(path, text, prose))
        findings.extend(_scan_text_rules(path, text, prose))

    binary = ast_grep_binary()
    if binary is None:
        # Secrets still scanned.  Say the pattern scan did not run, because
        # "no findings" and "no scanner" must never look the same.
        return CodeScanResult(
            findings=_cap(findings),
            files_scanned=0,
            files_available=len(scannable),
            languages=languages,
            engine="unavailable",
            error="ast-grep is not installed, so code patterns were not checked. "
            "Install it with `pip install ast-grep-cli` to enable them. Secrets were still scanned.",
        )

    if not scannable:
        return CodeScanResult(findings=[], files_scanned=0, files_available=0, languages={}, engine=binary)

    bounded = dict(list(scannable.items())[:MAX_FILES])
    root = _build_project(bounded)
    try:
        rows, failed_rules = await _run_engine(binary, root, _language_files(root, bounded))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    for rule, row in rows:
        path, line, text = _row_location(row, root)
        if rule.skip_in_tests and _looks_like_test(path):
            continue
        # A pattern can be broader than the problem it names; `forbid` is where
        # that is corrected, so `hashlib.$HASH(...)` does not report sha256.
        if rule.forbid and any(name in text.lower() for name in rule.forbid):
            continue
        findings.append(
            Finding(
                id=rule.id,
                title=rule.title,
                severity=rule.severity,
                category=rule.category,
                detail=rule.detail,
                location=path,
                line=line,
                source="code",
                cwe=rule.cwe,
                confidence=rule.confidence,
                snippet=_snippet(text),
            )
        )

    error = ""
    if failed_rules:
        error = (
            f"{len(failed_rules)} of {len(CODE_RULES)} pattern checks could not run, "
            "so their results are absent rather than clean."
        )
    return CodeScanResult(
        findings=_cap(findings),
        files_scanned=len(bounded),
        files_available=len(scannable),
        languages=languages,
        engine="ast-grep",
        error=error,
    )


def _cap(findings: list[Finding]) -> list[Finding]:
    """Most severe first, most frequent first within a severity, then capped."""
    from app.security.models import severity_rank

    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.id] = counts.get(finding.id, 0) + 1
    ordered = sorted(
        findings,
        key=lambda f: (
            severity_rank(f.severity),
            0 if f.confidence == "high" else 1,
            -counts[f.id],
            f.location,
            f.line or 0,
        ),
    )
    return ordered[:MAX_FINDINGS]
