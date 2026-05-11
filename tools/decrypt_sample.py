#!/usr/bin/env python3
"""Decrypt + inflate the Contents stream of a Crystal Reports .rpt file."""
import sys, olefile
sys.path.insert(0, ".")
from crdis.codec.cslibu_aes import decrypt_contents_stream

if len(sys.argv) < 2:
    sys.exit("usage: decrypt_sample.py FILE.rpt [FILE2.rpt ...]")

for path in sys.argv[1:]:
    with olefile.OleFileIO(path) as ole:
        body = ole.openstream("Contents").read()
    plain = decrypt_contents_stream(body)
    out_path = path.rsplit(".", 1)[0] + ".contents.bin"
    open(out_path, "wb").write(plain)
    print(f"{path}: encrypted {len(body)} bytes -> plaintext {len(plain)} bytes -> {out_path}")
