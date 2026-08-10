"""
Downloader Vimm's Lair.

Strategi (prioritas berurutan):
1. aria2c (resume & multi-connection, auto filename)
2. wget (resume, auto filename via --content-disposition)
3. httpx GET streaming (fallback terakhir, progress bar)

Output: <DOWNLOAD_DIR>/<SYSTEM>/<game_title>/<filename>
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Konfigurasi dari .env -----------------------------------------------
DOWNLOAD_DIR   = Path(os.getenv("DOWNLOAD_DIR", "~/roms")).expanduser()
ARIA2_CONN     = int(os.getenv("ARIA2_CONNECTIONS", "1"))
USE_WGET       = os.getenv("USE_WGET", "").strip() == "1"
HTTP_TIMEOUT   = int(os.getenv("HTTP_TIMEOUT", "30"))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# --------------------------------------------------------------------------
# Helper: path management
# --------------------------------------------------------------------------

def _sanitize(name: str) -> str:
    """Bersihkan karakter tidak valid dari nama folder/file."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return cleaned.strip(". ")


def build_output_dir(system: str, title: str, base: Path = DOWNLOAD_DIR) -> Path:
    """
    Bangun path folder output.
    Struktur: <base>/<SYSTEM>/<game_title>/
    """
    return base / _sanitize(system) / _sanitize(title)


def _parse_filename(content_disposition: str) -> str:
    """Ambil filename dari header Content-Disposition."""
    m = re.search(r"filename\*=UTF-8''(.+)", content_disposition, re.IGNORECASE)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    m = re.search(r'filename=["\']?([^"\';\r\n]+)["\']?', content_disposition, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


# --------------------------------------------------------------------------
# Downloader: aria2c
# --------------------------------------------------------------------------

def _aria2c_download(
    url:     str,
    out_dir: Path,
    referer: str,
) -> Path:
    """Download dengan aria2c — auto filename dari Content-Disposition."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "aria2c",
        "--continue=true",
        f"--max-connection-per-server={ARIA2_CONN}",
        f"--dir={out_dir}",
        "--allow-overwrite=false",
        "--auto-file-renaming=false",
        f"--referer={referer}",
        f"--user-agent={_HEADERS['User-Agent']}",
        url,
    ]
    subprocess.run(cmd, check=True)
    return out_dir


# --------------------------------------------------------------------------
# Downloader: wget
# --------------------------------------------------------------------------

def _wget_download(
    url:     str,
    out_dir: Path,
    referer: str,
) -> Path:
    """Download dengan wget — auto filename dari Content-Disposition."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "wget",
        "--continue",
        "--content-disposition",
        f"--directory-prefix={out_dir}",
        f"--referer={referer}",
        f"--user-agent={_HEADERS['User-Agent']}",
        url,
    ]
    subprocess.run(cmd, check=True)
    return out_dir


# --------------------------------------------------------------------------
# Downloader: httpx streaming (fallback terakhir)
# --------------------------------------------------------------------------

def _httpx_stream_download(
    url:      str,
    out_dir:  Path,
    referer:  str,
    filename: str = "",
) -> Path:
    """Fallback streaming GET via httpx."""
    from rich.progress import (
        Progress,
        DownloadColumn,
        TransferSpeedColumn,
        TimeRemainingColumn,
        TextColumn,
        BarColumn,
    )

    headers = {**_HEADERS, "Referer": referer}
    out_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        headers=headers,
        follow_redirects=True,
        timeout=httpx.Timeout(HTTP_TIMEOUT, read=None),
    ) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()

            cd = resp.headers.get("content-disposition", "")
            final_filename = filename or _parse_filename(cd) or "download.bin"
            out_path = out_dir / final_filename
            total    = int(resp.headers.get("content-length", 0)) or None

            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task(f"⬇  {final_filename}", total=total)
                with open(out_path, "wb") as f:
                    for chunk in resp.iter_bytes(65536):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

    return out_path


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def download_game(
    download_host: str,
    media_id:      int,
    game_id:       int,
    system:        str,
    title:         str,
    alt:           int = 0,
    filename:      str = "",
) -> Path:
    """
    Download ROM/ISO dari Vimm's Lair via direct GET request.
    """
    out_dir = build_output_dir(system, title)

    # Memastikan format URL mirror benar
    url = f"{download_host.rstrip('/')}/?mediaId={media_id}"
    if alt > 0:
        url += f"&alt={alt}"

    referer = f"https://vimm.net/vault/{game_id}"

    # 1. Coba aria2c
    if not USE_WGET and shutil.which("aria2c"):
        _aria2c_download(url, out_dir, referer)
        return out_dir

    # 2. Coba wget
    if shutil.which("wget"):
        _wget_download(url, out_dir, referer)
        return out_dir

    # 3. Fallback httpx GET
    return _httpx_stream_download(url, out_dir, referer, filename)
