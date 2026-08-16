"""Data models and system constants for Vimm's Lair."""

from dataclasses import dataclass
from typing import Optional

# All 36 systems available in the vault.
# Key = URL code, Value = display name
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
    """Full details of a single game from the vault page."""

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
    """A single search or browse result row."""

    game_id: int
    title:   str
    url:     str
