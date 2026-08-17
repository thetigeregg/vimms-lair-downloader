"""CLI entry point — Vimm's Lair Downloader."""

import contextlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

import click
import httpx
from rich.console import Console
from rich.table import Table

from vimms_downloader.config import Config, config
from vimms_downloader.downloader import (
    count_directory_files,
    count_xiso_files,
    download_game,
    extract_archive,
    extract_xiso_contents,
    find_downloaded_archive,
    find_iso,
    pack_zarchive,
)
from vimms_downloader.models import SYSTEMS
from vimms_downloader.progress_parsers import (
    is_extract_xiso_file_line,
    is_zarchive_adding_line,
    parse_7z_line,
    parse_aria2c_line,
    percent_from_file_count,
)
from vimms_downloader.scraper import VimmScraper
from vimms_downloader.status import (
    PHASE_LABELS,
    PHASE_ORDER,
    StatusBoard,
    load_snapshot,
    render_table_lines,
)

console = Console()


# --------------------------------------------------------------------------
# CLI group
# --------------------------------------------------------------------------

@click.group()
@click.version_option(package_name="vimms-lair-downloader")
def cli() -> None:
    """🎮 Vimm's Lair Downloader — ROM/ISO downloader CLI.

    \b
    Example workflow:
      vimms list-systems
      vimms search "mario" -s NES
      vimms info 17874
      vimms download 17874 8342 12345 --latest --wait 5
    """


# --------------------------------------------------------------------------
# list-systems
# --------------------------------------------------------------------------

@cli.command("list-systems")
def cmd_list_systems() -> None:
    """Show all systems available on Vimm's Lair."""
    table = Table(title="Vimm's Lair Systems", show_lines=False, expand=False)
    table.add_column("URL Code", style="cyan", no_wrap=True)
    table.add_column("System Name", style="green")

    for code, name in sorted(SYSTEMS.items(), key=lambda x: x[1]):
        table.add_row(code, name)

    console.print(table)
    console.print(f"[dim]Total: {len(SYSTEMS)} systems[/dim]")


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

@cli.command("search")
@click.argument("query")
@click.option(
    "--system", "-s",
    default=None,
    metavar="CODE",
    help="Filter by system code (NES, PS1, SNES, ...).",
)
@click.option(
    "--limit", "-l",
    default=20,
    type=int,
    show_default=True,
    help="Limit the number of results shown.",
)
def cmd_search(query: str, system: Optional[str], limit: int) -> None:
    """Search for games in the vault.

    \b
    Examples:
      vimms search "mario"
      vimms search "zelda" -s N64 -l 10
    """
    try:
        with VimmScraper() as scraper:
            with console.status(f"Searching [bold]{query}[/bold]..."):
                results = scraper.search(query, system=system)
    except httpx.HTTPError as e:
        console.print(f"[red]❌  Failed to connect to Vimm's Lair: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]❌  Error: {e}[/red]")
        raise SystemExit(1)

    if not results:
        console.print("[red]No results found.[/red]")
        return

    shown = results[:limit]
    table = Table(
        title=f"Search results: '[bold]{query}[/bold]'"
              + (f" — system: {system}" if system else ""),
        show_lines=False,
    )
    table.add_column("ID", style="cyan", justify="right", no_wrap=True)
    table.add_column("Title", style="green")
    table.add_column("URL", style="dim")

    for r in shown:
        table.add_row(str(r["game_id"]), r["title"], r["url"])

    console.print(table)
    if len(results) > limit:
        console.print(
            f"[dim]Showing {limit} of {len(results)} results. "
            f"Use --limit to see more.[/dim]"
        )


# --------------------------------------------------------------------------
# browse
# --------------------------------------------------------------------------

