"""
Downloader module for Vimm's Lair — aria2c only.

Vimm's Lair enforces a single connection per IP and returns HTTP 503 when a
download is attempted too soon after a previous one. Failed downloads are
retried with an increasing delay (doubling each time) whenever a 503 is
detected in aria2c's log.
"""

import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from vimms_downloader.config import Config, get_config

# Global download directory reference for backward compatibility
DOWNLOAD_DIR = get_config().download_dir

ARIA2_MAX_RETRIES = 5
ARIA2_RETRY_BASE_DELAY = 5  # seconds; doubles after each 503 retry


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

def _run_aria2c(cmd: list[str], log_path: Path) -> tuple[int, str]:
    """
    Run aria2c, inheriting the parent's stdio so its live progress display
    still works normally, and return its exit code plus the contents of its
    log file (used to detect HTTP 503 responses for retry purposes).
    """
    log_path.unlink(missing_ok=True)
    result = subprocess.run(cmd)
    log_text = log_path.read_text(errors="replace") if log_path.exists() else ""
    return result.returncode, log_text


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

    Retries with an increasing delay (doubling on each retry, up to
    ARIA2_MAX_RETRIES attempts) whenever aria2c reports an HTTP 503 from the
    mirror — Vimm's Lair only allows one connection per IP and briefly
    rejects requests made too soon after a prior download. `--continue=true`
    means each retry resumes the partial file rather than restarting it.

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

    log_path = Path(tempfile.gettempdir()) / f"vimms-aria2c-{media_id}.log"
    cmd = [
        "aria2c",
        "--continue=true",
        f"--max-connection-per-server={cfg.aria2_connections}",
        f"--dir={out_dir}",
        "--allow-overwrite=false",
        "--auto-file-renaming=false",
        f"--referer={referer}",
        f"--user-agent={cfg.user_agent}",
        f"--log={log_path}",
        "--log-level=notice",
        url,
    ]

    delay = ARIA2_RETRY_BASE_DELAY
    try:
        for attempt in range(1, ARIA2_MAX_RETRIES + 1):
            returncode, log_text = _run_aria2c(cmd, log_path)
            if returncode == 0:
                return out_dir

            if "status=503" not in log_text or attempt == ARIA2_MAX_RETRIES:
                raise subprocess.CalledProcessError(returncode, cmd, output=log_text)

            print(
                f"\n⚠  Vimm's Lair returned HTTP 503 (rate limited), "
                f"retrying in {delay}s (attempt {attempt}/{ARIA2_MAX_RETRIES})...\n"
            )
            time.sleep(delay)
            delay *= 2
    finally:
        log_path.unlink(missing_ok=True)
