"""Verify that crdis produces identical output to the captured Windows baseline.

Run on a fresh machine after `pip install -e .` to confirm the parser behaves
the same way the previous Windows session left it. Compares only what *must*
match across platforms — stream sha256s and summary-property JSON. Ignores
cosmetic differences (path separators, terminal width, etc.).

Usage:
    python3 tools/verify_baseline.py

Exit code 0 = baseline matches; 1 = mismatch (details printed).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from crdis.container import list_streams           # noqa: E402
from crdis.summary import read_summary             # noqa: E402


# Expected stream sha256 hashes — captured on Windows on 2026-05-08 from the
# CRforVS-13.0.20.2399-authored sample files. These are pure file content;
# they MUST match byte-for-byte on any platform.
EXPECTED_STREAMS: dict[str, dict[str, tuple[int, str]]] = {
    "samples/001_empty/report.rpt": {
        "\x05SummaryInformation":      (433,  "520e6f016f0e"),
        "Contents":                    (1406, "c8e0970711c1"),
        "CrystalReportDesignerStream": (114,  "e84d97ac02c1"),
        "QESession":                   (64,   "64a0c3bcb91c"),
        "ReportInfo":                  (58,   "462365f68ee2"),
    },
    "samples/002_one_label/report.rpt": {
        "\x05SummaryInformation":      (437,  "3036e0428735"),
        "Contents":                    (1633, "454459322d53"),
        "CrystalReportDesignerStream": (114,  "e84d97ac02c1"),
        "QESession":                   (64,   "b90c42772028"),
        "ReportInfo":                  (58,   "462365f68ee2"),
    },
}

# Expected summary-property output, captured the same day. Datetime fields are
# compared as ISO strings to avoid Python timezone/microsecond reformatting drift.
BASELINE_SUMMARY_FILES = {
    "samples/001_empty/report.rpt":      "research/windows_baseline_001_summary.json",
    "samples/002_one_label/report.rpt":  "research/windows_baseline_002_summary.json",
}


def _summary_to_json(summary: dict[str, object]) -> dict[str, object]:
    """Convert summary dict to the same JSON-friendly shape `summary-json` emits."""
    return {
        k: (v.isoformat() if hasattr(v, "isoformat") else v)
        for k, v in summary.items()
    }


def main() -> int:
    failures: list[str] = []

    for rel_sample, expected_streams in EXPECTED_STREAMS.items():
        sample = REPO / rel_sample
        if not sample.exists():
            failures.append(f"missing sample file: {sample}")
            continue

        # 1) stream inventory check
        actual = {s.name: (s.size, s.sha256[:12]) for s in list_streams(sample)}
        if actual != expected_streams:
            failures.append(
                f"stream mismatch in {rel_sample}\n"
                f"  expected: {expected_streams}\n"
                f"  actual:   {actual}"
            )

        # 2) summary properties check
        baseline_path = REPO / BASELINE_SUMMARY_FILES[rel_sample]
        if not baseline_path.exists():
            failures.append(f"missing baseline file: {baseline_path}")
            continue
        expected_summary = json.loads(baseline_path.read_text(encoding="utf-8"))
        actual_summary = _summary_to_json(read_summary(sample))
        if actual_summary != expected_summary:
            # Pinpoint the differing keys
            keys = set(expected_summary) | set(actual_summary)
            diffs = [
                f"    {k}: expected {expected_summary.get(k)!r}, got {actual_summary.get(k)!r}"
                for k in sorted(keys)
                if expected_summary.get(k) != actual_summary.get(k)
            ]
            failures.append(
                f"summary mismatch in {rel_sample}\n" + "\n".join(diffs)
            )

    if failures:
        print("FAIL — baseline does not match:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"PASS — {len(EXPECTED_STREAMS)} sample(s) match the Windows baseline.")
    print("       streams identical (size + sha256), summary properties identical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
