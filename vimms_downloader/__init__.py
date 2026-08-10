"""Vimm's Lair Downloader."""

from vimms_downloader.config import Config
from vimms_downloader.downloader import download_game
from vimms_downloader.models import GameInfo, SYSTEMS
from vimms_downloader.scraper import VimmScraper

__version__ = "0.1.0"

__all__ = [
    "Config",
    "GameInfo",
    "SYSTEMS",
    "VimmScraper",
    "download_game",
    "__version__",
]
