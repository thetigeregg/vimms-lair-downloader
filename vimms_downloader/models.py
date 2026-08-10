"""Data models dan konstanta sistem Vimm's Lair."""

from dataclasses import dataclass
from typing import Optional

# Semua 36 sistem yang tersedia di vault.
# Key = kode URL, Value = nama tampilan
SYSTEMS: dict[str, str] = {
    "Atari2600": "Atari 2600",
    "Atari5200": "Atari 5200",
    "Atari7800": "Atari 7800",
    "Jaguar":    "Jaguar",
    "JaguarCD":  "Jaguar CD",
    "Lynx":      "Lynx",
    "NES":       "Nintendo",
    "SNES":      "Super Nintendo",
    "N64":       "Nintendo 64",
    "GameCube":  "GameCube",
    "Wii":       "Wii",
    "WiiWare":   "WiiWare",
    "WiiU":      "Wii U",
    "GB":        "Game Boy",
    "GBC":       "Game Boy Color",
    "GBA":       "Game Boy Advance",
    "DS":        "Nintendo DS",
    "3DS":       "Nintendo 3DS",
    "VB":        "Virtual Boy",
    "SMS":       "Master System",
    "Genesis":   "Genesis",
    "SegaCD":    "Sega CD",
    "32X":       "Sega 32X",
    "Saturn":    "Saturn",
    "Dreamcast": "Dreamcast",
    "GG":        "Game Gear",
    "TG16":      "TurboGrafx-16",
    "TGCD":      "TurboGrafx-CD",
    "CDi":       "CD-i",
    "PS1":       "PlayStation",
    "PS2":       "PlayStation 2",
    "PS3":       "PlayStation 3",
    "PSP":       "PlayStation Portable",
    "Xbox":      "Xbox",
    "Xbox360":   "Xbox 360",
    "X360-D":    "Xbox 360 (Digital)",
}


@dataclass
class GameInfo:
    """Detail lengkap satu game dari halaman vault."""

    game_id:      int
    title:        str
    filename:     str = ""
    system:       Optional[str] = None
    media_id:     Optional[int] = None
    year:         Optional[str] = None
    players:      Optional[str] = None
    region:       Optional[str] = None
    file_size:    Optional[str] = None
    url:          str = ""


@dataclass
class SearchResult:
    """Satu baris hasil pencarian atau browse."""

    game_id: int
    title:   str
    url:     str
