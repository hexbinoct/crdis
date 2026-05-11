#!/usr/bin/env python3
"""Diff two parsed CSArchive record streams from .rpt files.

Usage:
    diff_records.py A.rpt B.rpt [--context N] [--max-bytes N]

Strategy:
    1. Decrypt + inflate each Contents stream.
    2. Parse top-level records via CSArchiveParser.
    3. Align records with difflib.SequenceMatcher on a per-record signature
       (tag, length, value). Print equal/insert/delete/replace blocks.
    4. For replaced records of the same tag, additionally show a byte-level diff
       (offset, before, after) of the value bytes — useful for spotting which
       fields inside a record changed.

This is the workhorse for Round 10 paired-sample diffing.
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

# Make the project root importable when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crdis.container import is_rpt, read_stream  # noqa: E402
from crdis.codec.cs_archive import CSArchiveParser, Record  # noqa: E402
from crdis.codec.cslibu_aes import decrypt_contents_stream  # noqa: E402


def load_records(path: Path, *, recurse: bool = True) -> list[Record]:
    if not is_rpt(path):
        raise SystemExit(f"{path}: not an .rpt file")
    body = read_stream(path, "Contents")
    plain = decrypt_contents_stream(body)
    return CSArchiveParser(plain).parse_all(recurse=recurse)


def sig(r: Record) -> tuple[int, int, bytes]:
    """Alignment key: identical (tag, length, value) => 'equal' in difflib."""
    return (r.tag, r.length, r.value)


def fmt_rec(idx: int, r: Record, side: str) -> str:
    head = f"  {side} #{idx:>3} tag=0x{r.tag:04x}({r.tag:5d}) len={r.length:>5}"
    return f"{head}  val[:32]={r.value[:32].hex()}"


def diff_bytes(a: bytes, b: bytes, max_runs: int = 8) -> str:
    """Compact byte-level diff: runs of differing offsets and their values."""
    n = max(len(a), len(b))
    aa = a + b"\x00" * (n - len(a))
    bb = b + b"\x00" * (n - len(b))
    runs: list[tuple[int, bytes, bytes]] = []
    i = 0
    while i < n:
        if aa[i] != bb[i]:
            j = i
            while j < n and aa[j] != bb[j]:
                j += 1
            runs.append((i, aa[i:j], bb[i:j]))
            i = j
        else:
            i += 1
    if not runs:
        return "    (no value-byte differences)"
    out = []
    for off, av, bv in runs[:max_runs]:
        out.append(f"    @0x{off:04x}  - {av.hex()}\n              + {bv.hex()}")
    if len(runs) > max_runs:
        out.append(f"    ... and {len(runs) - max_runs} more diff run(s)")
    if len(a) != len(b):
        out.append(f"    (length differs: {len(a)} vs {len(b)})")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Diff two .rpt record streams")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--context", type=int, default=1,
                    help="Equal-record context lines around changes (default 1)")
    ap.add_argument("--all", action="store_true",
                    help="Print every equal block in full (default: collapse with count)")
    args = ap.parse_args(argv)

    a_path, b_path = Path(args.a), Path(args.b)
    ra = load_records(a_path)
    rb = load_records(b_path)
    print(f"A {a_path}: {len(ra)} records")
    print(f"B {b_path}: {len(rb)} records")

    sa = [sig(r) for r in ra]
    sb = [sig(r) for r in rb]
    sm = difflib.SequenceMatcher(a=sa, b=sb, autojunk=False)
    ops = sm.get_opcodes()

    for op, i1, i2, j1, j2 in ops:
        if op == "equal":
            n = i2 - i1
            if args.all:
                for k in range(n):
                    print(fmt_rec(i1 + k, ra[i1 + k], "="))
            else:
                if n <= 2 * args.context:
                    for k in range(n):
                        print(fmt_rec(i1 + k, ra[i1 + k], "="))
                else:
                    for k in range(args.context):
                        print(fmt_rec(i1 + k, ra[i1 + k], "="))
                    print(f"  ... {n - 2 * args.context} identical record(s) ...")
                    for k in range(args.context):
                        print(fmt_rec(i2 - args.context + k,
                                      ra[i2 - args.context + k], "="))
        elif op == "delete":
            print(f"--- delete A[{i1}:{i2}] ---")
            for k in range(i1, i2):
                print(fmt_rec(k, ra[k], "-"))
        elif op == "insert":
            print(f"+++ insert B[{j1}:{j2}] ---")
            for k in range(j1, j2):
                print(fmt_rec(k, rb[k], "+"))
        elif op == "replace":
            print(f"~~~ replace A[{i1}:{i2}] -> B[{j1}:{j2}] ~~~")
            # If same length and tags pair up 1:1, do byte-diffs.
            if (i2 - i1) == (j2 - j1):
                for off in range(i2 - i1):
                    ar, br = ra[i1 + off], rb[j1 + off]
                    print(fmt_rec(i1 + off, ar, "-"))
                    print(fmt_rec(j1 + off, br, "+"))
                    if ar.tag == br.tag:
                        print(diff_bytes(ar.value, br.value))
                        # Auto-descend: when both sides have a single same-tag
                        # nested child, diff the child's value and tail too.
                        if (len(ar.children) == 1 and len(br.children) == 1
                                and ar.children[0].tag == br.children[0].tag):
                            ac, bc = ar.children[0], br.children[0]
                            print(f"    └─ nested tag=0x{ac.tag:04x} value diff:")
                            print(diff_bytes(ac.value, bc.value))
                            if ar.tail or br.tail:
                                print(f"    └─ tail diff ({len(ar.tail)}B vs {len(br.tail)}B):")
                                print(diff_bytes(ar.tail, br.tail))
            else:
                for k in range(i1, i2):
                    print(fmt_rec(k, ra[k], "-"))
                for k in range(j1, j2):
                    print(fmt_rec(k, rb[k], "+"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
