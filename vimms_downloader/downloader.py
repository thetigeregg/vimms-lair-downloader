"""
Downloader module for Vimm's Lair — aria2c only.

Vimm's Lair enforces a single connection per IP and can intermittently
fail requests (e.g. HTTP 503) when a download is attempted too soon after
a previous one. Any failed attempt is retried with an increasing delay.
"""

import re
import shutil
import subprocess
import time
from pathlib import Path

from vimms_downloader.config import Config, get_config

# Global download directory reference for backward compatibility
DOWNLOAD_DIR = get_config().download_dir

ARIA2_MAX_RETRIES = 5
ARIA2_RETRY_BASE_DELAY = 5  # seconds; doubles after each retry


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


# --------------------------------------------------------------------------
# aria2c
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
    Download a ROM/ISO from Vimm's Lair using aria2c.

    Any failed attempt (non-zero exit code — timeouts, connection resets,
    HTTP 5xx/4xx responses, etc.) is retried with an increasing delay
    (doubling on each retry, up to ARIA2_MAX_RETRIES attempts).
    `--continue=true` means each retry resumes the partial file rather than
    restarting it.

    :param download_host: Base download URL host.
    :param media_id: Target media ID.
    :param game_id: Target game ID for referer URL.
    :param system: Console system code/name.
    :param title: Game title.
    :param alt: Format alt index (default: 0).
    :param filename: Unused — aria2c derives the filename from the server's
        Content-Disposition header. Kept for call-site compatibility.
    :param config: Optional Config instance override.
    :return: Path to the destination directory.
    """
    if shutil.which("aria2c") is None:
        raise RuntimeError("aria2c is not installed or not available on PATH.")

    cfg = config or get_config()
    out_dir = build_output_dir(system, title, base=cfg.download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    url = f"{download_host.rstrip('/')}/?mediaId={media_id}"
    if alt > 0:
        url += f"&alt={alt}"
    referer = f"https://vimm.net/vault/{game_id}"

    cmd = [
        "aria2c",
        "--continue=true",
        f"--max-connection-per-server={cfg.aria2_connections}",
        f"--dir={out_dir}",
        "--allow-overwrite=false",
        "--auto-file-renaming=false",
        f"--referer={referer}",
        f"--user-agent={cfg.user_agent}",
        url,
    ]

    delay = ARIA2_RETRY_BASE_DELAY
    for attempt in range(1, ARIA2_MAX_RETRIES + 1):
        result = subprocess.run(cmd)
        if result.returncode == 0:
            return out_dir

        if attempt == ARIA2_MAX_RETRIES:
            raise subprocess.CalledProcessError(result.returncode, cmd)

        print(
            f"\n⚠  Download failed (aria2c exit code {result.returncode}), "
            f"retrying in {delay}s (attempt {attempt}/{ARIA2_MAX_RETRIES})...\n"
        )
        time.sleep(delay)
        delay *= 2
