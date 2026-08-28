from __future__ import annotations

import asyncio
import logging
import re

import httpx
import requests

from core.types import Document
from observability.tracer import observe

from .base_loader import BaseLoader

logger = logging.getLogger(__name__)

# YouTube video IDs are 11-char base64url strings.
_VIDEO_ID_RE = re.compile(r"\b([A-Za-z0-9_-]{11})\b")

# Recognised share/embed URL shapes (watch, youtu.be, shorts, embed, live),
# with the video id captured in group 2.
_YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?"
    r"(?:youtube\.com/(?:watch\?[^#\s]*v=|shorts/|embed/|live/|v/)"
    r"|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)

_OEMBED_URL = "https://www.youtube.com/oembed"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# YouTube transcripts can only be fetched for a handful of languages; English
# plus Hindi mirrors the reference Tube-AI-API implementation. Auto-generated
# captions are allowed so the loader works for videos without manual subtitles.
_DEFAULT_LANGUAGES = ("en", "hi")


def extract_video_id(url: str) -> str:
    """Return the 11-char YouTube video id from *url*, or raise :class:`ValueError`."""
    if not url or not url.strip():
        raise ValueError("YouTube source must be a non-blank URL")
    url = url.strip()

    # Bare video id (no URL at all).
    if _VIDEO_ID_RE.fullmatch(url):
        return url

    match = _YOUTUBE_URL_RE.search(url)
    if not match:
        raise ValueError(
            f"Cannot detect a YouTube video id in: '{url}'. Expected a watch, youtu.be, shorts, embed, or live URL."
        )
    return match.group(1)


class YouTubeLoader(BaseLoader):
    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 2,
        proxy_url: str | None = None,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._transcript_timeout = max(45.0, timeout * 1.5)
        self._proxy_url = proxy_url or None

    @observe(name="load_youtube")
    async def load(
        self,
        source: str | bytes,
        source_id: str,
        filename: str | None = None,
        metadata: dict | None = None,
    ) -> list[Document]:
        if not isinstance(source, str):
            raise TypeError(f"YouTubeLoader expects a URL string, got {type(source).__name__}")

        video_url = source.strip()
        video_id = extract_video_id(video_url)

        transcript, language_code = await self._fetch_transcript(video_id)

        video_meta = await self._fetch_video_meta(video_url, video_id)

        meta = {
            "url": video_url,
            "source_id": source_id,
            "source_type": "youtube",
            "title": video_meta.get("title") or f"YouTube {video_id}",
            "thumbnail": video_meta.get("thumbnail_url") or "",
            "author": video_meta.get("author_name") or "",
            "video_id": video_id,
            "language": language_code or _DEFAULT_LANGUAGES[0],
            "content_length": len(transcript),
        }
        if metadata:
            meta.update(metadata)

        return [
            Document(
                document_id=source_id,
                text=transcript,
                metadata=meta,
                source_type="youtube",
            )
        ]

    # ------------------------------------------------------------------ #
    # TRANSCRIPT
    # ------------------------------------------------------------------ #

    async def _fetch_transcript(self, video_id: str) -> tuple[str, str | None]:
        # youtube_transcript_api is synchronous (requests-based); run it in a
        # worker thread so the event loop is not blocked during ingestion.
        # The whole fetch is time-bounded so a slow/throttled caption endpoint
        # (e.g. listing a video with captions in an unusual language) can never
        # make the ingest request hang indefinitely.
        try:
            snippets, language_code = await asyncio.wait_for(
                asyncio.to_thread(self._get_transcript_snippets, video_id),
                timeout=self._transcript_timeout,
            )
        except TimeoutError:
            logger.error("Transcript fetch timed out. video_id=%s", video_id)
            raise RuntimeError(f"Timed out fetching a transcript for video '{video_id}'.") from None
        except Exception as exc:
            logger.error("Failed to fetch transcript. video_id=%s error=%s", video_id, exc)
            raise RuntimeError(f"Failed to fetch YouTube transcript: {exc}") from exc
        text = " ".join(snippet.text for snippet in snippets)
        return text, language_code

    def _get_transcript_snippets(self, video_id: str) -> tuple[list, str | None]:
        from youtube_transcript_api import YouTubeTranscriptApi

        # Reuse a single requests session so the browser-like headers are applied
        # consistently.  A proxy (set via YOUTUBE_PROXY) routes transcript
        # requests through a residential/rotating proxy, which is the documented
        # workaround for YouTube blocking cloud-provider IP addresses.
        session = requests.Session()
        session.headers.update({"User-Agent": _USER_AGENT})
        if self._proxy_url:
            session.proxies = {
                "http": self._proxy_url,
                "https": self._proxy_url,
            }

        api = YouTubeTranscriptApi(http_client=session)

        # Preferred languages first (English + Hindi, matching the reference
        # implementation).  Transcripts are served directly in these languages
        # and need no translation.
        try:
            fetched = api.fetch(
                video_id,
                languages=list(_DEFAULT_LANGUAGES),
                preserve_formatting=False,
            )
            return fetched.snippets, _DEFAULT_LANGUAGES[0]
        except Exception:
            # Fallback: this video may only carry captions in another language
            # (e.g. auto-generated Korean).  Pick the first available transcript
            # — manually-created transcripts are yielded before generated ones.
            for transcript in api.list(video_id):
                try:
                    fetched = transcript.fetch(preserve_formatting=False)
                    return fetched.snippets, getattr(transcript, "language_code", None)
                except Exception:
                    continue

        raise RuntimeError(
            f"No retrievable transcript found for video '{video_id}'. "
            "YouTube may be blocking this IP (common on cloud providers). "
            "Set YOUTUBE_PROXY in backend/.env to a residential/rotating proxy "
            "to work around the block."
        )

    # ------------------------------------------------------------------ #
    # VIDEO METADATA (oEmbed)
    # ------------------------------------------------------------------ #

    async def _fetch_video_meta(self, video_url: str, video_id: str) -> dict:
        params = {"url": video_url, "format": "json"}

        transport = httpx.AsyncHTTPTransport(retries=self._max_retries)
        async with httpx.AsyncClient(
            timeout=self._timeout,
            transport=transport,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            try:
                response = await client.get(_OEMBED_URL, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "oEmbed HTTP %d for video_id=%s — using id fallback.",
                    exc.response.status_code,
                    video_id,
                )
                return {}
            except httpx.RequestError as exc:
                logger.warning(
                    "oEmbed network error for video_id=%s — using id fallback. error=%s",
                    video_id,
                    exc,
                )
                return {}

        try:
            return response.json()
        except Exception:
            return {}