@cli.command("browse")
@click.argument("system")
@click.option(
    "--letter", "-l",
    default=None,
    metavar="A-Z",
    help="Filter by the title's starting letter.",
)
@click.option(
    "--limit",
    default=50,
    type=int,
    show_default=True,
    help="Limit the number of rows shown.",
)
def cmd_browse(system: str, letter: Optional[str], limit: int) -> None:
    """Browse the game list for a system.

    \b
    Examples:
      vimms browse SNES
      vimms browse NES -l M
      vimms browse PS1 --limit 100
    """
    label = f"{system}" + (f" / {letter.upper()}" if letter else "")

    try:
        with VimmScraper() as scraper:
            with console.status(f"Browsing [bold]{label}[/bold]..."):
                results = scraper.browse(system, letter=letter)
    except httpx.HTTPError as e:
        console.print(f"[red]❌  Failed to connect to Vimm's Lair: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]❌  Error: {e}[/red]")
        raise SystemExit(1)

    if not results:
        console.print("[red]No games found.[/red]")
        return

    shown = results[:limit]
    table = Table(title=f"Game List — {label}", show_lines=False)
    table.add_column("ID", style="cyan", justify="right", no_wrap=True)
    table.add_column("Title", style="green")

    for r in shown:
        table.add_row(str(r["game_id"]), r["title"])

    console.print(table)
    if len(results) > limit:
        console.print(
            f"[dim]Showing {limit} of {len(results)} games. "
            f"Use --limit to see more.[/dim]"
        )


# --------------------------------------------------------------------------
# info
# --------------------------------------------------------------------------

@cli.command("info")
@click.argument("game_id", type=int)
def cmd_info(game_id: int) -> None:
    """Show details for a single game by ID.

    \b
    Example:
      vimms info 17874
    """
    try:
        with VimmScraper() as scraper:
            with console.status(f"Fetching game [bold]{game_id}[/bold]..."):
                d = scraper.get_game_detail(game_id)
    except httpx.HTTPError as e:
        console.print(f"[red]❌  Failed to connect to Vimm's Lair: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]❌  Error: {e}[/red]")
        raise SystemExit(1)

    if not d.get("title") and not d.get("media_id"):
        console.print(f"[red]Game ID {game_id} not found.[/red]")
        return

    # Header
    console.print()
    console.print(f"[bold green]{d['title']}[/bold green]  "
                  f"[dim]{d.get('filename', '')}[/dim]")
    console.print()

    # Formats & Versions text info
    fmt_names = [f["name"] for f in d.get("formats", [])]
    fmt_str = ", ".join(fmt_names) if fmt_names else None
    ver_str = ", ".join(d.get("versions", [])) if d.get("versions") else None

    rows = [
        ("Game ID",  str(d["game_id"])),
        ("Media ID", str(d["media_id"]) if d.get("media_id") else "[red]N/A[/red]"),
        ("System",   d.get("system") or ""),
        ("Year",     d.get("year") or ""),
        ("Players",  d.get("players") or ""),
        ("Size",     d.get("file_size") or ""),
        ("Format",   fmt_str),
        ("Version",  ver_str),
        ("URL",      d["url"]),
    ]
    for label, val in rows:
        if val:
            console.print(f"  [dim]{label:<10}[/dim] {val}")

    console.print()
    if d.get("media_id"):
        cmd_suggest = f"vimms download {game_id}"
        if d.get("versions"):
            cmd_suggest += f" --version {d['versions'][-1]}"
        if d.get("formats"):
            cmd_suggest += f" --format {d['formats'][0]['name'].replace('.', '')}"
        console.print(f"[dim]To download: [bold]{cmd_suggest}[/bold][/dim]")
    else:
        console.print("[yellow]⚠  Download not available for this game.[/yellow]")


# --------------------------------------------------------------------------
# download — reporters
# --------------------------------------------------------------------------
#
# _download_stage()/_postprocess_stage() report through a Reporter instead
# of calling `console` directly, so the same pipeline logic drives two very
# different outputs:
#   - ConsoleReporter: today's plain console.print() output, used when
#     there's no real terminal (or fzf isn't available) to run the live
#     table in.
#   - StatusBoardReporter: updates a StatusBoard + per-item log files
#     instead, used for the fzf-driven live table.

