"""SummaryInformation stream — standard MS Office property set.

Format is `MS-OLEPS` (Microsoft public spec), not Crystal Reports specific.
`olefile` implements parsing, but the writer in CRforVS appears to over-pack the
property set so olefile occasionally reads past a string's logical end. We trim
defensively at the first NUL.
"""
from __future__ import annotations

from pathlib import Path

import olefile


def _clean(value: object) -> object:
    """Trim olefile string over-reads at the first NUL byte / NUL char."""
    if isinstance(value, bytes):
        return value.split(b"\x00", 1)[0].decode("latin-1", errors="replace") or None
    if isinstance(value, str):
        return value.split("\x00", 1)[0] or None
    return value


def read_summary(path: str | Path) -> dict[str, object]:
    """Return the standard summary properties: title, author, last-saved-time, etc."""
    with olefile.OleFileIO(str(path)) as ole:
        meta = ole.get_metadata()
    raw = {
        "title": meta.title,
        "subject": meta.subject,
        "author": meta.author,
        "keywords": meta.keywords,
        "comments": meta.comments,
        "last_saved_by": meta.last_saved_by,
        "revision_number": meta.revision_number,
        "create_time": meta.create_time,
        "last_saved_time": meta.last_saved_time,
        "creating_application": meta.creating_application,
        "company": meta.company,
        "manager": meta.manager,
    }
    return {k: _clean(v) for k, v in raw.items()}
