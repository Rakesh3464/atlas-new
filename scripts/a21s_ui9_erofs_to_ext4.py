#!/usr/bin/env python3
"""Convert ONLY donor product from EROFS to ext4, preserving xattrs on hosted Linux.
This is an UNTESTED PARTITION IMAGE, NOT a flashable ROM or super.img.
Requires root, rsync, losetup, mount with kernel EROFS support, mkfs.ext4.
"""
import hashlib
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from a21s_ui9_donor_vendor_compat import lp_partitions

MIB = 1048576
EXPECTED_DONOR_SUPER = 6382682112
EXPECTED_DONOR_PRODUCT = 676745216
TARGET_SUPER_ASSUMED = 10_000_000_000
SYSTEM_BYTES = 4878610432
ODM_BYTES = 20971520
A21S_VENDOR_BYTES = 846389248
RESERVE_BYTES = 32 * MIB

def cmd(*args, capture=False):
    if capture:
        return subprocess.check_output(list(map(str,args)), text=True, stderr=subprocess.STDOUT).strip()
    subprocess.run(list(map(str,args)), check=True)

def align(n):
    return (n + MIB-1)//MIB*MIB

def collect_security_labels(folder, maximum=200):
    samples=[]
    failures=[]
    for root,dirs,files in os.walk(folder,followlinks=False):
        for filename in ["."] + dirs + files:
            path=Path(root) if filename=="." else Path(root,filename)
            try:
                label=os.getxattr(path,"security.selinux",follow_symlinks=False)
                relative=path.relative_to(folder)
                samples.append((relative,label))
                if len(samples)>=maximum:
                    return samples,failures
            except OSError as e:
                if e.errno not in (61,95,2):
                    failures.append(f"{path}: errno {e.errno}")
                    if len(failures)>=5:
                        return samples,failures
    return samples,failures