class Reporter(Protocol):
    def status(self, game_id: int, message: str): ...
    def download_info(self, game_id: int, title: str, system: str, version: str,
                       fmt: str, media_id, output_dir: Path) -> None: ...
    def download_done(self, game_id: int, out_path: Path) -> None: ...
    def download_failed(self, game_id: int, message: str) -> None: ...
    def phase(self, game_id: int, phase: str, message: str): ...
    def phase_done(self, game_id: int, phase: str, message: str) -> None: ...
    def phase_failed(self, game_id: int, phase: str, message: str) -> None: ...
    def phase_warn(self, game_id: int, phase: str, message: str) -> None: ...
    def set_total_files(self, game_id: int, phase: str, total: Optional[int]) -> None: ...
    def on_line(self, game_id: int, phase: str) -> Optional[Callable[[str], None]]: ...


class ConsoleReporter:
    """Reproduces the existing plain console.print() output, unchanged."""

    def __init__(self, pipelined: bool = False) -> None:
        # True when running concurrently with another item's download in the
        # pipelined queue — captures post-processing subprocess output
        # instead of streaming it live, to avoid interleaving with aria2c's
        # live progress display on the same terminal. aria2c's own download
        # output always stays live regardless (see on_line()).
        self.pipelined = pipelined

    def status(self, game_id: int, message: str):
        return console.status(message)

    def download_info(self, game_id, title, system, version, fmt, media_id, output_dir) -> None:
        console.print()
        console.print(f"[bold]🎮 {title}[/bold]")
        console.print(f"  System  : {system}")
        console.print(f"  Version : {version}")
        console.print(f"  Format  : {fmt}")
        console.print(f"  Media ID: {media_id}")
        console.print(f"  Output  : {output_dir}/")
        console.print()

    def download_done(self, game_id, out_path) -> None:
        console.print(f"\n[bold green]✅  Download complete:[/bold green] {out_path}")

    def download_failed(self, game_id, message) -> None:
        console.print(f"[red]❌  {message}[/red]")

    def phase(self, game_id, phase, message):
        if phase == "download":
            return contextlib.nullcontext()  # aria2c shows its own progress
        label = f"[dim][{game_id}][/dim] "
        return console.status(f"{label}{message}")

    def phase_done(self, game_id, phase, message) -> None:
        label = f"[dim][{game_id}][/dim] "
        console.print(f"{label}[bold green]✅  {message}[/bold green]")

    def phase_failed(self, game_id, phase, message) -> None:
        label = f"[dim][{game_id}][/dim] "
        console.print(f"{label}[red]❌  {message}[/red]")

    def phase_warn(self, game_id, phase, message) -> None:
        label = f"[dim][{game_id}][/dim] "
        console.print(f"{label}[yellow]⚠  {message}[/yellow]")

    def set_total_files(self, game_id, phase, total) -> None:
        pass  # not used in the plain-text path

    def on_line(self, game_id, phase):
        if phase == "download":
            return None  # aria2c always stays live-inherited
        return (lambda line: None) if self.pipelined else None


