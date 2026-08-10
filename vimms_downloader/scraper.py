"""
Scraper Vimm's Lair — pure httpx + BeautifulSoup4.

Murni menggunakan BeautifulSoup4 dan httpx di runtime proyek.
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
    Context-manager wrapper untuk sesi httpx.

    Contoh penggunaan::

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
        """GET URL dan kembalikan BeautifulSoup dengan parser lxml."""
        resp = self._client.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")

    @staticmethod
    def _decode_canvas(soup: BeautifulSoup, selector: str) -> str:
        """
        Vimm.net meng-encode teks penting (judul, filename) sebagai
        Base64 dalam atribut ``data-v`` elemen ``<canvas>``.
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
        Cari game berdasarkan query teks, opsional filter per sistem.

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
        Browse daftar game untuk sistem tertentu, opsional filter per huruf.

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
        Ambil detail lengkap satu game dari ``/vault/<game_id>``.

        Informasi yang di-extract:
        - ``media_id``  — dari hidden input form download (statis, tanpa JS)
        - ``media_list``— parsed list ``media`` berisi id, version, title dll
        - ``formats``   — list format disk/ROM yang tersedia (e.g. .wbfs, .rvz)
        - ``versions``  — list versi game yang tersedia (e.g. 1.0, 1.1, 1.2)
        - ``download_host`` — domain cermin download (dl.vimm.net, dl2.vimm.net dll)
        - ``title``     — decode Base64 dari ``canvas#canvas[data-v]``
        - ``filename``  — nama file ROM asli (canvas#canvas2)
        """
        url = f"{BASE_URL}/vault/{game_id}"
        soup = self._get(url)

        # 1. Ekstrak array `media` dari tag script
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

        # 2. Ekstrak opsi format yang tersedia
        formats = []
        for opt in soup.select("select#dl_format option"):
            formats.append({
                "value": int(opt.get("value", 0)),
                "name": opt.get_text(strip=True),
                "title": opt.get("title", ""),
            })

        # 3. Ekstrak opsi versi yang tersedia
        versions = []
        for opt in soup.select("select#dl_version option"):
            versions.append(opt.get_text(strip=True))

        # 4. Ekstrak domain mirror download (e.g. //dl2.vimm.net/ atau //dl3.vimm.net/)
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

        # mediaId default (hidden input)
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
