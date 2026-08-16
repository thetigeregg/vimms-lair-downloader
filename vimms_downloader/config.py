"""
Configuration management for Vimm's Lair Downloader.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


@dataclass
class Config:
    """Dataclass holding application configuration loaded from environment variables."""

    download_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DOWNLOAD_DIR", "~/roms")).expanduser()
    )
    http_timeout: int = field(
        default_factory=lambda: int(os.getenv("HTTP_TIMEOUT", "30"))
    )
    aria2_connections: int = field(
        default_factory=lambda: int(os.getenv("ARIA2_CONNECTIONS", "1"))
    )
    user_agent: str = field(
        default_factory=lambda: os.getenv("USER_AGENT", DEFAULT_USER_AGENT)
    )

    @property
    def DOWNLOAD_DIR(self) -> Path:
        """Alias for backward compatibility with uppercase env var style."""
        return self.download_dir

    @property
    def HTTP_TIMEOUT(self) -> int:
        """Alias for backward compatibility with uppercase env var style."""
        return self.http_timeout

    @property
    def ARIA2_CONNECTIONS(self) -> int:
        """Alias for backward compatibility with uppercase env var style."""
        return self.aria2_connections

    @property
    def USER_AGENT(self) -> str:
        """Alias for backward compatibility with uppercase env var style."""
        return self.user_agent

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration instance from environment variables."""
        return cls()


def get_config() -> Config:
    """Helper function to obtain a default Config instance."""
    return Config.from_env()


# Global default instance
config = get_config()
