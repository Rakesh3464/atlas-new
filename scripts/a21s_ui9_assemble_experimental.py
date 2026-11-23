#!/usr/bin/env python3
"""Build an EXPERIMENTAL A21s One UI9 super image, never flash-ready by default.

This script consumes independently audited images. The --super-byte-size is
USER-REPORTED ONLY (exact target physical size has not been confirmed).
It keeps OEM Samsung A21s boot, DTBO and vendor unmodified.

Do not flash the output. Device VINTF, SELinux, boot and PIT geometry are unverified.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

from a21s_ui9_donor_vendor_compat import lp_partitions

MIB=1024*1024
DONOR_SHA="60a39482f3baba166627c4b784ad103fc0f10f83c36148291fb91071bcf7eb86"
VENDOR_SHA="39c3315fa5f164e1ddeba3fd2cfae85240e21a5ac61d8287d34e0b1b42136385"
BOOT_SHA="924d4b84802c5909cf7b4dc3f30382b4c7e35c1791a4ea344a179e4218a70632"
DTBO_SHA="acedb9d9e174e1348740150244ff0534610edf30f804538c7cc8c714013f8c29"
PARTITIONS={"system":4878610432,"odm":20971520}
VENDOR_SIZE=846389248
PRODUCT_EXT4_SIZE=1719664640
SUPER_INPUT_SIZE=6382682112
ASSUMED_DEVICE_SIZE=10_000_000_000

def checksum(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(16*MIB),b""):h.update(chunk)
    return h.hexdigest()

def check(path,sha,label):
    actual=checksum(path)
    if actual!=sha:
        raise ValueError(f"{label} SHA mismatch: {actual}")
    print(f"{label} SHA OK",flush=True)

def copy_extent(src,offset,length,dst):
    with src.open("rb") as inp,dst.open("wb") as out:
        inp.seek(offset)
        remaining=length
        while remaining:
            b=inp.read(min(16*MIB,remaining))
            if not b: raise EOFError(f"Unexpected EOF reading {src} at {offset}")
            out.write(b)
            remaining-=len(b)

def check_ext4(img):
    with img.open("rb") as f:
        f.seek(1080)
        if f.read(2)!=b"\x53\xef":
            raise ValueError(f"Not an ext4 filesystem: {img}")

def run(args):
    print("$ "+ " ".join(map(str,args[:10]))+(" ..." if len(args)>10 else ""),flush=True)
    subprocess.run([str(x) for x in args],check=True)

def main():
    if len(sys.argv)!=9:
        sys.exit("Usage: assemble.py donor-super.img vendor.zip boot.img dtbo.img product.ext4.img lpmake-bin output-dir report-dir")
    srcsuper,vendorzip,boot,dtbo,product,lpmake,output,report=map(Path,sys.argv[1:])
    output.mkdir(parents=True,exist_ok=True);report.mkdir(parents=True,exist_ok=True)
    work=Path("work")
    work.mkdir(exist_ok=True)
    # These checksums come from previous GitHub Actions runs.
    check(vendorzip,VENDOR_SHA,"A21s vendor ZIP")
    check(boot,BOOT_SHA,"A21s boot")
    check(dtbo,DTBO_SHA,"A21s DTBO")
    if srcsuper.stat().st_size!=SUPER_INPUT_SIZE:
        raise ValueError("Donor super.img size mismatch")
    with boot.open("rb") as f:
        if f.read(8)!=b"ANDROID!": raise ValueError("boot magic invalid")
    with dtbo.open("rb") as f:
        if f.read(4)!=bytes.fromhex("d7b7ab1e"): raise ValueError("dtbo magic invalid")
    parts=lp_partitions(srcsuper)
    for n,exp in PARTITIONS.items():
        if n not in parts or parts[n]["bytes"]!=exp:
            raise ValueError(f"Donor partition missing/size mismatch: {n}")
        copy_extent(srcsuper,parts[n]["offset"],exp,work/(n+".img"))
        check_ext4(work/(n+".img"))
    if product.stat().st_size!=PRODUCT_EXT4_SIZE:
        raise ValueError("Converted product ext4 size mismatch")
    check_ext4(product)
    with zipfile.ZipFile(vendorzip) as z:
        ims=[x for x in z.infolist() if x.filename.rsplit("/",1)[-1]=="vendor.img"]
        if len(ims)!=1 or ims[0].file_size!=VENDOR_SIZE:
            raise ValueError("Unexpected A21s vendor.img in ZIP")
        with z.open(ims[0]) as f,(work/"vendor.img").open("wb") as w:
            shutil.copyfileobj(f,w,16*MIB)
    check_ext4(work/"vendor.img")
    images={
        "system":work/"system.img",
        "product":product,
        "odm":work/"odm.img",
        "vendor":work/"vendor.img",
    }
    sizes={k:v.stat().st_size for k,v in images.items()}
    if sum(sizes.values())+128*MIB>=ASSUMED_DEVICE_SIZE:
        raise ValueError("Images too large for assumed 10GB device")
    group_capacity=9_000_000_000
    args=[lpmake,"--metadata-size","65536",
          "--super-name","super","--metadata-slots","2",
          "--device-size",str(ASSUMED_DEVICE_SIZE),
          "--alignment",str(MIB),"--group",f"group_basic:{group_capacity}",
          "--block-size","4096"]
    for name,img in images.items():
        size=img.stat().st_size
        args+=["--partition",f"{name}:readonly:{size}:group_basic","--image",f"{name}={img}"]
    result=output/"super-10GB-GUESS-UNVERIFIED.img"
    args+=["--sparse","--output",result]
    run(args)
    with result.open("rb") as f:
        magic=f.read(4)
    if magic!=bytes.fromhex("3aff26ed"):
        raise ValueError("Expected Android sparse super image; got "+magic.hex())
    shutil.copy2(boot,output/"boot-a21s-original.img")
    shutil.copy2(dtbo,output/"dtbo-a21s-original.img")
    # These files explicitly prevent mistaking prototype for a tested ROM.
    notice=(
        "SAMSUNG GALAXY A21s SM-A217F - ONE UI 9 EXPERIMENTAL ASSEMBLY\n"
        "!!! THIS IS NOT FLASH-READY, DO NOT FLASH !!!\n"
        "Generated with a GUESSED 10,000,000,000-byte physical super size;\n"
        "actual target PIT/LP geometry, boot/SELinux/VINTF, AVB have NOT been validated.\n"
        "This assembly combines donor Android 17 system/product/odm with\n"
        "Android 12 VNDK31 A21s vendor, boot and dtbo. Hardware is not tested.\n"
        "DONOR super.img, vendor, boot and DTBO were never flashed.\n"
        "The product partition was copied from EROFS to ext4 with SELinux xattrs.\n"
        "Do NOT flash or treat this package as a working One UI 9 A21s ROM.\n"
    )
    (output/"DO_NOT_FLASH_README.txt").write_text(notice)
    manifest={
      "target":"Samsung SM-A217F / Exynos 850",
      "donor":"SkyUI Cirrus 9 M21/M31/M31s/F41",
      "donor_android":"17 (API 37)",
      "target_vendor_android":"12 (API31/VNDK31)",
      "user_reported_super":"10 GB",
      "lpmake_assumed_device_size_bytes":ASSUMED_DEVICE_SIZE,
      "metadata_slots_assumed":2,
      "images":{k:{"byte_size":v.stat().st_size,"sha256":checksum(v)} for k,v in images.items()},
      "result_super":result.name,
      "output_size":result.stat().st_size,
      "output_sha256":checksum(result),
      "boot_sha256":checksum(boot),
      "dtbo_sha256":checksum(dtbo),
      "verified_bootable":False,
      "safe_to_flash":False,
      "warnings":[
          "Assumed super geometry may be wrong: physical super size not verified",
          "Donor framework Android 17 and VNDK31 Android12 target compatibility not established",
          "No Android on-device boot, VINTF or SELinux policy check",
          "No Odin/TWRP install script is provided for this UNTESTED assembly",
      ]
    }
    (output/"BUILD_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (report/"ASSEMBLY_REPORT.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (report/"DO_NOT_FLASH_README.txt").write_text(notice)
    for p in output.iterdir():
        print(f"OUTPUT {p.name}: {p.stat().st_size} bytes",flush=True)

if __name__=="__main__":
    main()
