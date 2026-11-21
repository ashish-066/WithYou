"""Fetch a public web page's text, safely.

The links come from recruiters (a candidate's portfolio, blog, project pages),
so they're untrusted: only http(s) to public internet addresses (never
localhost, private networks or cloud metadata, re-checked on every redirect),
a short timeout, a size cap and text-only content. The page's text is data for
the interviewer, never instructions.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TIMEOUT_S = 10.0
MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3
MAX_TEXT_CHARS = 4_000
USER_AGENT = "PresenceViewBot/1.0 (candidate background check)"


class UnsafeURLError(ValueError):
    pass


@dataclass
class Page:
    url: str
    title: str
    text: str


async def _public_address(host: str) -> None:
    """Raise unless every address the host resolves to is on the public internet."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UnsafeURLError(f"cannot resolve {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURLError(f"{host} is not a public address")


def _check_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeURLError("only http(s) web addresses")
    if parsed.username or parsed.password:
        raise UnsafeURLError("no credentials in links")
    if parsed.port not in (None, 80, 443):
        raise UnsafeURLError("only standard web ports")
    return parsed.hostname


def page_text(html: str) -> tuple[str, str]:
    """(title, readable text) of an HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    for tag in soup(["head", "script", "style", "noscript", "svg", "nav", "footer", "form", "iframe"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return title[:200], text


async def fetch_page(url: str, client: httpx.AsyncClient | None = None) -> Page:
    """Fetch one page's text. Raises UnsafeURLError or httpx errors."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False)
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await _public_address(_check_url(current))
            async with client.stream("GET", current, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain"}) as r:
                if r.is_redirect:
                    location = r.headers.get("location")
                    if not location:
                        raise UnsafeURLError("redirect without a location")
                    current = urljoin(current, location)
                    continue
                r.raise_for_status()
                kind = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if kind not in ("text/html", "text/plain", "application/xhtml+xml"):
                    raise UnsafeURLError(f"not a web page ({kind or 'unknown type'})")
                body = b""
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        break
                raw = body[:MAX_BYTES].decode(r.encoding or "utf-8", errors="replace")
                if kind == "text/plain":
                    return Page(current, "", re.sub(r"\s+", " ", raw).strip()[:MAX_TEXT_CHARS])
                title, text = page_text(raw)
                return Page(current, title, text[:MAX_TEXT_CHARS])
        raise UnsafeURLError("too many redirects")
    finally:
        if own:
            await client.aclose()


async def fetch_pages(urls: list[str]) -> list[dict]:
    """Each link's text, or why it couldn't be read. Never raises."""

    async def one(url: str) -> dict:
        try:
            page = await fetch_page(url)
            return {"url": url, "final_url": page.url, "title": page.title, "text": page.text, "error": None}
        except Exception as e:
            logger.info(f"Background link not read ({url}): {e}")
            return {"url": url, "final_url": None, "title": "", "text": "", "error": str(e)[:200]}

    return list(await asyncio.gather(*(one(u) for u in urls[:10])))
