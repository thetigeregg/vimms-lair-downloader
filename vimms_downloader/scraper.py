"""
Vimm's Lair scraper — pure httpx + BeautifulSoup4.

Uses only BeautifulSoup4 and httpx at project runtime.
"""

import base64
import json
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from vimms_downloader.config import Config, config as default_config

BASE_URL = "https://vimm.net"


def _make_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }


class VimmScraper:
    """
    Context-manager wrapper around an httpx session.

    Usage example::

        with VimmScraper() as scraper:
            results = scraper.search("mario", system="NES")
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or default_config
        headers = _make_headers(self.config.user_agent)
        self._client = httpx.Client(
            headers=headers,
            timeout=self.config.http_timeout,
            follow_redirects=True,
        )

    def __enter__(self) -> "VimmScraper":
        return self

    def __exit__(self, *_) -> None:
        self._client.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str) -> BeautifulSoup:
        """GET a URL and return a BeautifulSoup object using the lxml parser."""
        resp = self._client.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    @staticmethod
    def _decode_canvas(soup: BeautifulSoup, selector: str) -> str:
        """
        Vimm.net encodes important text (title, filename) as Base64
        in the ``data-v`` attribute of a ``<canvas>`` element.
        """
        el = soup.select_one(selector)
        if el and el.get("data-v"):
            try:
                return base64.b64decode(el["data-v"]).decode("utf-8")
            except Exception:
                pass
        return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, system: Optional[str] = None) -> list[dict]:
        """
        Search for games by text query, optionally filtered by system.

        URL: ``/vault/?p=list&q=<query>[&system=<system>]``

        Returns:
            List of ``{"game_id": int, "title": str, "url": str}``
        """
        params: dict[str, str] = {"p": "list", "q": query}
        if system:
            params["system"] = system
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        soup = self._get(f"{BASE_URL}/vault/?{qs}")

        results: list[dict] = []
        for row in soup.select("table.rounded.striped tr"):
            links = row.select("a[href*='/vault/']")
            link = None
            for l in links:
                href = l.get("href", "")
                if "/999999" not in href and "display:none" not in l.get("style", ""):
                    link = l
                    break

            if not link:
                continue

            href = link.get("href", "")
            parts = href.strip("/").split("/")
            if parts and parts[-1].isdigit():
                results.append({
                    "game_id": int(parts[-1]),
                    "title": link.get_text(strip=True),
                    "url": BASE_URL + href,
                })
        return results

    def browse(self, system: str, letter: Optional[str] = None) -> list[dict]:
        """
        Browse the game list for a given system, optionally filtered by letter.

        URL: ``/vault/<system>[/<LETTER>]``

        Returns:
            List of ``{"game_id": int, "title": str, "url": str}``
        """
        url = f"{BASE_URL}/vault/{system}"
        if letter:
            url += f"/{letter.upper()}"
        soup = self._get(url)
        results: list[dict] = []

        for link in soup.select("table.rounded.striped a[href]"):
            href = link.get("href", "")
            if "/999999" in href or "display:none" in link.get("style", ""):
                continue
            parts = href.strip("/").split("/")
            if len(parts) >= 2 and parts[-1].isdigit():
                results.append({
                    "game_id": int(parts[-1]),
                    "title": link.get_text(strip=True),
                    "url": BASE_URL + href,
                })
        return results

    def get_game_detail(self, game_id: int) -> dict:
        """
        Fetch the full details of a single game from ``/vault/<game_id>``.

        Extracted information:
        - ``media_id``  — from the hidden download form input (static, no JS)
        - ``media_list``— parsed ``media`` list containing id, version, title, etc.
        - ``formats``   — list of available disk/ROM formats (e.g. .wbfs, .rvz)
        - ``versions``  — list of available game versions (e.g. 1.0, 1.1, 1.2)
        - ``download_host`` — download mirror domain (dl.vimm.net, dl2.vimm.net, etc.)
        - ``title``     — Base64-decoded from ``canvas#canvas[data-v]``
        - ``filename``  — original ROM filename (canvas#canvas2)
        """
        url = f"{BASE_URL}/vault/{game_id}"
        soup = self._get(url)

        # 1. Extract the `media` array from a script tag
        media = []
        for script in soup.select("script"):
            script_text = script.string or script.text or ""
            if "let media=" in script_text:
                m = re.search(r'let media\s*=\s*(\[.*?\]);', script_text, re.DOTALL)
                if m:
                    try:
                        media = json.loads(m.group(1))
                    except Exception:
                        pass
                break

        # 2. Extract the available format options
        formats = []
        for opt in soup.select("select#dl_format option"):
            formats.append({
                "value": int(opt.get("value", 0)),
                "name": opt.get_text(strip=True),
                "title": opt.get("title", ""),
            })

        # 3. Extract the available version options
        versions = []
        for opt in soup.select("select#dl_version option"):
            versions.append(opt.get_text(strip=True))

        # 4. Extract the download mirror domain (e.g. //dl2.vimm.net/ or //dl3.vimm.net/)
        form = soup.select_one("form#dl_form")
        download_host = "https://dl3.vimm.net/"
        if form:
            action = form.get("action", "")
            if action.startswith("//"):
                download_host = "https:" + action
            elif action.startswith("/"):
                download_host = "https://vimm.net" + action
            elif action:
                download_host = action

        # Default mediaId (hidden input)
        media_input = soup.select_one("input[name='mediaId']")
        default_media_id = int(media_input["value"]) if media_input else None

        title = self._decode_canvas(soup, "canvas#canvas")
        filename_hint = self._decode_canvas(soup, "canvas#canvas2")

        info: dict[str, str] = {}
        for row in soup.select("table.rounded.cellpadding1 tr"):
            cells = row.select("td")
            if len(cells) >= 3:
                key = (
                    cells[0].get_text(strip=True)
                    .lower()
                    .replace(" ", "_")
                    .replace("#", "num")
                )
                val = cells[2].get_text(strip=True)
                if key and val:
                    info[key] = val

        size_el = soup.select_one("#dl_size")
        file_size = size_el.get_text(strip=True) if size_el else None

        section_el = soup.select_one(".sectionTitle")
        system = section_el.get_text(strip=True) if section_el else None

        return {
            "game_id": game_id,
            "title": title,
            "filename": filename_hint,
            "system": system,
            "media_id": default_media_id,
            "media_list": media,
            "formats": formats,
            "versions": versions,
            "download_host": download_host,
            "year": info.get("year"),
            "players": info.get("players"),
            "file_size": file_size,
            "url": url,
        }