class StatusBoardReporter:
    """Reports into a StatusBoard + per-item log files, for the fzf TUI."""

    def __init__(self, board: StatusBoard, log_dir: Path) -> None:
        self.board = board
        self.log_dir = log_dir
        self._log_files: dict[int, object] = {}
        self._file_counts: dict[tuple[int, str], int] = {}
        self._file_totals: dict[tuple[int, str], Optional[int]] = {}

    def _log(self, game_id: int, text: str) -> None:
        f = self._log_files.get(game_id)
        if f is None:
            f = (self.log_dir / f"{game_id}.log").open("a", buffering=1)
            self._log_files[game_id] = f
        f.write(text + "\n")

    def status(self, game_id, message):
        self._log(game_id, f"... {message}")
        return contextlib.nullcontext()

    def download_info(self, game_id, title, system, version, fmt, media_id, output_dir) -> None:
        self.board.set_title(game_id, title)
        self._log(game_id, f"=== {title} ===")
        self._log(game_id, f"System: {system}  Version: {version}  Format: {fmt}  Media ID: {media_id}")
        self._log(game_id, f"Output: {output_dir}")

    def download_done(self, game_id, out_path) -> None:
        self.board.update_phase(game_id, "download", state="done", percent=100, finished_at=time.time())
        self._log(game_id, f"Download complete: {out_path}")

    def download_failed(self, game_id, message) -> None:
        self.board.update_phase(game_id, "download", state="failed", finished_at=time.time())
        self._log(game_id, f"ERROR: {message}")

    @contextlib.contextmanager
    def phase(self, game_id, phase, message):
        self.board.update_phase(game_id, phase, state="running", started_at=time.time())
        self._log(game_id, f"=== [{phase}] {message} ===")
        yield

    def phase_done(self, game_id, phase, message) -> None:
        self.board.update_phase(game_id, phase, state="done", percent=100, finished_at=time.time())
        self._log(game_id, message)

    def phase_failed(self, game_id, phase, message) -> None:
        self.board.update_phase(game_id, phase, state="failed", finished_at=time.time())
        self._log(game_id, f"ERROR: {message}")

    def phase_warn(self, game_id, phase, message) -> None:
        self.board.update_phase(game_id, phase, state="failed", finished_at=time.time())
        self._log(game_id, f"WARNING: {message}")

    def set_total_files(self, game_id, phase, total) -> None:
        self._file_totals[(game_id, phase)] = total

    def on_line(self, game_id, phase):
        def _handler(line: str) -> None:
            self._log(game_id, line)
            percent = self._parse_progress(game_id, phase, line)
            if percent is not None:
                self.board.update_phase(game_id, phase, state="running", percent=percent)
        return _handler

    def _parse_progress(self, game_id, phase, line) -> Optional[int]:
        if phase == "download":
            return parse_aria2c_line(line)
        if phase == "7z":
            return parse_7z_line(line)
        if phase in ("extract-xiso", "zar"):
            is_file_line = is_extract_xiso_file_line(line) if phase == "extract-xiso" else is_zarchive_adding_line(line)
            if not is_file_line:
                return None
            key = (game_id, phase)
            self._file_counts[key] = self._file_counts.get(key, 0) + 1
            return percent_from_file_count(self._file_counts[key], self._file_totals.get(key))
        return None

    def close(self, game_id: int) -> None:
        f = self._log_files.pop(game_id, None)
        if f is not None:
            f.close()


# --------------------------------------------------------------------------
# download — pipeline
# --------------------------------------------------------------------------

@dataclass
class DownloadedItem:
    """Info handed off from the download stage to the post-processing stage."""
    game_id: int
    system: str
    title: str
    base_dir: Path


