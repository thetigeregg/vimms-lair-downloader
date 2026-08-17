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
from typing import Callable

from vimms_downloader.config import Config, get_config

# Global download directory reference for backward compatibility
DOWNLOAD_DIR = get_config().download_dir

ARIA2_MAX_RETRIES = 5
ARIA2_RETRY_BASE_DELAY = 5  # seconds; doubles after each retry

OnLine = Callable[[str], None]


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


def _run(cmd: list[str], on_line: OnLine | None = None) -> tuple[int, str]:
    """
    Run `cmd`.

    If `on_line` is None, inherit stdio directly so the process's own live
    progress display (aria2c/7z/etc.) renders straight to the terminal, same
    as running it by hand.

    If `on_line` is given, stream stdout+stderr line-by-line via Popen
    instead — nothing goes to the real terminal. Every line is passed to
    `on_line` (which may write it to a log file, parse it for progress, both,
    or do nothing) and is also buffered so it can be attached to the
    returned CalledProcessError-style output on failure.
    """
    if on_line is None:
        result = subprocess.run(cmd)
        return result.returncode, ""

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines: list[str] = []
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n")
        lines.append(line)
        on_line(line)
    proc.wait()
    return proc.returncode, "\n".join(lines)


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
    on_line: OnLine | None = None,
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
    :param on_line: See _run(). When set, also lowers aria2c's summary
        interval to 1s so piped/non-tty output still gets frequent updates
        (its default 60s interval is meant for a live terminal, which
        already gets fast \\r-updated progress independent of the interval).
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
    ]
    if on_line is not None:
        cmd.append("--summary-interval=1")
    cmd.append(url)

    delay = ARIA2_RETRY_BASE_DELAY
    for attempt in range(1, ARIA2_MAX_RETRIES + 1):
        returncode, output = _run(cmd, on_line)
        if returncode == 0:
            return out_dir

        if attempt == ARIA2_MAX_RETRIES:
            raise subprocess.CalledProcessError(returncode, cmd, output=output)

        if on_line is not None:
            on_line(
                f"⚠  Download failed (aria2c exit code {returncode}), "
                f"retrying in {delay}s (attempt {attempt}/{ARIA2_MAX_RETRIES})..."
            )
        else:
            print(
                f"\n⚠  Download failed (aria2c exit code {returncode}), "
                f"retrying in {delay}s (attempt {attempt}/{ARIA2_MAX_RETRIES})...\n"
            )
        time.sleep(delay)
        delay *= 2


# --------------------------------------------------------------------------
# 7z archive extraction
# --------------------------------------------------------------------------

def find_downloaded_archive(out_dir: Path) -> Path | None:
    """Return the most recently modified .7z file in out_dir, if any."""
    archives = sorted(out_dir.glob("*.7z"), key=lambda p: p.stat().st_mtime, reverse=True)
    return archives[0] if archives else None


def extract_archive(archive_path: Path, remove_after: bool = False, on_line: OnLine | None = None) -> Path:
    """
    Extract a .7z archive into its containing directory using the `7z` CLI.

    :param archive_path: Path to the .7z archive.
    :param remove_after: Delete the archive once extraction succeeds.
    :param on_line: See _run().
    :return: The directory the archive was extracted into.
    """
    if shutil.which("7z") is None:
        raise RuntimeError("7z is not installed or not available on PATH.")

    out_dir = archive_path.parent
    cmd = ["7z", "x", str(archive_path), f"-o{out_dir}", "-y"]
    returncode, output = _run(cmd, on_line)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd, output=output)

    if remove_after:
        archive_path.unlink()

    return out_dir


# --------------------------------------------------------------------------
# extract-xiso (Xbox / Xbox 360 disc extraction)
# --------------------------------------------------------------------------

def find_iso(out_dir: Path) -> Path | None:
    """Return the most recently modified .iso file under out_dir, if any."""
    isos = sorted(out_dir.rglob("*.iso"), key=lambda p: p.stat().st_mtime, reverse=True)
    return isos[0] if isos else None


_XISO_FILE_COUNT_RE = re.compile(r"^(\d+)\s+files?\s+in\s+", re.IGNORECASE)


def count_xiso_files(iso_path: Path) -> int | None:
    """
    Best-effort count of files inside an Xbox/Xbox 360 .iso, via
    `extract-xiso -l`, for turning extract-xiso's per-file completion lines
    into an overall percentage. `-l`'s output ends with a summary line like
    "3 files in game.iso total 200026 bytes" — that's what's parsed here.
    Returns None (rather than raising) if extract-xiso is unavailable or its
    list output can't be parsed — the caller should treat that as "no
    percentage available", not an error.
    """
    if shutil.which("extract-xiso") is None:
        return None
    try:
        result = subprocess.run(
            ["extract-xiso", "-l", str(iso_path)],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    for line in result.stdout.splitlines():
        m = _XISO_FILE_COUNT_RE.match(line.strip())
        if m:
            return int(m.group(1))
    return None


def extract_xiso_contents(iso_path: Path, remove_after: bool = False, on_line: OnLine | None = None) -> Path:
    """
    Run extract-xiso on an Xbox/Xbox 360 .iso, extracting it to a sibling
    directory (named after the .iso, minus its extension).

    :param iso_path: Path to the .iso.
    :param remove_after: Delete the .iso once extraction succeeds.
    :param on_line: See _run().
    :return: The directory the .iso was extracted into.
    """
    if shutil.which("extract-xiso") is None:
        raise RuntimeError("extract-xiso is not installed or not available on PATH.")

    out_dir = iso_path.parent / iso_path.stem
    cmd = ["extract-xiso", "-x", "-d", str(out_dir), str(iso_path)]
    returncode, output = _run(cmd, on_line)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd, output=output)

    if remove_after:
        iso_path.unlink()

    return out_dir


# --------------------------------------------------------------------------
# ZArchive (.zar packing for Xenia Canary/Edge)
# --------------------------------------------------------------------------

def count_directory_files(source_dir: Path) -> int | None:
    """
    Count regular files under source_dir, for turning zarchive's per-file
    "Adding ..." lines into an overall percentage. Returns None if the
    directory can't be walked.
    """
    try:
        return sum(1 for p in source_dir.rglob("*") if p.is_file()) or None
    except OSError:
        return None


def pack_zarchive(source_dir: Path, remove_source: bool = False, on_line: OnLine | None = None) -> Path:
    """
    Pack a directory (the extract-xiso output) into a .zar archive using the
    `zarchive` CLI — Xenia Canary/Edge's compressed Xbox 360 format.

    :param source_dir: Directory to pack (the extract-xiso output folder).
    :param remove_source: Delete source_dir once packing succeeds.
    :param on_line: See _run().
    :return: Path to the resulting .zar file.
    """
    if shutil.which("zarchive") is None:
        raise RuntimeError("zarchive is not installed or not available on PATH.")

    output_file = source_dir.parent / f"{source_dir.name}.zar"
    if output_file.exists():
        output_file.unlink()  # zarchive refuses to run if the output already exists
    cmd = ["zarchive", str(source_dir), str(output_file)]
    returncode, output = _run(cmd, on_line)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd, output=output)

    if remove_source:
        shutil.rmtree(source_dir)

    return output_file
