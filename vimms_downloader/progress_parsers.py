"""
Pure line-parsers that extract a completion percentage from each download
tool's own output, for the live status table. None of these touch the
filesystem or subprocess state directly — they take a single line of text
(and, where the tool doesn't self-report an overall percentage, a
pre-computed file count) and return an int 0-100, or None if the line
doesn't carry progress info.

Ad hoc CLI progress text isn't a stable contract, so every parser here
fails soft: a line it doesn't recognize just yields None rather than
raising, and the caller keeps showing the phase as "running" with no (or
its last known) percentage.
"""

import re

_ARIA2_PERCENT_RE = re.compile(r"\((\d{1,3})%\)")
_7Z_PERCENT_RE = re.compile(r"(?:^\s*(\d{1,3})%|\s(\d{1,3})%\s*$)")
_EXTRACT_XISO_FILE_RE = re.compile(r"^extracting\s+.+\[(\d{1,3})%\]\s*$", re.IGNORECASE)
_ZARCHIVE_ADDING_RE = re.compile(r"^Adding\s+")


def _clamp(percent: int) -> int:
    return max(0, min(100, percent))


def parse_aria2c_line(line: str) -> int | None:
    """
    Parse aria2c's bracketed summary line, e.g.:
        [#d1b921 359MiB/3.3GiB(10%) CN:1 DL:6.3MiB ETA:7m56s]
    Requires --summary-interval set low enough to get frequent updates when
    aria2c's stdout isn't a real terminal.
    """
    m = _ARIA2_PERCENT_RE.search(line)
    if not m:
        return None
    return _clamp(int(m.group(1)))


def parse_7z_line(line: str) -> int | None:
    """
    Parse a 7z progress line. 7-Zip's classic style prints the percentage
    near the start of the line (e.g. "  3% 2 - somefile.bin"); some
    versions/modes instead show it trailing. Try both; caller should treat
    a None as "no new info" rather than a regression.
    """
    m = _7Z_PERCENT_RE.search(line)
    if not m:
        return None
    percent = m.group(1) or m.group(2)
    return _clamp(int(percent))


def is_extract_xiso_file_line(line: str) -> bool:
    """
    True if this line represents one completed file in extract-xiso's
    output, e.g.:
        extracting /path/to/file.bin (1234 bytes) [100%]
    extract-xiso reports completion per-file, not per-archive, so overall
    percent is derived by counting these lines against a pre-flight file
    count (see count_xiso_files() in downloader.py) via
    percent_from_file_count() below.
    """
    return bool(_EXTRACT_XISO_FILE_RE.match(line.strip()))


def is_zarchive_adding_line(line: str) -> bool:
    """True if this line represents one file zarchive has just added to the pack."""
    return bool(_ZARCHIVE_ADDING_RE.match(line.strip()))


def percent_from_file_count(completed: int, total: int | None) -> int | None:
    """Shared helper for the file-counting phases (extract-xiso, zarchive)."""
    if not total:
        return None
    return _clamp(int(completed / total * 100))