def _download_stage(
    scraper: VimmScraper,
    game_id: int,
    format: Optional[str],
    version: Optional[str],
    latest: bool,
    base_dir: Path,
    output_dir: Optional[str],
    reporter: Reporter,
) -> Optional[DownloadedItem]:
    """Fetch details and run the aria2c download. Returns None on failure."""
    # --- Fetch game details ---
    try:
        with reporter.status(game_id, f"Fetching details for game [bold]{game_id}[/bold]..."):
            detail = scraper.get_game_detail(game_id)
    except httpx.HTTPError as e:
        reporter.download_failed(game_id, f"Failed to connect to Vimm's Lair: {e}")
        return None
    except Exception as e:
        reporter.download_failed(game_id, f"Error fetching details: {e}")
        return None

    if not detail.get("media_id"):
        reporter.download_failed(game_id, f"No mediaId found for game {game_id}. Download not available.")
        return None

    # --- Determine mediaId based on version ---
    media_list = detail.get("media_list", [])
    target_media = None

    if version and media_list:
        for m in media_list:
            if m.get("Version") == version:
                target_media = m
                break
        if not target_media:
            avail_ver = ", ".join(detail.get("versions", []))
            reporter.download_failed(game_id, f"Version '{version}' not found. Available options: {avail_ver}")
            return None

    if latest and detail.get("versions"):
        newest_version = detail["versions"][-1]
        for m in media_list:
            if m.get("Version") == newest_version:
                target_media = m
                break

    if not target_media:
        # Look up the default mediaId record
        for m in media_list:
            if m.get("ID") == detail["media_id"]:
                target_media = m
                break
        if not target_media:
            target_media = {"ID": detail["media_id"], "Version": "Default"}

    media_id = target_media["ID"]
    actual_version = target_media.get("Version", "Default")

    # --- Determine format (alt parameter) ---
    alt = 0
    formats = detail.get("formats", [])
    selected_format_name = "Default"

    if format and formats:
        clean_fmt = format.lower().strip(".")
        for fmt in formats:
            if clean_fmt in fmt["name"].lower():
                alt = fmt["value"]
                selected_format_name = fmt["name"]
                break
        else:
            avail_fmt = ", ".join([f["name"] for f in formats])
            reporter.download_failed(game_id, f"Format '{format}' not found. Available options: {avail_fmt}")
            return None
    elif formats:
        selected_format_name = formats[0]["name"]
        alt = formats[0]["value"]

    system = detail.get("system") or "Unknown"
    title = detail.get("title") or f"game_{game_id}"
    filename = detail.get("filename") or ""

    reporter.download_info(
        game_id, title, system, actual_version, selected_format_name, media_id,
        base_dir / system / title,
    )

    # --- Run the download ---
    try:
        cfg = Config(download_dir=base_dir) if output_dir else None
        with reporter.phase(game_id, "download", "Downloading..."):
            out_path = download_game(
                download_host=detail["download_host"],
                media_id=media_id,
                game_id=game_id,
                system=system,
                title=title,
                alt=alt,
                filename=filename,
                config=cfg,
                on_line=reporter.on_line(game_id, "download"),
            )
        reporter.download_done(game_id, out_path)
    except subprocess.CalledProcessError as e:
        reporter.download_failed(game_id, f"Download process failed (exit code {e.returncode}).")
        return None
    except Exception as e:
        reporter.download_failed(game_id, f"Error: {e}")
        return None

    return DownloadedItem(game_id=game_id, system=system, title=title, base_dir=base_dir)


def _postprocess_stage(
    item: DownloadedItem,
    reporter: Reporter,
    extract: bool = False,
    delete_archive: bool = False,
    extract_xiso: bool = False,
    delete_iso: bool = False,
    zar: bool = False,
    delete_xex_folder: bool = False,
) -> bool:
    """Run the extract/extract-xiso/zar chain for an already-downloaded game.
    Returns True on success, False on failure."""
    game_dir = item.base_dir / item.system / item.title

    if extract:
        archive = find_downloaded_archive(game_dir)
        if archive is None:
            reporter.phase_warn(item.game_id, "7z", "--extract requested but no .7z archive was found.")
            return False
        try:
            with reporter.phase(item.game_id, "7z", f"Extracting {archive.name}..."):
                extract_archive(archive, remove_after=delete_archive, on_line=reporter.on_line(item.game_id, "7z"))
            reporter.phase_done(item.game_id, "7z", f"Extracted: {archive.parent}")
        except subprocess.CalledProcessError as e:
            reporter.phase_failed(item.game_id, "7z", f"Extraction failed (exit code {e.returncode}).")
            return False
        except Exception as e:
            reporter.phase_failed(item.game_id, "7z", f"Extraction error: {e}")
            return False

    if extract_xiso:
        iso_path = find_iso(game_dir)
        if iso_path is None:
            reporter.phase_warn(item.game_id, "extract-xiso", "--extract-xiso requested but no .iso file was found.")
            return False
        reporter.set_total_files(item.game_id, "extract-xiso", count_xiso_files(iso_path))
        try:
            with reporter.phase(item.game_id, "extract-xiso", f"Running extract-xiso on {iso_path.name}..."):
                extracted_dir = extract_xiso_contents(
                    iso_path, remove_after=delete_iso, on_line=reporter.on_line(item.game_id, "extract-xiso"),
                )
            reporter.phase_done(item.game_id, "extract-xiso", f"extract-xiso complete: {extracted_dir}")
        except subprocess.CalledProcessError as e:
            reporter.phase_failed(item.game_id, "extract-xiso", f"extract-xiso failed (exit code {e.returncode}).")
            return False
        except Exception as e:
            reporter.phase_failed(item.game_id, "extract-xiso", f"extract-xiso error: {e}")
            return False

        if zar:
            reporter.set_total_files(item.game_id, "zar", count_directory_files(extracted_dir))
            try:
                with reporter.phase(item.game_id, "zar", f"Packing {extracted_dir.name} into .zar..."):
                    zar_path = pack_zarchive(
                        extracted_dir, remove_source=delete_xex_folder, on_line=reporter.on_line(item.game_id, "zar"),
                    )
                reporter.phase_done(item.game_id, "zar", f"Packed: {zar_path}")
            except subprocess.CalledProcessError as e:
                reporter.phase_failed(item.game_id, "zar", f"zarchive packing failed (exit code {e.returncode}).")
                return False
            except Exception as e:
                reporter.phase_failed(item.game_id, "zar", f"zarchive error: {e}")
                return False

    return True


