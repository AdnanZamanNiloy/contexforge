from __future__ import annotations

import logging
from typing import List

import httpx
import trafilatura

from .base_loader import BaseLoader
from core.types import Document
from observability.tracer import observe

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; ContextForge/2.0; "
    "+https://github.com/yourorg/contextforge)"
)


_MIN_LINE_LENGTH = 10


class WebLoader(BaseLoader):

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 2,
        enable_js_fallback: bool = False,
    ) -> None:
      
        self._timeout = timeout
        self._max_retries = max_retries
        self._enable_js_fallback = enable_js_fallback

    @observe(name="load_web")
    async def load(
        self,
        source: str | bytes,
        source_id: str,
        filename: str | None = None,
    ) -> List[Document]:
    
        if not isinstance(source, str):
            raise ValueError(
                f"WebLoader expects a URL string, got {type(source).__name__}"
            )

        html = await self._fetch(source)

        text = self._extract_main_content(html)

        # JS fallback: only triggered when enabled AND extraction failed
        if not text and self._enable_js_fallback:
            logger.info("Primary extraction empty, trying JS fallback. url=%s", source)
            html = await self._fetch_with_js(source)
            text = self._extract_main_content(html)

        if not text:
            raise RuntimeError(
                f"Failed to extract meaningful content from {source}. "
                "Page may be JS-only — consider enable_js_fallback=True."
            )

        text = self._clean_text(text)

        # Use trafilatura's built-in metadata 
        title = self._extract_title(html)
        lang = self._detect_language(text)

        metadata = {
            "url": source,
            "source_id": source_id,
            "source_type": "web",
            "title": title,
            "language": lang,
            "content_length": len(text),  
        }

        return [
            Document(
                document_id=source_id,
                text=text,
                metadata=metadata,
                source_type="web",
            )
        ]

    # ------------------------------------------------------------------ #
    # FETCHING
    # ------------------------------------------------------------------ #

    async def _fetch(self, url: str) -> str:
        
        transport = httpx.AsyncHTTPTransport(retries=self._max_retries)

        async with httpx.AsyncClient(
            timeout=self._timeout,
            transport=transport,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Now properly caught separately from network errors
                logger.error(
                    "HTTP error fetching URL. url=%s status=%d",
                    url, exc.response.status_code,
                )
                raise RuntimeError(
                    f"HTTP {exc.response.status_code} fetching {url}"
                ) from exc
            except httpx.RequestError as exc:
                logger.error("Network error fetching URL. url=%s error=%s", url, exc)
                raise RuntimeError(f"Network error fetching {url}: {exc}") from exc

         
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                raise ValueError(
                    f"WebLoader expects HTML, got '{content_type}' for {url}"
                )

            return response.text  

    # ------------------------------------------------------------------ #
    # EXTRACTION
    # ------------------------------------------------------------------ #

    def _extract_main_content(self, html: str) -> str:
      
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,       
            favor_precision=True,
        )
        return text or ""

    def _extract_title(self, html: str) -> str:
      
        meta = trafilatura.bare_extraction(html) or {}
        return meta.get("title", "") or ""

    # ------------------------------------------------------------------ #
    # CLEANING
    # ------------------------------------------------------------------ #

    def _clean_text(self, text: str) -> str:
        
        lines = [line.strip() for line in text.splitlines()]
        lines = [l for l in lines if len(l) >= _MIN_LINE_LENGTH]

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for line in lines:
            if line not in seen:
                seen.add(line)
                unique.append(line)

        return "\n\n".join(unique)

    # ------------------------------------------------------------------ #
    # LANGUAGE DETECTION
    # ------------------------------------------------------------------ #

    def _detect_language(self, text: str) -> str:
        
        try:
            from langdetect import detect, DetectorFactory, LangDetectException
            DetectorFactory.seed = 0       
            return detect(text[:1000])
        except Exception:           
            return "unknown"

    # ------------------------------------------------------------------ #
    # JS FALLBACK (OPTIONAL / ADVANCED)
    # ------------------------------------------------------------------ #

    async def _fetch_with_js(self, url: str) -> str:
  
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright not installed."
            ) from exc

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:                           
                page = await browser.new_page()
                await page.goto(url, timeout=int(self._timeout * 1000))
                html = await page.content()
            finally:
                await browser.close()     

        return html