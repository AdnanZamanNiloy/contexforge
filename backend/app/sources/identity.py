"""Deterministic source identity, so ingesting the same thing twice replaces it.

Every source type except GitHub used to be assigned ``uuid.uuid4()`` at ingest
time. That made ingestion non-idempotent: pasting the same article URL twice
produced two unrelated sources, both titled the same, both answering queries,
and both impossible to tell apart in the sidebar. Deleting one left the other.

A source id is now a pure function of what the source *is*, so re-ingesting
resolves to the same id and the existing chunks are replaced instead of
duplicated:

===================  ==========================================  =========================
Type                 Identity                                    Id
===================  ==========================================  =========================
``github``           ``owner/name`` from the repo URL             ``repo:owner/name``
``youtube``          the video id (watch/youtu.be/shorts/embed)   ``youtube:<id>``
``web``              the normalised URL                           ``web:<hash>``
``text``             the normalised text                          ``text:<hash>``
``pdf`` / ``docx``   the SHA-256 of the file bytes                ``pdf:<hash>``
===================  ==========================================  =========================

URLs are normalised before hashing, so cosmetic differences do not read as
different documents: case in the scheme and host, a default port, a fragment,
tracking parameters, query-parameter order, and a trailing slash are all removed.
The scheme itself is kept, because ``http://`` and ``https://`` can genuinely
serve different content and silently merging them would be a worse bug than a
rare duplicate. Path case is kept for the same reason.

File uploads are keyed on content, not filename. Two identical files are one
source even under different names, which is what a user re-uploading a corrected
copy means; a file whose bytes actually changed is a new source rather than a
silent overwrite of the old one.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = [
    "content_source_id",
    "legacy_source_id_for",
    "normalize_url",
    "url_source_id",
]

# Tracking parameters that identify a campaign, not a document. Left in, they
# make the same article hash differently on every shared link.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "gclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "ref",
        "ref_src",
        "referrer",
        "source",
    }
)

_DEFAULT_PORTS = {"http": "80", "https": "443"}

# 16 hex characters is 64 bits, which is far more than enough to separate the
# sources in one workspace while keeping the id short in logs and the sidebar.
_HASH_LENGTH = 16

_GITHUB_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s?#]+)",
    re.IGNORECASE,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_HASH_LENGTH]


def normalize_url(url: str) -> str:
    """Return a canonical form of *url*, or the stripped input if unparseable.

    An unparseable value is returned nearly as-is rather than raising: identity
    must never be the reason an ingest fails. Two unparseable inputs that differ
    will hash differently, which degrades to the old duplicate behaviour for that
    input alone.
    """
    raw = (url or "").strip()
    if not raw:
        return ""

    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw

    if not parts.scheme or not parts.netloc:
        return raw

    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    # Preserve credentials-free authority but drop the default port and any
    # userinfo, neither of which identifies a different document.
    port = parts.port
    netloc = host.lower()
    if port is not None and _DEFAULT_PORTS.get(scheme) != str(port):
        netloc = f"{netloc}:{port}"

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
    ]
    # Sorting makes ?a=1&b=2 and ?b=2&a=1 the same document.
    query = urlencode(sorted(query_pairs), doseq=True)

    # The fragment addresses a position inside the page, not a different page.
    return urlunsplit((scheme, netloc, path, query, ""))


def url_source_id(source_type: str, url: str) -> str:
    """Return the deterministic id for a URL-backed source.

    Args:
        source_type: One of ``github``, ``web`` or ``youtube``.
        url:         The URL as supplied by the user.

    Returns:
        ``repo:owner/name`` for a repository, ``youtube:<video id>`` when the
        video id can be read, and ``<type>:<hash>`` otherwise.

    Raises:
        ValueError: If ``github`` is given a URL that is not a repository.
    """
    kind = (source_type or "").strip().lower()

    if kind == "github":
        match = _GITHUB_URL_RE.match((url or "").strip())
        if not match:
            raise ValueError("Invalid GitHub repository URL")
        owner, name = match.group(1), match.group(2)
        return f"repo:{owner}/{name.removesuffix('.git')}"

    if kind == "youtube":
        # Imported lazily: the loader pulls in transcript machinery that has no
        # business being loaded just to work out an id.
        from core.ingestion.youtube_loader import extract_video_id

        try:
            return f"youtube:{extract_video_id(url)}"
        except ValueError:
            # Fall through to a URL hash. A malformed YouTube URL is the
            # loader's problem to report with a precise message, not ours.
            pass

    return f"{kind or 'web'}:{_digest(normalize_url(url))}"


def content_source_id(source_type: str, payload: bytes | str) -> str:
    """Return the deterministic id for content supplied directly.

    Args:
        source_type: ``pdf``, ``docx`` or ``text``.
        payload:     File bytes, or the text itself.

    Returns:
        ``<type>:<hash>``, stable for identical input.
    """
    kind = (source_type or "text").strip().lower() or "text"
    if isinstance(payload, str):
        # Line endings and trailing whitespace are not content, so two pastes of
        # the same text from different editors resolve to one source.
        normalised = payload.replace("\r\n", "\n").replace("\r", "\n").strip()
        return f"{kind}:{_digest(normalised)}"
    return f"{kind}:{hashlib.sha256(payload).hexdigest()[:_HASH_LENGTH]}"


def legacy_source_id_for(
    infos: list[dict],
    *,
    source_type: str,
    url: str,
) -> str | None:
    """Find an already-stored source that represents the same URL.

    Sources ingested before ids were deterministic carry random UUIDs, so a
    deterministic id would not match them and re-ingesting would leave the old
    entry behind as a second copy. This adopts the existing id instead, which
    makes the first re-ingest after the upgrade the repair point: after that the
    deterministic id exists and the lookup is not needed again.

    Args:
        infos:       Entries from ``FAISSStore.get_source_info()``.
        source_type: The type being ingested.
        url:         The URL as supplied, normalised for comparison.

    Returns:
        The existing ``source_id``, or ``None`` when nothing matches.
    """
    target = normalize_url(url)
    kind = (source_type or "").strip().lower()
    for info in infos or []:
        if (info.get("type") or "").strip().lower() != kind:
            continue
        existing = normalize_url(str(info.get("url") or ""))
        if existing and existing == target:
            return info.get("source_id")
    return None
