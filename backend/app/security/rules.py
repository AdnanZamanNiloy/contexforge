"""The rules the code scan matches.

Two kinds, deliberately kept apart because they fail differently.

**Structural patterns** are ast-grep patterns: they match the shape of code, not
its text, so a password in a comment or a string literal is not a finding while a
real call to ``eval`` is.  That is the whole reason this scanner is ast-grep and
not a pile of regular expressions -- a regex scanner flags ``# password = 1``,
and a report that cries wolf is a report nobody reads.

**Secret patterns** are the one place text matching is correct, because a secret
*is* a string.  They are paired with an exclusion list for the placeholder forms
that make up most of the false positives in a naive scan: ``changeme``,
``xxxxxxxx``, ``your-api-key-here``, and values that are obviously not keys.

Every rule carries a ``confidence``.  A pattern that is a problem in one context
and correct in another -- ``hashlib.md5`` is a fine checksum and a broken
signature, ``subprocess.run`` is fine with a list and fatal with a string -- is
marked ``medium`` and reported as *worth reviewing* rather than counted as a
confirmed flaw.  Overstating that is the fastest way to make a security report
useless.

Provenance: the categories and the shape of each rule are modelled on
semgrep's registry, and the CWE identifiers are the standard ones.  The patterns
are written for this codebase rather than copied, and they are far fewer than
semgrep's -- the point is precision, not coverage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "CODE_RULES",
    "SECRET_PATTERNS",
    "TEXT_RULES",
    "SecretRule",
    "language_of",
]


@dataclass(frozen=True)
class CodeRule:
    """One structural pattern, and what a match means."""

    id: str
    title: str
    severity: str
    category: str
    pattern: str
    languages: tuple[str, ...]
    detail: str
    cwe: str = ""
    confidence: str = "high"
    #: Rules that only matter in a particular context set this, so a match on
    #: ``subprocess.run(x)`` is reported but not when the file is a test.
    skip_in_tests: bool = True
    #: Substrings that disqualify a match.  Used where a pattern is broader than
    #: the problem: ``hashlib.$HASH(...)`` matches sha256 as readily as md5, and
    #: calling sha256 a weak hash would be simply wrong.
    forbid: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecretRule:
    """A credential shape, with the placeholders that are not credentials."""

    id: str
    title: str
    pattern: re.Pattern
    severity: str = "high"
    category: str = "Secrets"
    cwe: str = "CWE-798"
    #: Case-insensitive fragments that make a match a placeholder rather than a
    #: leak.  Without these the scan is unusable on any real repository.
    placeholders: tuple[str, ...] = ()


# ast-grep language names, which are not the extension names.
def language_of(path: str) -> str | None:
    """The ast-grep language for a path, or ``None`` when it is not source."""
    base = path.rsplit("/", 1)[-1].lower()
    if base.endswith((".py", ".pyi")):
        return "python"
    if base.endswith((".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")):
        return "javascript"
    if base.endswith((".go",)):
        return "go"
    if base.endswith((".java",)):
        return "java"
    if base.endswith((".rb",)):
        return "ruby"
    if base.endswith((".php",)):
        return "php"
    if base.endswith((".rs",)):
        return "rust"
    if base.endswith((".c", ".h")):
        return "c"
    if base.endswith((".cpp", ".cc", ".cxx", ".hpp", ".hh")):
        return "cpp"
    return None


#: Hashes that are not weak, so a generic ``$HASH`` match on one of these is
#: dropped rather than reported.
_STRONG_HASHES = ("sha256", "sha384", "sha512", "sha224", "sha3", "blake2", "shake", "whirlpool")

_PY = ("python",)
_JS = ("javascript",)
_GO = ("go",)
_JAVA = ("java",)
_ANY_PY_JS = ("python", "javascript")

CODE_RULES: tuple[CodeRule, ...] = (
    # --- code execution -------------------------------------------------- #
    CodeRule(
        id="dynamic-eval",
        title="Dynamic code execution",
        severity="high",
        category="Code execution",
        pattern="eval($$$A)",
        languages=_ANY_PY_JS,
        detail="eval executes its argument as code. Anything reaching it becomes program text.",
        cwe="CWE-95",
    ),
    CodeRule(
        id="dynamic-exec",
        title="Dynamic code execution",
        severity="high",
        category="Code execution",
        pattern="exec($$$A)",
        languages=_PY,
        detail="exec executes its argument as code in the current interpreter.",
        cwe="CWE-95",
    ),
    CodeRule(
        id="js-function-constructor",
        title="Code built from a string",
        severity="high",
        category="Code execution",
        pattern="new Function($$$A)",
        languages=_JS,
        detail="new Function compiles a string into a callable, which is eval by another name.",
        cwe="CWE-95",
    ),
    CodeRule(
        id="python-os-system",
        title="Shell invoked through os.system",
        severity="high",
        category="Injection",
        pattern="os.system($CMD)",
        languages=_PY,
        detail="os.system passes its argument to a shell, so any interpolated value is shell syntax.",
        cwe="CWE-78",
    ),
    CodeRule(
        id="python-shell-true",
        title="Subprocess run through a shell",
        severity="high",
        category="Injection",
        pattern="subprocess.$F($$$A, shell=True)",
        languages=_PY,
        detail="shell=True hands the whole command line to a shell; pass an argument list instead.",
        cwe="CWE-78",
    ),
    CodeRule(
        id="node-child-process-exec",
        title="Shell invoked through child_process.exec",
        severity="high",
        category="Injection",
        pattern="child_process.exec($CMD)",
        languages=_JS,
        detail="exec runs through a shell. execFile with an argument array avoids the shell entirely.",
        cwe="CWE-78",
    ),
    CodeRule(
        id="go-exec-command",
        title="Command built from a value",
        severity="medium",
        category="Injection",
        pattern="exec.Command($NAME, $$$A)",
        languages=_GO,
        detail="exec.Command is safe with fixed arguments; a value interpolated into the name or args is not.",
        cwe="CWE-78",
        confidence="medium",
    ),
    # --- deserialization ------------------------------------------------- #
    CodeRule(
        id="python-pickle-loads",
        title="Unpickling untrusted data",
        severity="high",
        category="Deserialization",
        pattern="pickle.loads($$$A)",
        languages=_PY,
        detail="pickle reconstructs arbitrary objects and can execute code on load. Only unpickle data you produced.",
        cwe="CWE-502",
    ),
    CodeRule(
        id="python-yaml-unsafe-load",
        title="YAML loaded unsafely",
        severity="high",
        category="Deserialization",
        pattern="yaml.load($$$A)",
        languages=_PY,
        detail="yaml.load can construct arbitrary Python objects. Use yaml.safe_load.",
        cwe="CWE-502",
    ),
    # --- transport ------------------------------------------------------- #
    CodeRule(
        id="python-verify-false",
        title="TLS verification disabled",
        severity="high",
        category="Transport",
        pattern="verify=False",
        languages=_ANY_PY_JS,
        detail="Certificate verification turned off makes the connection interceptable.",
        cwe="CWE-295",
    ),
    CodeRule(
        id="python-insecure-hostname",
        title="TLS hostname check disabled",
        severity="high",
        category="Transport",
        pattern="ssl._create_unverified_context()",
        languages=_PY,
        detail="An unverified context accepts any certificate for any host.",
        cwe="CWE-295",
    ),
    # --- cryptography ---------------------------------------------------- #
    CodeRule(
        id="python-ecb-mode",
        title="AES in ECB mode",
        severity="high",
        category="Cryptography",
        pattern="$C.MODE_ECB",
        languages=_PY,
        detail="ECB encrypts identical plaintext blocks to identical ciphertext, so it leaks structure.",
        cwe="CWE-327",
    ),
    CodeRule(
        id="python-weak-hash",
        title="Weak hash algorithm",
        severity="medium",
        category="Cryptography",
        pattern="hashlib.$HASH($$$A)",
        languages=_PY,
        detail="md5 and sha1 are broken for signatures and passwords. Fine for a content checksum.",
        cwe="CWE-327",
        confidence="medium",
        forbid=_STRONG_HASHES,
    ),
    CodeRule(
        id="js-weak-hash",
        title="Weak hash algorithm",
        severity="medium",
        category="Cryptography",
        pattern="crypto.createHash($HASH)",
        languages=_JS,
        detail="md5 and sha1 are broken for signatures and passwords. Fine for a content checksum.",
        cwe="CWE-327",
        confidence="medium",
        forbid=_STRONG_HASHES,
    ),
    CodeRule(
        id="java-weak-hash",
        title="Weak hash algorithm",
        severity="medium",
        category="Cryptography",
        pattern='MessageDigest.getInstance($HASH)',
        languages=_JAVA,
        detail="MD5 and SHA-1 are broken for signatures and passwords. Fine for a content checksum.",
        cwe="CWE-327",
        confidence="medium",
        forbid=_STRONG_HASHES,
    ),
    # --- browser sinks --------------------------------------------------- #
    CodeRule(
        id="js-inner-html",
        title="Unescaped HTML assigned",
        severity="medium",
        category="Injection",
        pattern="$EL.innerHTML = $VALUE",
        languages=_JS,
        detail="innerHTML parses its argument as markup, so untrusted text becomes script.",
        cwe="CWE-79",
        confidence="medium",
    ),
    CodeRule(
        id="js-document-write",
        title="document.write of a value",
        severity="medium",
        category="Injection",
        pattern="document.write($VALUE)",
        languages=_JS,
        detail="document.write injects markup into the page.",
        cwe="CWE-79",
        confidence="medium",
    ),
    # --- memory safety --------------------------------------------------- #
    CodeRule(
        id="c-unsafe-copy",
        title="Unbounded copy into a fixed buffer",
        severity="high",
        category="Memory safety",
        pattern="strcpy($$$A)",
        languages=("c", "cpp"),
        detail="strcpy has no length limit; strncpy or a bounded copy avoids the overflow.",
        cwe="CWE-120",
    ),
    CodeRule(
        id="c-sprintf",
        title="Unbounded format into a fixed buffer",
        severity="medium",
        category="Memory safety",
        pattern="sprintf($$$A)",
        languages=("c", "cpp"),
        detail="sprintf writes without a bound; snprintf takes a size.",
        cwe="CWE-120",
    ),
)

# Fragments that mark a string as a placeholder rather than a live credential.
# Without these a single repository surfaces dozens of fake "leaked" keys and
# the real one is lost in the noise.
_PLACEHOLDERS = (
    "example",
    "changeme",
    "change-me",
    "your-",
    "your_",
    "placeholder",
    "dummy",
    "sample",
    "redacted",
    "xxxx",
    "todo",
    "insert",
    "replace",
    "fake",
    "test",
    "notreal",
    "<",
    "***",
    "abcdef123456",
)

#: A value made only of lowercase letters and underscores is a name, not a
#: credential.  `app.secret_key = "secret_key"` and `password = "development"`
#: are the two most common "leaks" in any real codebase, and neither is a value
#: anyone generated.  Every genuine key carries a digit or an upper-case letter,
#: so this one test removes the whole class rather than a word at a time.
_LOWERCASE_WORD = re.compile(r"^[a-z_]+$")


def _secret(
    rule_id: str,
    title: str,
    pattern: str,
    severity: str = "high",
    cwe: str = "CWE-798",
) -> SecretRule:
    return SecretRule(
        id=rule_id,
        title=title,
        pattern=re.compile(pattern),
        severity=severity,
        cwe=cwe,
        placeholders=_PLACEHOLDERS,
    )


@dataclass(frozen=True)
class TextRule:
    """A rule that has to be matched as text, because it is not a code shape.

    A handful of security switches are bare keyword arguments or config keys
    rather than calls -- ``verify=False``, ``rejectUnauthorized: false`` -- so
    there is no AST node to match and no pattern to write.  Matching them as text
    is safe precisely because the token is distinctive: unlike ``password``,
    ``verify=False`` does not appear in prose.
    """

    id: str
    title: str
    pattern: re.Pattern
    severity: str
    category: str
    detail: str
    cwe: str = ""
    confidence: str = "high"


#: Config and code switches that disable a security control.  All are distinctive
#: enough that matching them as text produces no false positives.
TEXT_RULES: tuple[TextRule, ...] = (
    TextRule(
        id="tls-verify-disabled",
        title="TLS verification disabled",
        pattern=re.compile(r"\bverify\s*=\s*False\b"),
        severity="high",
        category="Transport",
        detail="Certificate verification turned off makes the connection interceptable.",
        cwe="CWE-295",
    ),
    TextRule(
        id="node-tls-reject-unauthorized",
        title="TLS verification disabled for Node",
        pattern=re.compile(r"rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0"),
        severity="high",
        category="Transport",
        detail="Certificate verification turned off makes the connection interceptable.",
        cwe="CWE-295",
    ),
    TextRule(
        id="insecure-random",
        title="Non-cryptographic randomness",
        pattern=re.compile(r"Math\.random\(\)"),
        severity="low",
        category="Cryptography",
        detail="Math.random is predictable. Use crypto for tokens, keys and nonces.",
        cwe="CWE-338",
        confidence="medium",
    ),
    TextRule(
        id="django-debug-true",
        title="Debug mode enabled",
        pattern=re.compile(r"^\s*DEBUG\s*=\s*True\s*$", re.MULTILINE),
        severity="medium",
        category="Transport",
        detail="DEBUG=True serves tracebacks with settings to anyone who triggers an error.",
        cwe="CWE-489",
    ),
)


SECRET_PATTERNS: tuple[SecretRule, ...] = (
    _secret("aws-access-key", "AWS access key id", r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b"),
    _secret(
        "aws-secret-key",
        "AWS secret access key",
        r"(?i)aws_?secret_?access_?key\s*[=:]\s*[\"']?([A-Za-z0-9/+=]{40})[\"']?",
    ),
    _secret("github-token", "GitHub token", r"\b(gh[pousr]_[A-Za-z0-9]{36,255})\b"),
    _secret("slack-token", "Slack token", r"\b(xox[baprs]-[A-Za-z0-9-]{10,72})\b"),
    _secret("stripe-key", "Stripe secret key", r"\b(sk_(?:live|test)_[A-Za-z0-9]{16,99})\b"),
    _secret("google-api-key", "Google API key", r"\b(AIza[0-9A-Za-z\-_]{35})\b"),
    _secret(
        "private-key-block",
        "Private key committed",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
    ),
    _secret(
        "generic-password-assignment",
        "Hardcoded password",
        r"(?i)\b(?:pass(?:word|wd)|pw|pwd|secret_?key|api_?key|auth_?token|access_?token)\b"
        r"\s*[:=]\s*[\"']([^\"'\n]{8,120})[\"']",
    ),
    # A bare `token` or `secret` is weaker evidence than the names above --
    # `token` is a common name for a counter, a parser token or a CSRF token --
    # so it is reported as worth reviewing rather than as a leaked credential.
    _secret(
        "generic-token-assignment",
        "Hardcoded token",
        r"(?i)\b(?:token|secret)\b\s*[:=]\s*[\"']([^\"'\n]{12,120})[\"']",
        severity="medium",
    ),
    _secret(
        "bearer-token-literal",
        "Hardcoded bearer token",
        r"(?i)\bauthorization\b\s*[:=]\s*[\"']?(?:Bearer|Basic)\s+([A-Za-z0-9\-._~+/]{16,200})",
        severity="medium",
    ),
)
