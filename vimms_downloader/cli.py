"""CLI entry point — Vimm's Lair Downloader."""

import subprocess
import time
from pathlib import Path
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.table import Table

from vimms_downloader.config import Config, config
from vimms_downloader.downloader import download_game, extract_archive, find_downloaded_archive
from vimms_downloader.models import SYSTEMS
from vimms_downloader.scraper import VimmScraper

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
# download
# --------------------------------------------------------------------------

def _download_one(
    scraper: VimmScraper,
    game_id: int,
    format: Optional[str],
    version: Optional[str],
    latest: bool,
    base_dir: Path,
    output_dir: Optional[str],
    extract: bool = False,
    delete_archive: bool = False,
) -> bool:
    """Download a single game. Returns True on success, False on failure."""
    # --- Fetch game details ---
    try:
        with console.status(f"Fetching details for game [bold]{game_id}[/bold]..."):
            detail = scraper.get_game_detail(game_id)
    except httpx.HTTPError as e:
        console.print(f"[red]❌  Failed to connect to Vimm's Lair: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]❌  Error fetching details: {e}[/red]")
        return False

    if not detail.get("media_id"):
        console.print(
            f"[red]❌  No mediaId found for game {game_id}. "
            f"Download not available.[/red]"
        )
        return False

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
            console.print(f"[red]❌  Version '{version}' not found. Available options: {avail_ver}[/red]")
            return False

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
            console.print(f"[red]❌  Format '{format}' not found. Available options: {avail_fmt}[/red]")
            return False
    elif formats:
        selected_format_name = formats[0]["name"]
        alt = formats[0]["value"]

    system = detail.get("system") or "Unknown"
    title = detail.get("title") or f"game_{game_id}"
    filename = detail.get("filename") or ""

    # --- Show info before downloading ---
    console.print()
    console.print(f"[bold]🎮 {title}[/bold]")
    console.print(f"  System  : {system}")
    console.print(f"  Version : {actual_version}")
    console.print(f"  Format  : {selected_format_name}")
    console.print(f"  Media ID: {media_id}")
    console.print(f"  Output  : {base_dir / system / title}/")
    console.print()

    # --- Run the download ---
    try:
        cfg = Config(download_dir=base_dir) if output_dir else None
        out_path = download_game(
            download_host=detail["download_host"],
            media_id=media_id,
            game_id=game_id,
            system=system,
            title=title,
            alt=alt,
            filename=filename,
            config=cfg,
        )
        console.print(f"\n[bold green]✅  Download complete:[/bold green] {out_path}")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌  Download process failed (exit code {e.returncode}).[/red]")
        return False
    except Exception as e:
        console.print(f"[red]❌  Error: {e}[/red]")
        return False

    if extract:
        archive = find_downloaded_archive(base_dir / system / title)
        if archive is None:
            console.print("[yellow]⚠  --extract requested but no .7z archive was found.[/yellow]")
            return False
        try:
            with console.status(f"Extracting [bold]{archive.name}[/bold]..."):
                extract_archive(archive, remove_after=delete_archive)
            console.print(f"[bold green]✅  Extracted:[/bold green] {archive.parent}")
        except subprocess.CalledProcessError as e:
            console.print(f"[red]❌  Extraction failed (exit code {e.returncode}).[/red]")
            return False
        except Exception as e:
            console.print(f"[red]❌  Extraction error: {e}[/red]")
            return False

    return True


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
    output_dir: Optional[str],
) -> None:
    """Download one or more ROMs/ISOs by game ID.

    \b
    File is saved to: DOWNLOAD_DIR/<SYSTEM>/<title>/
    Examples:
      vimms download 17874 --format rvz --latest --extract
      vimms download 17874 8342 12345 --latest --wait 5
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

    base_dir = Path(output_dir).expanduser() if output_dir else config.download_dir

    with VimmScraper() as scraper:
        results = []
        for i, game_id in enumerate(game_ids):
            if i > 0 and wait > 0:
                time.sleep(wait)
            results.append(
                _download_one(
                    scraper, game_id, format, version, latest, base_dir, output_dir,
                    extract=extract, delete_archive=delete_archive,
                )
            )

    if len(game_ids) > 1:
        succeeded = sum(results)
        console.print(f"\n[bold]Queue complete:[/bold] {succeeded}/{len(game_ids)} succeeded.")
        failed_ids = [gid for gid, ok in zip(game_ids, results) if not ok]
        if failed_ids:
            console.print(f"[red]Failed IDs:[/red] {' '.join(str(gid) for gid in failed_ids)}")

    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
