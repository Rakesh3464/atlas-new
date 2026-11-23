#!/usr/bin/env python3
"""Read-only Samsung A21s (SM-A217F) input audit.
Usage: python3 scripts/a21s_ui9_input_audit.py boot.img dtbo.img vendor.zip reports/a21s-inputs.md
No modifications, unpacking to disk, or flashing occur.
"""
import hashlib
import io
import struct
import sys
import zipfile
from pathlib import Path

MiB = 1024 * 1024

def digest_file(path):
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def inspect_boot(path):
    with path.open("rb") as f:
        head = f.read(4096)
    out = [f"Size: {path.stat().st_size} bytes ({path.stat().st_size / MiB:.2f} MiB)",
           f"SHA-256: {digest_file(path)}"]
    if head[:8] != b"ANDROID!":
        out.append("MAGIC FAIL: not a standard Android boot image. Do not flash before identification.")
        return out, False
    out.append("MAGIC PASS: ANDROID!")
    kernel_size = struct.unpack_from("<I", head, 8)[0]
    out.append(f"First header word (kernel size on legacy boot image): {kernel_size} bytes")
    if not 0 < kernel_size < path.stat().st_size:
        out.append("WARNING: legacy kernel-size interpretation invalid; inspect boot header version.")
    # Legacy page size is at offset 36; Android boot v3/v4 differs.
    page_size_candidate = struct.unpack_from("<I", head, 36)[0]
    out.append(f"Legacy page-size candidate at offset 36: {page_size_candidate}")
    if page_size_candidate in (2048, 4096, 8192, 16384):
        out.append("Legacy Android boot header probable; verify header version with unpack_bootimg.")
    return out, True

def inspect_dtbo(path):
    with path.open("rb") as f:
        head = f.read(64)
    out = [f"Size: {path.stat().st_size} bytes ({path.stat().st_size / MiB:.2f} MiB)",
           f"SHA-256: {digest_file(path)}"]
    magic = struct.unpack_from(">I", head, 0)[0]
    if magic == 0xd7b7ab1e:
        total_size, header_size, entry_size, entry_count, entry_offset, page_size, version = struct.unpack_from(">7I", head, 4)
        out += ["MAGIC PASS: standard Android DTBO table",
                f"Header total bytes: {total_size}",
                f"Header bytes: {header_size}",
                f"DT entry size: {entry_size}",
                f"DT entries: {entry_count}",
                f"DT entry offset: {entry_offset}",
                f"Page size: {page_size}",
                f"Version: {version}"]
        okay=(total_size <= path.stat().st_size and 32 <= header_size <= 4096
              and 0 < entry_size <= 4096 and 0 < entry_count < 8192)
        if not okay:
            out.append("WARNING: DTBO header metadata does not pass sanity checks")
        return out, okay
    out.append(f"MAGIC FAIL/UNKNOWN: first 4 bytes 0x{magic:08x}")
    out.append("This may use Samsung-specific wrapping. Do not flash before verification.")
    return out, False

def inspect_vendor(path):
    out = [f"Size: {path.stat().st_size} bytes ({path.stat().st_size / MiB:.2f} MiB)",
           f"SHA-256: {digest_file(path)}"]
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos) > 500000:
            raise ValueError("Unexpectedly many ZIP entries")
        out.append(f"ZIP entries: {len(infos)}")
        out.append(f"Total uncompressed bytes: {sum(i.file_size for i in infos)}")
        out.append("## Largest ZIP members")
        for i in sorted(infos, key=lambda x:x.file_size,reverse=True)[:25]:
            out.append(f"- {i.filename}: {i.file_size} bytes")
        names=[i.filename for i in infos]
        low=[n.lower() for n in names]
        out.append("## Vendor format candidates")
        candidates=[n for n in names if n.lower().endswith((
            "vendor.img", "vendor.new.dat", "vendor.new.dat.br", "vendor.transfer.list",
            "vendor/build.prop", "vendor/etc/vintf/manifest.xml",
            "vendor/etc/vintf/compatibility_matrix.xml", "super.img"
        ))]
        out.extend("- "+n for n in candidates[:60])
        if not candidates:
            out.append("No obvious vendor payload detected by filename; manual inspection required")
        out.append("## Property lines (only for text files directly stored in ZIP)")
        prop_members = [n for n in names if n.lower().endswith(("vendor/build.prop","vendor/default.prop"))]
        for n in prop_members[:5]:
            info = z.getinfo(n)
            if info.file_size > 10 * MiB:
                continue
            content=z.read(n).decode("utf-8", errors="replace")
            for line in content.splitlines():
                if line.startswith(("ro.vendor.build.version.sdk=",
                                    "ro.vndk.version=",
                                    "ro.product.vendor.device=",
                                    "ro.vendor.build.fingerprint=",
                                    "ro.vendor.build.version.release=")):
                    out.append(f"- {n}: {line[:400]}")
        # Avoid expensive full decompression if a huge vendor image is present;
        # zipfile integrity has been verified structurally with central directory.
        out.append("ZIP central directory read: PASS (full per-file CRC not checked here)")
    return out, True

def main():
    if len(sys.argv)!=5:
        sys.exit("Usage: a21s_ui9_input_audit.py boot.img dtbo.img vendor.zip report.md")
    boot,dtbo,vendor,outpath=map(Path,sys.argv[1:])
    if not all(p.is_file() for p in (boot,dtbo,vendor)):
        raise SystemExit("MISSING INPUT: boot.img, dtbo.img and vendor.zip all required")
    sections=[]
    checks=[]
    for title, func, filename in [
        ("A21s boot.img", inspect_boot, boot),
        ("A21s dtbo.img", inspect_dtbo, dtbo),
        ("A21s vendor.zip", inspect_vendor, vendor)]:
        rows,okay=func(filename)
        checks.append(okay)
        sections.extend([f"## {title}", *rows, ""])
    result="\n".join([
        "# A21s One UI 9 input audit (NO FLASH)",
        "",
        "Target: SM-A217F / Exynos 850; donor: SkyUI Cirrus 9 for M21/M31/M31s/F41",
        "This report validates signatures and archive contents only; no device ABI compatibility or bootability is certified.",
        "",
        *sections,
        f"Input signature checks passed: {sum(checks)} / {len(checks)}",
        "No ROM was built and these files are NOT automatically flash-ready.",
        "A21s super partition size/layout and actual VINTF compatibility must be checked before image repacking.",
        ""
    ])
    outpath.parent.mkdir(parents=True,exist_ok=True)
    outpath.write_text(result)
    print(result)

if __name__=="__main__":
    main()