def _run_queue(
    game_ids: tuple[int, ...],
    format: Optional[str],
    version: Optional[str],
    latest: bool,
    wait: int,
    base_dir: Path,
    output_dir: Optional[str],
    extract: bool,
    delete_archive: bool,
    extract_xiso: bool,
    delete_iso: bool,
    zar: bool,
    delete_xex_folder: bool,
    reporter: Reporter,
) -> list[bool]:
    """
    Run the download queue against `reporter`. Post-processing
    (extract/extract-xiso/zar) is CPU/disk-bound, unlike the network-bound,
    rate-limited download step. When there's post-processing work and more
    than one ID, downloads and post-processing run in two independently
    paced lanes: downloads stay strictly sequential (Vimm's single-connection
    limit + --wait), post-processing also stays strictly sequential (one
    item at a time, in download-completion order), but the two lanes run
    concurrently instead of blocking each other.
    """
    do_postprocess = extract
    use_pipeline = do_postprocess and len(game_ids) > 1
    results: list[bool] = [False] * len(game_ids)

    with VimmScraper() as scraper:
        if not use_pipeline:
            for i, game_id in enumerate(game_ids):
                if i > 0 and wait > 0:
                    time.sleep(wait)
                item = _download_stage(scraper, game_id, format, version, latest, base_dir, output_dir, reporter)
                ok = item is not None
                if ok and do_postprocess:
                    ok = _postprocess_stage(
                        item, reporter, extract=extract, delete_archive=delete_archive,
                        extract_xiso=extract_xiso, delete_iso=delete_iso,
                        zar=zar, delete_xex_folder=delete_xex_folder,
                    )
                results[i] = ok
        else:
            with ThreadPoolExecutor(max_workers=1) as post_executor:
                futures: dict[int, "Future[bool]"] = {}
                for i, game_id in enumerate(game_ids):
                    if i > 0 and wait > 0:
                        time.sleep(wait)
                    item = _download_stage(scraper, game_id, format, version, latest, base_dir, output_dir, reporter)
                    if item is None:
                        results[i] = False
                        continue
                    futures[i] = post_executor.submit(
                        _postprocess_stage, item, reporter, extract, delete_archive,
                        extract_xiso, delete_iso, zar, delete_xex_folder,
                    )
                for i, future in futures.items():
                    try:
                        results[i] = future.result()
                    except Exception as e:
                        console.print(f"[red]❌  Post-processing error: {e}[/red]")
                        results[i] = False

    return results


def _active_phases(extract: bool, extract_xiso: bool, zar: bool) -> list[str]:
    phases = ["download"]
    if extract:
        phases.append("7z")
    if extract_xiso:
        phases.append("extract-xiso")
    if zar:
        phases.append("zar")
    return phases


