"""crdis CLI.

Subcommands as we build them. Today: `info`, `dump`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .codec.cs_archive import CSArchiveParser, dump_records
from .codec.cslibu_aes import decrypt_contents_stream
from .container import is_rpt, list_streams, read_stream
from .summary import read_summary


def _cmd_info(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not is_rpt(path):
        print(f"crdis: {path} does not look like a .rpt file (CFB magic missing).", file=sys.stderr)
        return 2

    print(f"file: {path}  ({path.stat().st_size} bytes)")
    print()
    print("streams:")
    streams = list_streams(path)
    for s in streams:
        # \x05 prefix on SummaryInformation is non-printable; show it readably
        display = s.name.replace("\x05", "\\x05")
        print(f"  {display:35s}  {s.size:>7d} B  sha256:{s.sha256[:12]}..  {s.role}")
    print()
    summary = read_summary(path)
    nonempty = {k: v for k, v in summary.items() if v}
    if nonempty:
        print("summary properties:")
        for k, v in nonempty.items():
            print(f"  {k:22s}  {v!r}")
    else:
        print("summary properties: (none set)")
    return 0


def _cmd_dump(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not is_rpt(path):
        print(f"crdis: {path} does not look like a .rpt file.", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for s in list_streams(path):
        # Sanitize filename — \x05 prefix and any path slashes
        safe = s.name.replace("\x05", "x05_").replace("/", "_")
        out_path = out_dir / f"{safe}.bin"
        out_path.write_bytes(read_stream(path, s.name))
        print(f"  {out_path}  ({s.size} B)")
    return 0


def _cmd_decrypt(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not is_rpt(path):
        print(f"crdis: {path} does not look like a .rpt file.", file=sys.stderr)
        return 2
    body = read_stream(path, "Contents")
    plain = decrypt_contents_stream(body)
    out_path = Path(args.out) if args.out else path.with_suffix(".contents.bin")
    out_path.write_bytes(plain)
    print(f"{path}: {len(body)} encrypted -> {len(plain)} plaintext -> {out_path}")
    return 0


def _cmd_records(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not is_rpt(path):
        print(f"crdis: {path} does not look like a .rpt file.", file=sys.stderr)
        return 2
    body = read_stream(path, "Contents")
    plain = decrypt_contents_stream(body)
    parser = CSArchiveParser(plain)
    records = parser.parse_all(recurse=args.recurse)
    print(f"{path}: {len(plain)} plaintext bytes, {len(records)} top-level records")
    if not args.summary:
        dump_records(records, max_show=args.limit)
    else:
        from collections import Counter
        hist = Counter(r.tag for r in records)
        print("Tag histogram:")
        for tag, count in sorted(hist.items(), key=lambda kv: -kv[1]):
            print(f"  tag=0x{tag:04x} ({tag:5d})  count={count}")
    return 0


def _cmd_summary_json(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not is_rpt(path):
        print(f"crdis: {path} does not look like a .rpt file.", file=sys.stderr)
        return 2
    summary = read_summary(path)
    serializable = {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                    for k, v in summary.items()}
    json.dump(serializable, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Ensure non-ASCII output works on Windows consoles (cp1252 by default).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    p = argparse.ArgumentParser(prog="crdis", description="Crystal Reports .rpt disassembler")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="Show stream inventory and summary properties.")
    p_info.add_argument("file")
    p_info.set_defaults(func=_cmd_info)

    p_dump = sub.add_parser("dump", help="Extract every stream as a separate .bin file.")
    p_dump.add_argument("file")
    p_dump.add_argument("-o", "--out", default="streams", help="Output directory (default: ./streams).")
    p_dump.set_defaults(func=_cmd_dump)

    p_sum = sub.add_parser("summary-json", help="Emit summary properties as JSON.")
    p_sum.add_argument("file")
    p_sum.set_defaults(func=_cmd_summary_json)

    p_dec = sub.add_parser("decrypt", help="Decrypt + inflate the Contents stream.")
    p_dec.add_argument("file")
    p_dec.add_argument("-o", "--out", default=None, help="Output path (default: FILE.contents.bin).")
    p_dec.set_defaults(func=_cmd_decrypt)

    p_rec = sub.add_parser("records", help="Decrypt and parse the inner CSArchive record stream.")
    p_rec.add_argument("file")
    p_rec.add_argument("--recurse", action="store_true", help="Recurse into nested records when value bytes look like a record header.")
    p_rec.add_argument("--summary", action="store_true", help="Print tag histogram instead of full record dump.")
    p_rec.add_argument("--limit", type=int, default=30, help="Max records to show (default 30).")
    p_rec.set_defaults(func=_cmd_records)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
