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

# Shared by render_table_lines() and render_header_line() so the header and
# the data rows are guaranteed to use identical column widths.
TITLE_WIDTH = 24
PHASE_WIDTH = 14
COLUMN_GAP = "  "

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
        self._lock = threading.RLock()
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
        # Locked end-to-end (not just the in-memory read that used to happen
        # via snapshot()) because add_item()/update_phase()/set_title() call
        # this right after releasing the lock, and there are two threads
        # that can be doing so concurrently in the pipelined queue (the
        # download lane and the single-worker post-processing lane).
        # Without the lock, two overlapping writers using the same fixed
        # .tmp path could race: one thread's os.replace() "steals" the
        # other's .tmp file out from under it, raising ENOENT. The
        # per-thread-ident suffix on tmp_path is a second, independent
        # safety net against exactly that. (self._lock is an RLock as
        # cheap insurance against any future nested acquisition here.)
        with self._lock:
            items = [self._items[gid] for gid in self._order]
            payload = {"items": [item.to_dict() for item in items]}
            tmp_path = self.snapshot_path.with_name(f"{self.snapshot_path.name}.{threading.get_ident()}.tmp")
            tmp_path.write_text(json.dumps(payload))
            tmp_path.replace(self.snapshot_path)  # atomic on POSIX


def _pad_ansi(styled: str, plain: str, width: int) -> str:
    """Left-justify `styled` to `width`, padding by the *visible* (plain) length
    so embedded ANSI escape codes don't throw off column alignment."""
    pad = max(0, width - len(plain))
    return styled + (" " * pad)


def active_phase_names(item: ItemStatus) -> list[str]:
    """Phases actually requested for this item's run (not 'skipped'), in PHASE_ORDER."""
    return [name for name in PHASE_ORDER if item.phases[name].state != "skipped"]


def render_header_line(active_phases: list[str]) -> str:
    """
    Header text for fzf's --header, column-aligned to match
    render_table_lines()'s single visible field exactly. `active_phases`
    should be the same list passed to StatusBoard.add_item() for this run —
    phases nobody asked for (e.g. --zar with no --extract-xiso) aren't
    shown as columns at all, rather than as a permanently "skipped" one.
    """
    columns = ["Title".ljust(TITLE_WIDTH)] + [
        PHASE_LABELS[name].ljust(PHASE_WIDTH) for name in active_phases
    ]
    return COLUMN_GAP.join(columns)


def render_table_lines(items: list[ItemStatus]) -> list[str]:
    """
    Render fzf list lines: tab-separated `game_id`, `log_path` (both hidden
    from display via --with-nth), then a single pre-formatted visible field
    (title + phase columns, restricted to that item's active_phase_names()).
    Keeping the visible portion as one field — rather than several
    tab-separated ones shown via `--with-nth N..` — matters: fzf re-joins
    multiple `--with-nth`-selected fields using the `--delimiter` itself (a
    literal tab here), which does not line up with plain-space column
    padding the way render_header_line() is built, so header and rows would
    drift out of alignment.
    """
    lines = []
    for item in items:
        title_plain = item.title[:TITLE_WIDTH]
        columns = [title_plain.ljust(TITLE_WIDTH)]
        for name in active_phase_names(item):
            phase = item.phases[name]
            plain = phase.cell_plain()[:PHASE_WIDTH]
            columns.append(_pad_ansi(phase.cell_ansi(), plain, PHASE_WIDTH))
        visible = COLUMN_GAP.join(columns)
        lines.append("\t".join([str(item.game_id), item.log_path, visible]))
    return lines


def load_snapshot(path: Path) -> list[ItemStatus]:
    data = json.loads(path.read_text())
    return [ItemStatus.from_dict(d) for d in data.get("items", [])]