def _run_tui(
    game_ids: tuple[int, ...],
    format: Optional[str],
    version: Optional[str],
    latest: bool,
    wait: int,
    base_dir: Path,
    output_dir: Optional[str],
    extract: bool,
    delete_archive: bool,
    extract_xiso: bool,
    delete_iso: bool,
    zar: bool,
    delete_xex_folder: bool,
) -> list[bool]:
    """
    Run the queue with the live fzf table: the main thread runs fzf in the
    foreground (it needs the real terminal); a background thread runs the
    actual download/post-process pipeline and reports into a StatusBoard,
    which fzf polls every second via `every(1):reload-sync`. Closing fzf
    early does not cancel the pipeline — it keeps running to completion in
    the background, and the final summary prints once it's done.
    """
    log_dir = Path(tempfile.mkdtemp(prefix="vimms-logs-"))
    status_path = log_dir / "status.json"
    board = StatusBoard(status_path)
    reporter = StatusBoardReporter(board, log_dir)

    active_phases = _active_phases(extract, extract_xiso, zar)
    for game_id in game_ids:
        item_log_path = log_dir / f"{game_id}.log"
        item_log_path.touch()  # exists before fzf's preview (tail -F) ever runs
        board.add_item(game_id, title=f"#{game_id}", log_path=item_log_path, active_phases=active_phases)

    results: list[bool] = []

    def _driver() -> None:
        nonlocal results
        results = _run_queue(
            game_ids, format, version, latest, wait, base_dir, output_dir,
            extract, delete_archive, extract_xiso, delete_iso, zar, delete_xex_folder,
            reporter,
        )

    driver_thread = threading.Thread(target=_driver, daemon=False)
    driver_thread.start()

    header = "Title".ljust(30) + "  " + "  ".join(PHASE_LABELS[p].ljust(18) for p in PHASE_ORDER)
    render_status_cmd = f"vimms _render-status {shlex.quote(str(status_path))}"
    fzf_cmd = [
        "fzf",
        "--ansi",
        "--track",
        "--id-nth", "1",
        "--with-nth", "3..",
        "--delimiter", "\t",
        "--header", header,
        "--bind", f"start,every(1):reload-sync:{render_status_cmd}",
        "--preview", 'tail -n +1 -F "{2}"',
        "--preview-window", "right,60%",
    ]
    try:
        subprocess.run(fzf_cmd)
    except KeyboardInterrupt:
        pass

    if driver_thread.is_alive():
        console.print("[dim]Finishing remaining downloads in the background...[/dim]")
    driver_thread.join()

    return results


