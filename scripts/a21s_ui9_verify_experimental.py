#!/usr/bin/env python3
"""Validate every partition of EXPERIMENTAL super after expanding sparse to raw.

No flashing. Ensures each LP partition extent bytes exactly match its input.
"""
import hashlib
import json
import sys
from pathlib import Path
from a21s_ui9_donor_vendor_compat import lp_partitions

def digest(src,offset,length):
    h=hashlib.sha256()
    with src.open("rb") as f:
        f.seek(offset)
        while length:
            b=f.read(min(length,16*1024*1024))
            if not b:raise EOFError("Unexpected EOF")
            h.update(b)
            length-=len(b)
    return h.hexdigest()

def main():
    if len(sys.argv)!=3:
        sys.exit("Usage: verify_super.py raw_super.img BUILD_MANIFEST.json")
    raw=Path(sys.argv[1])
    manifest=json.loads(Path(sys.argv[2]).read_text())
    if raw.stat().st_size!=manifest["lpmake_assumed_device_size_bytes"]:
        raise ValueError("Raw prototype super has wrong assumed physical size")
    parts=lp_partitions(raw)
    print("Prototype LP partitions:",{k:v["bytes"] for k,v in parts.items()},flush=True)
    for name,info in manifest["images"].items():
        part=parts.get(name)
        if part is None or part["bytes"]!=info["byte_size"]:
            raise ValueError("Wrong LP partition size for "+name)
        actual=digest(raw,part["offset"],part["bytes"])
        if actual!=info["sha256"]:
            raise ValueError("Prototype raw LP partition checksum mismatch: "+name)
        print("Verified partition payload:",name,actual,flush=True)
    print("PROTOTYPE LP VALIDATION PASSED, BOOTABILITY NOT TESTED. DO NOT FLASH.",flush=True)

if __name__=="__main__":
    main()
