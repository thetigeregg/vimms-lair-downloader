"""
Thread-safe live status board for the fzf-driven download TUI.

The download/post-process pipeline (vimms_downloader/cli.py) reports into a
single StatusBoard as it runs. The board is snapshotted to a small JSON file
on every change; a separate `vimms _render-status` process (run repeatedly
by fzf's `every(1):reload-sync` bind) reads that file and prints the table
fzf displays. Keeping the "renderer" as a standalone read of a JSON file
(rather than some IPC channel) keeps the fzf side dead simple — it's just a
CLI command fzf can shell out to on a timer.
"""

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

PhaseState = Literal["pending", "running", "done", "failed", "skipped"]

# Fixed column order — a phase not requested via CLI flags stays "skipped".
PHASE_ORDER = ["download", "7z", "extract-xiso", "zar"]
PHASE_LABELS = {"download": "Download", "7z": "7z", "extract-xiso": "extract-xiso", "zar": "zar"}

_STATE_COLOR = {
    "pending": "dim",
    "running": "yellow",
    "done": "green",
    "failed": "red",
    "skipped": "dim",
}
_STATE_GLYPH = {
    "pending": "·",   # ·
    "running": "▸",   # ▸
    "done": "✓",      # ✓
    "failed": "✗",    # ✗
    "skipped": "-",
}
_ANSI_CODE = {
    "dim": "\x1b[2m",
    "yellow": "\x1b[33m",
    "green": "\x1b[32m",
    "red": "\x1b[31m",
}
_ANSI_RESET = "\x1b[0m"


@dataclass
class PhaseStatus:
    name: str
    state: PhaseState = "pending"
    percent: int | None = None
    detail: str = ""
    started_at: float | None = None
    finished_at: float | None = None

    def cell_plain(self) -> str:
        glyph = _STATE_GLYPH[self.state]
        if self.state == "running" and self.percent is not None:
            return f"{glyph} {self.percent}%"
        if self.state == "running":
            elapsed = int(time.time() - self.started_at) if self.started_at else 0
            return f"{glyph} {elapsed}s"
        if self.state == "failed":
            return f"{glyph} failed"
        if self.state == "skipped":
            return glyph
        return f"{glyph} {self.state}"

    def cell_ansi(self) -> str:
        color = _ANSI_CODE.get(_STATE_COLOR[self.state], "")
        body = self.cell_plain()
        return f"{color}{body}{_ANSI_RESET}" if color else body


@dataclass
class ItemStatus:
    game_id: int
    title: str = ""
    log_path: str = ""
    phases: dict[str, PhaseStatus] = field(
        default_factory=lambda: {name: PhaseStatus(name=name) for name in PHASE_ORDER}
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ItemStatus":
        phases = {name: PhaseStatus(**pdata) for name, pdata in d.get("phases", {}).items()}
        return cls(game_id=d["game_id"], title=d.get("title", ""), log_path=d.get("log_path", ""), phases=phases)


class StatusBoard:
    """In-memory, thread-safe status for every item in the current queue."""

    def __init__(self, snapshot_path: Path) -> None:
        self._lock = threading.Lock()
        self._items: dict[int, ItemStatus] = {}
        self._order: list[int] = []
        self.snapshot_path = snapshot_path

    def add_item(self, game_id: int, title: str, log_path: Path, active_phases: list[str]) -> None:
        with self._lock:
            item = ItemStatus(game_id=game_id, title=title, log_path=str(log_path))
            for name in PHASE_ORDER:
                item.phases[name].state = "pending" if name in active_phases else "skipped"
            self._items[game_id] = item
            self._order.append(game_id)
        self._write_snapshot()

    def update_phase(self, game_id: int, phase: str, **fields) -> None:
        with self._lock:
            item = self._items.get(game_id)
            if item is None:
                return
            phase_status = item.phases[phase]
            for k, v in fields.items():
                setattr(phase_status, k, v)
        self._write_snapshot()

    def set_title(self, game_id: int, title: str) -> None:
        with self._lock:
            item = self._items.get(game_id)
            if item is not None:
                item.title = title
        self._write_snapshot()

    def snapshot(self) -> list[ItemStatus]:
        with self._lock:
            return [self._items[gid] for gid in self._order]

    def _write_snapshot(self) -> None:
        # Called right after releasing/around the lock is fine here since we
        # only ever call this right after a mutation on the same thread;
        # snapshot() itself takes its own lock for the read.
        items = self.snapshot()
        payload = {"items": [item.to_dict() for item in items]}
        tmp_path = self.snapshot_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload))
        tmp_path.replace(self.snapshot_path)  # atomic on POSIX


def _pad_ansi(styled: str, plain: str, width: int) -> str:
    """Left-justify `styled` to `width`, padding by the *visible* (plain) length
    so embedded ANSI escape codes don't throw off column alignment."""
    pad = max(0, width - len(plain))
    return styled + (" " * pad)


def render_table_lines(items: list[ItemStatus]) -> list[str]:
    """
    Render fzf list lines: tab-separated `game_id`, `log_path` (both hidden
    from display via --with-nth), then the visible title + phase columns.
    """
    lines = []
    for item in items:
        title_plain = item.title[:30]
        columns = [title_plain.ljust(30)]
        for name in PHASE_ORDER:
            phase = item.phases[name]
            plain = phase.cell_plain()[:18]
            columns.append(_pad_ansi(phase.cell_ansi(), plain, 18))
        lines.append("\t".join([str(item.game_id), item.log_path, *columns]))
    return lines


def load_snapshot(path: Path) -> list[ItemStatus]:
    data = json.loads(path.read_text())
    return [ItemStatus.from_dict(d) for d in data.get("items", [])]