@cli.command("download")
@click.argument("game_ids", type=int, nargs=-1, required=True)
@click.option(
    "--format", "-f",
    default=None,
    help="Desired disk/ROM format (e.g. wbfs, rvz, iso).",
)
@click.option(
    "--version", "-v",
    default=None,
    help="Desired game version (e.g. 1.0, 1.1, 1.2). Only valid for a single game ID.",
)
@click.option(
    "--latest", "-L",
    is_flag=True,
    default=False,
    help="Always select the newest available version (ignores --version).",
)
@click.option(
    "--wait", "-w",
    default=0,
    type=int,
    show_default=True,
    help="Seconds to wait between downloads when queuing multiple IDs.",
)
@click.option(
    "--extract", "-x",
    is_flag=True,
    default=False,
    help="Extract the downloaded .7z archive after downloading.",
)
@click.option(
    "--delete-archive",
    is_flag=True,
    default=False,
    help="Delete the .7z archive after successful extraction (requires --extract).",
)
@click.option(
    "--extract-xiso", "-X",
    is_flag=True,
    default=False,
    help="Run extract-xiso on the extracted .iso, for Xbox/Xbox 360 games (requires --extract).",
)
@click.option(
    "--delete-iso",
    is_flag=True,
    default=False,
    help="Delete the .iso after successful extract-xiso extraction (requires --extract-xiso).",
)
@click.option(
    "--zar", "-z",
    is_flag=True,
    default=False,
    help="Pack the extract-xiso output into a .zar archive for Xenia (requires --extract-xiso).",
)
@click.option(
    "--delete-xex-folder",
    is_flag=True,
    default=False,
    help="Delete the extracted folder after successful .zar packing (requires --zar).",
)
@click.option(
    "--output-dir", "-o",
    default=None,
    metavar="PATH",
    help="Override the output directory (defaults to DOWNLOAD_DIR from config/.env).",
)
def cmd_download(
    game_ids: tuple[int, ...],
    format: Optional[str],
    version: Optional[str],
    latest: bool,
    wait: int,
    extract: bool,
    delete_archive: bool,
    extract_xiso: bool,
    delete_iso: bool,
    zar: bool,
    delete_xex_folder: bool,
    output_dir: Optional[str],
) -> None:
    """Download one or more ROMs/ISOs by game ID.

    \b
    File is saved to: DOWNLOAD_DIR/<SYSTEM>/<title>/
    In a real terminal (with fzf installed), this shows a live table with
    one row per game and one column per phase — move the cursor to a row to
    see that item's full log. Non-interactive runs (piped output, scripts,
    docker exec -T) fall back to plain scrolling output.
    Examples:
      vimms download 17874 --format rvz --latest --extract
      vimms download 17874 8342 12345 --latest --wait 5
      vimms download 15323 --latest --format xiso.iso --extract --extract-xiso --zar
    """
    if latest and version:
        console.print("[red]❌  --latest and --version are mutually exclusive.[/red]")
        raise SystemExit(1)

    if version and len(game_ids) > 1:
        console.print(
            "[red]❌  --version can't be used with multiple game IDs — each game has "
            "its own version numbering. Use --latest instead, or download one ID at a time.[/red]"
        )
        raise SystemExit(1)

    if delete_archive and not extract:
        console.print("[red]❌  --delete-archive requires --extract.[/red]")
        raise SystemExit(1)

    if extract_xiso and not extract:
        console.print("[red]❌  --extract-xiso requires --extract.[/red]")
        raise SystemExit(1)

    if delete_iso and not extract_xiso:
        console.print("[red]❌  --delete-iso requires --extract-xiso.[/red]")
        raise SystemExit(1)

    if zar and not extract_xiso:
        console.print("[red]❌  --zar requires --extract-xiso.[/red]")
        raise SystemExit(1)

    if delete_xex_folder and not zar:
        console.print("[red]❌  --delete-xex-folder requires --zar.[/red]")
        raise SystemExit(1)

    base_dir = Path(output_dir).expanduser() if output_dir else config.download_dir
    interactive = sys.stdin.isatty() and sys.stdout.isatty()

    if interactive:
        if shutil.which("fzf") is None:
            console.print(
                "[red]❌  fzf is required for the live download table but is not installed "
                "or not on PATH.[/red]"
            )
            raise SystemExit(1)
        results = _run_tui(
            game_ids, format, version, latest, wait, base_dir, output_dir,
            extract, delete_archive, extract_xiso, delete_iso, zar, delete_xex_folder,
        )
    else:
        reporter = ConsoleReporter(pipelined=extract and len(game_ids) > 1)
        results = _run_queue(
            game_ids, format, version, latest, wait, base_dir, output_dir,
            extract, delete_archive, extract_xiso, delete_iso, zar, delete_xex_folder,
            reporter,
        )

    if len(game_ids) > 1:
        succeeded = sum(results)
        console.print(f"\n[bold]Queue complete:[/bold] {succeeded}/{len(game_ids)} succeeded.")
        failed_ids = [gid for gid, ok in zip(game_ids, results) if not ok]
        if failed_ids:
            console.print(f"[red]Failed IDs:[/red] {' '.join(str(gid) for gid in failed_ids)}")

    if not all(results):
        raise SystemExit(1)


@cli.command("_render-status", hidden=True)
@click.argument("status_path", type=click.Path())
def cmd_render_status(status_path: str) -> None:
    """Internal: print fzf list lines from a StatusBoard JSON snapshot."""
    path = Path(status_path)
    if not path.exists():
        return
    try:
        items = load_snapshot(path)
    except Exception:
        return
    for line in render_table_lines(items):
        click.echo(line)


if __name__ == "__main__":
    cli()
