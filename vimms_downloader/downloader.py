"""
Downloader module for Vimm's Lair using the Strategy pattern.

Supported download strategies (attempted in priority order):
1. Aria2Downloader: Multi-connection, resume support via `aria2c` CLI.
2. WgetDownloader: Resume & Content-Disposition support via `wget` CLI.
3. HttpxDownloader: Pure Python streaming download fallback with rich progress bar.
"""

from abc import ABC, abstractmethod
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote

import httpx

from vimms_downloader.config import Config, get_config

# Global download directory reference for backward compatibility
DOWNLOAD_DIR = get_config().download_dir


# --------------------------------------------------------------------------
# Path management & helpers
# --------------------------------------------------------------------------

def _sanitize(name: str) -> str:
    """Clean invalid characters from directory or file names."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return cleaned.strip(". ")


def build_output_dir(system: str, title: str, base: Path | None = None) -> Path:
    """
    Build target output directory path.
    Structure: <base>/<SYSTEM>/<game_title>/
    """
    base_path = base or get_config().download_dir
    return base_path / _sanitize(system) / _sanitize(title)


def _parse_filename(content_disposition: str) -> str:
    """Extract filename from Content-Disposition header."""
    m = re.search(r"filename\*=UTF-8''(.+)", content_disposition, re.IGNORECASE)
    if m:
        return unquote(m.group(1))
    m = re.search(r'filename=["\']?([^"\';\r\n]+)["\']?', content_disposition, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


# --------------------------------------------------------------------------
# Abstract Strategy
# --------------------------------------------------------------------------

class BaseDownloader(ABC):
    """Abstract base class for download strategy implementations."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether downloader dependencies and options allow execution."""
        pass

    @abstractmethod
    def download(
        self,
        url: str,
        out_dir: Path,
        referer: str,
        filename: str = "",
    ) -> Path:
        """
        Execute file download to target output directory.

        :param url: Direct download URL.
        :param out_dir: Destination directory path.
        :param referer: HTTP Referer header URL.
        :param filename: Optional suggested filename.
        :return: Path to downloaded file or containing directory.
        """
        pass


# --------------------------------------------------------------------------
# Strategy 1: Aria2
# --------------------------------------------------------------------------

class Aria2Downloader(BaseDownloader):
    """Download strategy using external `aria2c` CLI tool."""

    def is_available(self) -> bool:
        """Check if aria2c is installed on system and not disabled via config."""
        return not self.config.use_wget and shutil.which("aria2c") is not None

    def download(
        self,
        url: str,
        out_dir: Path,
        referer: str,
        filename: str = "",
    ) -> Path:
        """Download using aria2c with multi-connection and resume support."""
        if not self.is_available():
            raise RuntimeError("aria2c is not available or disabled by configuration.")

        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "aria2c",
            "--continue=true",
            f"--max-connection-per-server={self.config.aria2_connections}",
            f"--dir={out_dir}",
            "--allow-overwrite=false",
            "--auto-file-renaming=false",
            f"--referer={referer}",
            f"--user-agent={self.config.user_agent}",
            url,
        ]
        subprocess.run(cmd, check=True)
        return out_dir


# --------------------------------------------------------------------------
# Strategy 2: Wget
# --------------------------------------------------------------------------

class WgetDownloader(BaseDownloader):
    """Download strategy using external `wget` CLI tool."""

    def is_available(self) -> bool:
        """Check if wget is installed on system."""
        return shutil.which("wget") is not None

    def download(
        self,
        url: str,
        out_dir: Path,
        referer: str,
        filename: str = "",
    ) -> Path:
        """Download using wget with Content-Disposition auto-filename."""
        if not self.is_available():
            raise RuntimeError("wget executable is not available on system.")

        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "wget",
            "--continue",
            "--content-disposition",
            f"--directory-prefix={out_dir}",
            f"--referer={referer}",
            f"--user-agent={self.config.user_agent}",
            url,
        ]
        subprocess.run(cmd, check=True)
        return out_dir


# --------------------------------------------------------------------------
# Strategy 3: HTTPX (Fallback)
# --------------------------------------------------------------------------

class HttpxDownloader(BaseDownloader):
    """Pure Python fallback download strategy using httpx and rich progress."""

    def is_available(self) -> bool:
        """httpx is always available as a Python package dependency."""
        return True

    def download(
        self,
        url: str,
        out_dir: Path,
        referer: str,
        filename: str = "",
    ) -> Path:
        """Download using HTTP streaming via httpx with rich visual progress bar."""
        from rich.progress import (
            BarColumn,
            DownloadColumn,
            Progress,
            TextColumn,
            TimeRemainingColumn,
            TransferSpeedColumn,
        )

        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": referer,
        }
        out_dir.mkdir(parents=True, exist_ok=True)

        with httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(self.config.http_timeout, read=None),
        ) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()

                cd = resp.headers.get("content-disposition", "")
                final_filename = filename or _parse_filename(cd) or "download.bin"
                out_path = out_dir / final_filename
                total = int(resp.headers.get("content-length", 0)) or None

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
# Public API / Orchestrator
# --------------------------------------------------------------------------

def download_game(
    download_host: str,
    media_id: int,
    game_id: int,
    system: str,
    title: str,
    alt: int = 0,
    filename: str = "",
    config: Config | None = None,
) -> Path:
    """
    Download ROM/ISO from Vimm's Lair trying strategies in fallback order:
    1. Aria2Downloader
    2. WgetDownloader
    3. HttpxDownloader

    :param download_host: Base download URL host.
    :param media_id: Target media ID.
    :param game_id: Target game ID for referer URL.
    :param system: Console system code/name.
    :param title: Game title.
    :param alt: Format alt index (default: 0).
    :param filename: Optional filename hint.
    :param config: Optional Config instance override.
    :return: Path to downloaded file or destination directory.
    """
    cfg = config or get_config()
    out_dir = build_output_dir(system, title, base=cfg.download_dir)

    url = f"{download_host.rstrip('/')}/?mediaId={media_id}"
    if alt > 0:
        url += f"&alt={alt}"

    referer = f"https://vimm.net/vault/{game_id}"

    strategies: list[BaseDownloader] = [
        Aria2Downloader(config=cfg),
        WgetDownloader(config=cfg),
        HttpxDownloader(config=cfg),
    ]

    last_error: Exception | None = None
    for strategy in strategies:
        if strategy.is_available():
            try:
                return strategy.download(
                    url=url,
                    out_dir=out_dir,
                    referer=referer,
                    filename=filename,
                )
            except Exception as err:
                last_error = err
                continue

    if last_error:
        raise last_error
    raise RuntimeError("No available download strategy could execute the download.")
