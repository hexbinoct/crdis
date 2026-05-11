"""CFB container layer for .rpt files.

A `.rpt` is an OLE Compound File Binary (CFB) — magic `D0 CF 11 E0 A1 B1 1A E1`.
This module is a thin wrapper around `olefile` that surfaces the streams a CR
report contains. It does not interpret stream contents; that lives in sibling
modules.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import olefile


CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# Stream names known to appear in CRforVS 13.x reports.
KNOWN_STREAMS: dict[str, str] = {
    "\x05SummaryInformation": "Standard MS Office property set (title, author, timestamps, etc).",
    "Contents": "Report definition. Body is encrypted/scrambled in CRforVS 13.x — see research/format_notes.md.",
    "CrystalReportDesignerStream": "Designer state. Static for many sample variants.",
    "QESession": "Per-save session GUID/salt. Random-looking; ignored.",
    "ReportInfo": "Report-level metadata. Static for many sample variants.",
}


@dataclass(frozen=True)
class StreamInfo:
    name: str
    size: int
    sha256: str
    role: str  # human-readable hypothesis from KNOWN_STREAMS, or "(unknown)"


def is_rpt(path: str | Path) -> bool:
    """Quick check: does the file have a CFB magic header?"""
    with open(path, "rb") as f:
        return f.read(8) == CFB_MAGIC


def list_streams(path: str | Path) -> list[StreamInfo]:
    """Enumerate all streams in the .rpt and return their size + sha256."""
    out: list[StreamInfo] = []
    with olefile.OleFileIO(str(path)) as ole:
        for entry in ole.listdir(streams=True, storages=False):
            stream_path = "/".join(entry)
            with ole.openstream(stream_path) as s:
                data = s.read()
            out.append(
                StreamInfo(
                    name=stream_path,
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    role=KNOWN_STREAMS.get(stream_path, "(unknown)"),
                )
            )
    return out


def read_stream(path: str | Path, stream_name: str) -> bytes:
    """Read a single stream by exact name (e.g. 'Contents', '\\x05SummaryInformation')."""
    with olefile.OleFileIO(str(path)) as ole:
        with ole.openstream(stream_name) as s:
            return s.read()
