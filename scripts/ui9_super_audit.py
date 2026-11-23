#!/usr/bin/env python3
"""Read AOSP liblp metadata from donor super.img inside a ZIP. Read-only audit.

Reference: https://android.googlesource.com/platform/system/core/+/master/fs_mgr/liblp/include/liblp/metadata_format.h
This is *not* a flash, repack, or port implementation.
"""
import hashlib
import struct
import sys
import zipfile
from pathlib import Path

LP_GEOMETRY_MAGIC = 0x616c4467
LP_HEADER_MAGIC = 0x414C5030
SPARSE_MAGIC = 0xED26FF3A
PREFIX_BYTES = 8 * 1024 * 1024
READ_BYTES = 16 * 1024 * 1024

def u32(buf, offset):
    return struct.unpack_from("<I", buf, offset)[0]

def parse_sparse_prefix(src, limit=PREFIX_BYTES):
    if len(src) < 28:
        raise ValueError("Sparse image header too short")
    file_hdr = struct.unpack_from("<H", src, 8)[0]
    chunk_hdr = struct.unpack_from("<H", src, 10)[0]
    block_sz = u32(src, 12)
    chunks = u32(src, 20)
    if not 28 <= file_hdr <= 4096 or not 12 <= chunk_hdr <= 4096 or not 512 <= block_sz <= (1 << 20):
        raise ValueError("Unexpected Android sparse geometry")
    pos = file_hdr
    out = bytearray()
    for _ in range(chunks):
        if len(out) >= limit:
            break
        if pos + chunk_hdr > len(src):
            raise ValueError("Need more compressed-stream bytes for sparse chunks")
        typ, _, block_count, total_sz = struct.unpack_from("<HHII", src, pos)
        if total_sz < chunk_hdr:
            raise ValueError("Bad sparse chunk size")
        pos += chunk_hdr
        out_sz = block_count * block_sz
        needed = min(out_sz, limit - len(out))
        if typ == 0xCAC1:       # RAW
            if pos + needed > len(src):
                raise ValueError("Sparse RAW prefix incomplete")
            out.extend(src[pos:pos + needed])
        elif typ == 0xCAC2:     # FILL
            if pos + 4 > len(src):
                raise ValueError("Sparse FILL prefix incomplete")
            fill = src[pos:pos + 4]
            out.extend((fill * ((needed + 3) // 4))[:needed])
        elif typ == 0xCAC3:     # DONT_CARE
            out.extend(b"\x00" * needed)
        elif typ == 0xCAC4:     # CRC
            pass
        else:
            raise ValueError("Unknown sparse chunk type: 0x%x" % typ)
        pos += total_sz - chunk_hdr
    return bytes(out)

def checked_table(prefix, metadata_offset, header_size, table_size, descriptor_offset, min_entry):
    offset, count, size = struct.unpack_from("<III", prefix, metadata_offset + descriptor_offset)
    if count > 4096 or size < min_entry or offset + count * size > table_size:
        raise ValueError("Invalid LP descriptor at header offset %d" % descriptor_offset)
    beginning = metadata_offset + header_size + offset
    if beginning + count * size > len(prefix):
        raise ValueError("Incomplete LP table in prefix")
    return [(beginning + i * size, size) for i in range(count)]

def read_report(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        match = [n for n in z.namelist() if n.rsplit("/", 1)[-1].lower() == "super.img"]
        if len(match) != 1:
            raise ValueError("Exactly one super.img was expected; found %d" % len(match))
        item = z.getinfo(match[0])
        with z.open(item) as stream:
            file_prefix = stream.read(READ_BYTES)
    if len(file_prefix) < 16384:
        raise ValueError("super.img is too small")
    magic = u32(file_prefix, 0)
    sparse = magic == SPARSE_MAGIC
    prefix = parse_sparse_prefix(file_prefix) if sparse else file_prefix[:PREFIX_BYTES]
    if len(prefix) < 16384 or u32(prefix, 4096) != LP_GEOMETRY_MAGIC:
        raise ValueError("LP geometry missing at 4096 in first raw-image bytes")
    geometry_size = u32(prefix, 4100)
    max_meta = u32(prefix, 4136)
    slots = u32(prefix, 4140)
    logical_block_size = u32(prefix, 4144)
    if geometry_size != 52 or not (512 <= max_meta <= 1024 * 1024) or not (1 <= slots <= 4):
        raise ValueError("Suspicious LP geometry dimensions")
    geom = bytearray(prefix[4096:4096 + geometry_size])
    checksum = bytes(geom[8:40])
    geom[8:40] = b"\x00" * 32
    if hashlib.sha256(geom).digest() != checksum:
        raise ValueError("LP geometry SHA256 mismatch")
    meta_at = 4096 + 2 * 4096
    if u32(prefix, meta_at) != LP_HEADER_MAGIC:
        raise ValueError("LP primary metadata magic missing")
    major, minor, head_size = struct.unpack_from("<HHI", prefix, meta_at + 4)
    if major != 10 or not 128 <= head_size <= 4096:
        raise ValueError("Unsupported LP metadata version/size")
    table_size = u32(prefix, meta_at + 44)
    if table_size > max_meta or meta_at + head_size + table_size > len(prefix):
        raise ValueError("LP table too large for captured prefix")
    head = bytearray(prefix[meta_at:meta_at + head_size])
    expected_header = bytes(head[12:44])
    head[12:44] = b"\x00" * 32
    if hashlib.sha256(head).digest() != expected_header:
        raise ValueError("LP metadata header SHA256 mismatch")
    table_bytes = prefix[meta_at + head_size:meta_at + head_size + table_size]
    if hashlib.sha256(table_bytes).digest() != prefix[meta_at + 48:meta_at + 80]:
        raise ValueError("LP metadata table checksum mismatch")

    parts = checked_table(prefix, meta_at, head_size, table_size, 80, 52)
    exts = checked_table(prefix, meta_at, head_size, table_size, 92, 24)
    groups = checked_table(prefix, meta_at, head_size, table_size, 104, 48)
    devices = checked_table(prefix, meta_at, head_size, table_size, 116, 64)
    get_name = lambda data: data.split(b"\x00", 1)[0].decode("ascii", errors="replace")
    names = [get_name(prefix[p:p + 36]) for p, _ in groups]
    lines = [
        "# SkyUI Cirrus 9 donor super.img LP metadata",
        "",
        "READ-ONLY inspection; not for flashing, not a port build.",
        f"super.img format: {'Android sparse' if sparse else 'raw'}",
        f"super.img ZIP entry uncompressed bytes: {item.file_size}",
        f"LP metadata version: {major}.{minor}",
        f"LP metadata slots: {slots}",
        f"Logical block size: {logical_block_size}",
        f"LP metadata maximum bytes per slot: {max_meta}",
        f"LP block device count: {len(devices)}",
        "",
        "## LP block devices",
    ]
    for pos, _ in devices:
        dev_size = struct.unpack_from("<Q", prefix, pos + 16)[0]
        dev_name = get_name(prefix[pos + 24:pos + 60])
        lines.append(f"- {dev_name}: {dev_size} bytes ({dev_size / 2**30:.2f} GiB)")
    lines += ["", "## LP partitions"]
    for pos, _ in parts:
        name = get_name(prefix[pos:pos + 36])
        attrs, first, n_extents, group_idx = struct.unpack_from("<IIII", prefix, pos + 36)
        if first + n_extents > len(exts):
            raise ValueError("Invalid extent references for partition " + name)
        size_bytes = sum(struct.unpack_from("<Q", prefix, exts[i][0])[0] * 512
                         for i in range(first, first + n_extents))
        group = names[group_idx] if group_idx < len(names) else f"unknown-{group_idx}"
        lines.append(f"- {name}: {size_bytes} bytes ({size_bytes / 2**30:.3f} GiB), "
                     f"extents={n_extents}, group={group}, attrs=0x{attrs:x}")
    lines += ["", "## Required precautions",
              "- Do not flash this donor super.img to Samsung A21s SM-A217F.",
              "- Compare donor partition sizes with actual A21s super layout and filesystem / vendor ABI.",
              "- Keep A21s hardware-specific boot, dtbo, vendor and radio stacks."]
    return "\n".join(lines) + "\n"

def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python3 scripts/ui9_super_audit.py donor.zip reports/super-audit.md")
    result = read_report(sys.argv[1])
    path = Path(sys.argv[2])
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(result)
    print(result)

if __name__ == "__main__":
    main()
