"""CLI entry point — Vimm's Lair Downloader."""

import subprocess
from pathlib import Path
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.table import Table

from vimms_downloader.config import Config, config
from vimms_downloader.downloader import download_game
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
    Contoh alur kerja:
      vimms list-systems
      vimms search "mario" -s NES
      vimms info 17874
      vimms download 17874 --format rvz --version 1.2
    """


# --------------------------------------------------------------------------
# list-systems
# --------------------------------------------------------------------------

@cli.command("list-systems")
def cmd_list_systems() -> None:
    """Tampilkan semua sistem yang tersedia di Vimm's Lair."""
    table = Table(title="Sistem di Vimm's Lair", show_lines=False, expand=False)
    table.add_column("Kode URL", style="cyan", no_wrap=True)
    table.add_column("Nama Sistem", style="green")

    for code, name in sorted(SYSTEMS.items(), key=lambda x: x[1]):
        table.add_row(code, name)

    console.print(table)
    console.print(f"[dim]Total: {len(SYSTEMS)} sistem[/dim]")


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

@cli.command("search")
@click.argument("query")
@click.option(
    "--system", "-s",
    default=None,
    metavar="CODE",
    help="Filter per kode sistem (NES, PS1, SNES, ...).",
)
@click.option(
    "--limit", "-l",
    default=20,
    type=int,
    show_default=True,
    help="Batas jumlah hasil yang ditampilkan.",
)
def cmd_search(query: str, system: Optional[str], limit: int) -> None:
    """Cari game di vault.

    \b
    Contoh:
      vimms search "mario"
      vimms search "zelda" -s N64 -l 10
    """
    try:
        with VimmScraper() as scraper:
            with console.status(f"Mencari [bold]{query}[/bold]..."):
                results = scraper.search(query, system=system)
    except httpx.HTTPError as e:
        console.print(f"[red]❌  Gagal terhubung ke Vimm's Lair: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]❌  Error: {e}[/red]")
        raise SystemExit(1)

    if not results:
        console.print("[red]Tidak ada hasil ditemukan.[/red]")
        return

    shown = results[:limit]
    table = Table(
        title=f"Hasil pencarian: '[bold]{query}[/bold]'"
              + (f" — sistem: {system}" if system else ""),
        show_lines=False,
    )
    table.add_column("ID", style="cyan", justify="right", no_wrap=True)
    table.add_column("Judul", style="green")
    table.add_column("URL", style="dim")

    for r in shown:
        table.add_row(str(r["game_id"]), r["title"], r["url"])

    console.print(table)
    if len(results) > limit:
        console.print(
            f"[dim]Menampilkan {limit} dari {len(results)} hasil. "
            f"Gunakan --limit untuk memperbanyak.[/dim]"
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
    help="Filter berdasarkan huruf awal judul.",
)
@click.option(
    "--limit",
    default=50,
    type=int,
    show_default=True,
    help="Batas jumlah baris yang ditampilkan.",
)
def cmd_browse(system: str, letter: Optional[str], limit: int) -> None:
    """Browse daftar game per sistem.

    \b
    Contoh:
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
        console.print(f"[red]❌  Gagal terhubung ke Vimm's Lair: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]❌  Error: {e}[/red]")
        raise SystemExit(1)

    if not results:
        console.print("[red]Tidak ada game ditemukan.[/red]")
        return

    shown = results[:limit]
    table = Table(title=f"Game List — {label}", show_lines=False)
    table.add_column("ID", style="cyan", justify="right", no_wrap=True)
    table.add_column("Judul", style="green")

    for r in shown:
        table.add_row(str(r["game_id"]), r["title"])

    console.print(table)
    if len(results) > limit:
        console.print(
            f"[dim]Menampilkan {limit} dari {len(results)} game. "
            f"Gunakan --limit untuk melihat lebih banyak.[/dim]"
        )


# --------------------------------------------------------------------------
# info
# --------------------------------------------------------------------------

@cli.command("info")
@click.argument("game_id", type=int)
def cmd_info(game_id: int) -> None:
    """Tampilkan detail satu game berdasarkan ID.

    \b
    Contoh:
      vimms info 17874
    """
    try:
        with VimmScraper() as scraper:
            with console.status(f"Fetching game [bold]{game_id}[/bold]..."):
                d = scraper.get_game_detail(game_id)
    except httpx.HTTPError as e:
        console.print(f"[red]❌  Gagal terhubung ke Vimm's Lair: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]❌  Error: {e}[/red]")
        raise SystemExit(1)

    if not d.get("title") and not d.get("media_id"):
        console.print(f"[red]Game ID {game_id} tidak ditemukan.[/red]")
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
        ("Sistem",   d.get("system") or ""),
        ("Tahun",    d.get("year") or ""),
        ("Pemain",   d.get("players") or ""),
        ("Ukuran",   d.get("file_size") or ""),
        ("Format",   fmt_str),
        ("Versi",    ver_str),
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
        console.print(f"[dim]Untuk download: [bold]{cmd_suggest}[/bold][/dim]")
    else:
        console.print("[yellow]⚠  Download tidak tersedia untuk game ini.[/yellow]")


# --------------------------------------------------------------------------
# download
# --------------------------------------------------------------------------

@cli.command("download")
@click.argument("game_id", type=int)
@click.option(
    "--format", "-f",
    default=None,
    help="Format disk/ROM yang diinginkan (e.g. wbfs, rvz, iso).",
)
@click.option(
    "--version", "-v",
    default=None,
    help="Versi game yang diinginkan (e.g. 1.0, 1.1, 1.2).",
)
@click.option(
    "--output-dir", "-o",
    default=None,
    metavar="PATH",
    help="Override direktori output (default dari DOWNLOAD_DIR di config/.env).",
)
def cmd_download(
    game_id: int,
    format: Optional[str],
    version: Optional[str],
    output_dir: Optional[str],
) -> None:
    """Download ROM/ISO berdasarkan game ID.

    \b
    File disimpan di: DOWNLOAD_DIR/<SISTEM>/<judul>/
    Contoh:
      vimms download 17874 --format rvz --version 1.2
    """
    base_dir = Path(output_dir).expanduser() if output_dir else config.download_dir

    # --- Ambil detail game ---
    try:
        with VimmScraper() as scraper:
            with console.status(f"Fetching detail game [bold]{game_id}[/bold]..."):
                detail = scraper.get_game_detail(game_id)
    except httpx.HTTPError as e:
        console.print(f"[red]❌  Gagal terhubung ke Vimm's Lair: {e}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]❌  Error fetching detail: {e}[/red]")
        raise SystemExit(1)

    if not detail.get("media_id"):
        console.print(
            f"[red]❌  mediaId tidak ditemukan untuk game {game_id}. "
            f"Download tidak tersedia.[/red]"
        )
        return

    # --- Tentukan mediaId berdasarkan versi ---
    media_list = detail.get("media_list", [])
    target_media = None

    if version and media_list:
        for m in media_list:
            if m.get("Version") == version:
                target_media = m
                break
        if not target_media:
            avail_ver = ", ".join(detail.get("versions", []))
            console.print(f"[red]❌  Versi '{version}' tidak ditemukan. Opsi tersedia: {avail_ver}[/red]")
            return

    if not target_media:
        # Cari record mediaId default
        for m in media_list:
            if m.get("ID") == detail["media_id"]:
                target_media = m
                break
        if not target_media:
            target_media = {"ID": detail["media_id"], "Version": "Default"}

    media_id = target_media["ID"]
    actual_version = target_media.get("Version", "Default")

    # --- Tentukan format (alt parameter) ---
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
            console.print(f"[red]❌  Format '{format}' tidak ditemukan. Opsi tersedia: {avail_fmt}[/red]")
            return
    elif formats:
        selected_format_name = formats[0]["name"]
        alt = formats[0]["value"]

    system = detail.get("system") or "Unknown"
    title = detail.get("title") or f"game_{game_id}"
    filename = detail.get("filename") or ""

    # --- Tampilkan info sebelum download ---
    console.print()
    console.print(f"[bold]🎮 {title}[/bold]")
    console.print(f"  Sistem  : {system}")
    console.print(f"  Versi   : {actual_version}")
    console.print(f"  Format  : {selected_format_name}")
    console.print(f"  Media ID: {media_id}")
    console.print(f"  Output  : {base_dir / system / title}/")
    console.print()

    # --- Jalankan download ---
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
        console.print(f"\n[bold green]✅  Download selesai:[/bold green] {out_path}")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌  Proses download gagal (exit code {e.returncode}).[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]❌  Error: {e}[/red]")
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