def main(super_path,outimg,report):
    if os.geteuid()!=0:
        raise SystemExit("Root required on isolated GitHub runner to preserve UID/GID and SELinux xattrs")
    super_path=super_path.resolve()
    if super_path.stat().st_size!=EXPECTED_DONOR_SUPER:
        raise ValueError("Donor super size differs from independently audited image")
    parts=lp_partitions(super_path)
    product=parts.get("product")
    if not product or product["bytes"]!=EXPECTED_DONOR_PRODUCT:
        raise ValueError("Unexpected donor product extent")
    report.parent.mkdir(parents=True,exist_ok=True)
    outimg.parent.mkdir(parents=True,exist_ok=True)
    loop=None
    erofs_mounted=False
    ext4_mounted=False
    lines=[
        "# A21s One UI 9 Donor product EROFS -> ext4",
        "",
        "Conversion only. A21s-compatible ROM booting and VNDK/VINTF remain unverified.",
        f"Donor product input bytes: {product['bytes']}",
        f"Donor raw super offset: {product['offset']}",
        "Android SELinux xattrs, ownership, symlinks, hardlinks and capabilities are copied where supported.",
        "",
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="a21s-product-") as temporary:
            tmp=Path(temporary)
            src=tmp/"erofs"
            dst=tmp/"ext4"
            src.mkdir();dst.mkdir()
            try:
                loop=cmd("losetup","--find","--show","--read-only",
                         "--offset",product["offset"],"--sizelimit",product["bytes"],
                         super_path,capture=True)
                fstype=cmd("blkid","-p","-o","value","-s","TYPE",loop,capture=True)
                lines.append(f"Source filesystem confirmed: {fstype}")
                if fstype!="erofs":
                    raise ValueError("Expected EROFS source, found "+fstype)
                cmd("mount","-t","erofs","-o","ro,nodev,nosuid",loop,src)
                erofs_mounted=True
                apparent=int(cmd("du","-sb",src,capture=True).split()[0])
                lines.append(f"Source apparent content size: {apparent} bytes")
                labels,scan_errors=collect_security_labels(src)
                lines.append(f"Sampled source security.selinux xattrs: {len(labels)}")
                if scan_errors: lines.append("Source label read errors: "+repr(scan_errors))
                # Size the uncompressed ext4 filesystem generously, but never exceed
                # conservative arithmetic budget on the user-reported decimal 10 GB super.
                size=align(max(1600*MIB, math.ceil(apparent*1.45+320*MIB)))
                max_product=TARGET_SUPER_ASSUMED-SYSTEM_BYTES-ODM_BYTES-A21S_VENDOR_BYTES-RESERVE_BYTES
                lines.append(f"Super-size arithmetic maximum for product: {max_product} bytes (not verified block-device size)")
                if size>max_product:
                    raise ValueError(f"Ext4 product image {size} exceeds 10 GB provisional allocation budget {max_product}")
                lines.append(f"Selected output ext4 image size: {size} bytes")
                with outimg.open("wb") as w:
                    w.truncate(size)
                cmd("mkfs.ext4","-F","-m","0","-L","product","-b","4096",
                    "-E","lazy_itable_init=0,lazy_journal_init=0",outimg)
                cmd("mount","-t","ext4","-o","loop",outimg,dst)
                ext4_mounted=True
                cmd("rsync","-aHAX","--numeric-ids","--one-file-system",
                    "--",str(src)+"/",str(dst)+"/")
                # -c verifies contents, -H hardlinks, -A ACLs, -X xattrs.
                dryrun=cmd("rsync","-nrcaHAX","--numeric-ids","--one-file-system",
                           "--delete","--itemize-changes","--",
                           str(src)+"/",str(dst)+"/",capture=True)
                if dryrun:
                    lines.append("Dry-run rsync mismatch:\n"+dryrun[:3000])
                    raise ValueError("Post-copy file or metadata mismatch")
                lines.append("Rsync checksum and metadata dry-run: CLEAN")
                problems=[]
                for rel,label in labels:
                    try:
                        dst_label=os.getxattr(dst/rel,"security.selinux",follow_symlinks=False)
                        if label!=dst_label:
                            problems.append(str(rel))
                    except OSError as e:
                        problems.append(f"{rel} missing SELinux label: errno {e.errno}")
                if problems:
                    lines.append("SELinux label mismatch paths: "+repr(problems[:30]))
                    raise ValueError("SELinux xattrs were not preserved")
                lines.append(f"SELinux xattrs verified on {len(labels)} sampled inodes")
                if not labels:
                    lines.append("WARNING: Source has no accessible security.selinux labels; cannot verify Android SELinux labeling")
                cmd("sync")
                cmd("umount",dst)
                ext4_mounted=False
                fsck=subprocess.run(["e2fsck","-f","-n",str(outimg)],capture_output=True,text=True,timeout=240)
                lines.append(f"Ext4 read-only e2fsck exit: {fsck.returncode}")
                lines.append("e2fsck tail: "+(fsck.stdout+"\n"+fsck.stderr)[-1400:])
                if fsck.returncode!=0:
                    raise ValueError("ext4 filesystem fails read-only e2fsck")
                output_type=cmd("blkid","-p","-o","value","-s","TYPE",outimg,capture=True)
                lines.append("Output filesystem confirmed: "+output_type)
                if output_type!="ext4":
                    raise ValueError("Converted filesystem not ext4")
            finally:
                if ext4_mounted:
                    subprocess.run(["umount",str(dst)],check=False)
                if erofs_mounted:
                    subprocess.run(["umount",str(src)],check=False)
                    erofs_mounted=False
                if loop:
                    subprocess.run(["losetup","-d",loop],check=False)
                    loop=None
        sha=hashlib.sha256()
        with outimg.open("rb") as f:
            for block in iter(lambda:f.read(16*MIB),b""):
                sha.update(block)
        lines.extend(["",f"Output image SHA-256: {sha.hexdigest()}",
                      "Output: ext4 partition image ONLY.",
                      "FLASH-READY A21s ROM: NO. Need verified target super geometry, VINTF, and an integration/boot test.",
                      "Do NOT flash directly over unknown super layout."])
        report.write_text("\n".join(lines)+"\n")
        print(report.read_text(),flush=True)
    except Exception as exc:
        lines.extend(["","CONVERSION FAILED: "+str(exc)[:1000],
                      "NO VERIFIED IMAGE MUST BE FLASHED."])
        report.write_text("\n".join(lines)+"\n")
        raise

if __name__=="__main__":
    if len(sys.argv)!=4:
        sys.exit("Usage: script.py input-donor-super.img output-product.ext4.img report.md")
    main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
