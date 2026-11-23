#!/usr/bin/env python3
"""Read-only audit of A21s boot.img, dtbo.img and vendor.zip.
Aimed at One UI 9 port preparation. Never edits images or flashes a device.
Usage: python3 scripts/a21s_ui9_hardware_audit.py boot.img dtbo.img vendor.zip report.md
"""
import hashlib
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MIB=1024*1024

def u32_le(b,pos):
    return struct.unpack_from("<I",b,pos)[0]

def u32_be(b,pos):
    return struct.unpack_from(">I",b,pos)[0]

def image_format(path):
    with open(path,"rb") as f:
        data=f.read(8192)
    if data.startswith(b"ANDROID!"): return "Android boot image"
    if data.startswith(b"\x3a\xff\x26\xed"): return "Android sparse image"
    if data.startswith(b"\xe0\xf5\xe1\xe2"): return "EROFS (offset 0)"
    if len(data)>1082 and data[1080:1082]==b"\x53\xef": return "raw ext4"
    if len(data)>1028 and data[1024:1028]==b"\xe2\xe1\xf5\xe0": return "EROFS (offset 1024)"
    if data.startswith(b"PK\x03\x04"): return "ZIP"
    return "Unrecognized image"

def audit_boot(path):
    data=Path(path).read_bytes()[:4096]
    out=["## Boot image",f"Size: {Path(path).stat().st_size} bytes",
         f"Magic: {data[:8]!r}"]
    if data[:8] != b"ANDROID!":
        return out + ["WARN: Android boot magic not present"]
    fields=[
        ("kernel_size",8),("kernel_addr",12),("ramdisk_size",16),
        ("ramdisk_addr",20),("second_size",24),("second_addr",28),
        ("tags_addr",32),("page_size",36),("header_version",40),("os_version",44),
    ]
    out.extend(f"{name}: {u32_le(data,pos)}" for name,pos in fields)
    page=u32_le(data,36)
    version=u32_le(data,40)
    out += [
        f"Legacy boot layout probable: {str(page in (2048,4096,8192,16384) and version in (0,1,2)).lower()}",
        "Boot content is for analysis only; no boot.img was repacked."
    ]
    return out


def inspect_boot_ramdisk(path):
    """Read the stock boot ramdisk in memory; never unpack it to an output image."""
    import gzip
    out=["## Boot ramdisk fstab and mount metadata"]
    data=Path(path).read_bytes()
    if data[:8]!=b"ANDROID!":
        return out+["Boot header unknown"]
    page=u32_le(data,36)
    kernel=u32_le(data,8)
    rsize=u32_le(data,16)
    if page not in (2048,4096,8192,16384) or rsize>64*MIB:
        return out+["Invalid legacy boot layout"]
    offset=page+((kernel+page-1)//page)*page
    if offset+rsize>len(data):
        return out+["Ramdisk outside boot image"]
    blob=data[offset:offset+rsize]
    out.append(f"Ramdisk offset: {offset}, bytes: {rsize}")
    out.append(f"Ramdisk signature: {blob[:12].hex()}")
    if blob.startswith(b"\x1f\x8b"):
        decoded=gzip.decompress(blob)
        out.append("Ramdisk compression: gzip")
    elif blob.startswith(b"\x04\x22\x4d\x18") or blob.startswith(b"\x02\x21\x4c\x18"):
        kind="lz4"
        if not shutil.which(kind):
            return out+["LZ4 ramdisk detected; lz4 tool unavailable"]
        p=subprocess.run(["lz4","-d","-c"],input=blob,capture_output=True,timeout=30)
        if p.returncode: return out+["Could not decode LZ4 ramdisk"]
        decoded=p.stdout
        out.append("Ramdisk compression: lz4")
    else:
        decoded=blob
        out.append("Ramdisk compression: raw/unknown")
    if len(decoded)>128*MIB:
        return out+["Refusing oversized ramdisk"]
    i=0
    matches=[]
    while i+110<=len(decoded):
        hdr=decoded[i:i+110]
        if hdr[:6] not in (b"070701",b"070702"):
            if i==0: out.append("No cpio newc entries detected")
            break
        try:
            size=int(hdr[54:62],16)
            nsize=int(hdr[94:102],16)
        except ValueError:
            break
        if nsize<1 or nsize>4096 or size>80*MIB: break
        name_bytes=decoded[i+110:i+110+nsize]
        name=name_bytes.split(b"\x00",1)[0].decode("utf-8","replace")
        dstart=(i+110+nsize+3)//4*4
        dend=dstart+size
        if dend>len(decoded):break
        if name=="TRAILER!!!":break
        if ("fstab" in name.lower() or name.lower().endswith(".rc")) and size<256*1024:
            contents=decoded[dstart:dend].decode("utf-8","replace")
            hits=[line.strip() for line in contents.splitlines() if
                 ("fstab" in name.lower() and
                  any(q in line.split() for q in ("/system","/vendor","/product","/odm")))
                 or ("fstab" in line and name.lower().endswith(".rc"))]
            if hits: matches.append((name,hits[:30]))
        i=(dend+3)//4*4
    if matches:
        for name,hits in matches:
            out.append(f"File: {name}")
            out.extend("  "+line[:500] for line in hits)
    else:
        out.append("No system/vendor/product/odm fstab lines discovered in ramdisk cpio")
    return out

def audit_dtbo(path):
    data=Path(path).read_bytes()[:80]
    out=["## DTBO image",f"Size: {Path(path).stat().st_size} bytes"]
    if len(data)<32 or u32_be(data,0)!=0xd7b7ab1e:
        return out + ["WARN: not a standard Android DTBO image"]
    fields=[
       ("total_size",4),("header_size",8),("dt_entry_size",12),
       ("dt_entry_count",16),("dt_entries_offset",20),
       ("page_size",24),("version",28)
    ]
    out.extend(f"{name}: {u32_be(data,pos)}" for name,pos in fields)
    okay=(u32_be(data,4)<=Path(path).stat().st_size
          and u32_be(data,8)>=32 and u32_be(data,16)>0)
    out.append(f"Basic DTBO header sanity: {str(okay).lower()}")
    return out

def debugfs_text(img,name):
    try:
        p=subprocess.run(["debugfs","-R",f"cat {name}",str(img)],
                         capture_output=True,text=True,errors="replace",timeout=30)
    except (OSError,subprocess.TimeoutExpired):
        return ""
    raw=p.stdout
    if p.returncode!=0 or "File not found by ext2_lookup" in raw or "not found" in raw[:300].lower():
        return ""
    return raw[:2_000_000]

def debugfs_ls(img,name):
    try:
        p=subprocess.run(["debugfs","-R",f"ls -p {name}",str(img)],
                         capture_output=True,text=True,errors="replace",timeout=25)
        return p.stdout[:20000] if p.returncode==0 else ""
    except (OSError,subprocess.TimeoutExpired):
        return ""

def property_extract(content):
    preferred=("ro.vndk.version","ro.vendor.build.version.sdk","ro.vendor.build.version.release",
               "ro.vendor.build.fingerprint","ro.product.vendor.device",
               "ro.product.board","ro.board.platform","ro.hardware",
               "ro.build.version.sdk","ro.build.version.release",
               "ro.vendor.build.security_patch","ro.boot.dynamic_partitions")
    found={}
    for line in content.splitlines():
        if "=" not in line or line.startswith("#"): continue
        k,v=line.split("=",1)
        if k.strip() in preferred: found[k.strip()]=v.strip()
    return found

def audit_vendor(vendor_zip):
    lines=["## Vendor ZIP and filesystem"]
    with zipfile.ZipFile(vendor_zip) as z:
        info=z.infolist()
        lines.extend([f"ZIP entries: {len(info)}",f"Uncompressed bytes: {sum(x.file_size for x in info)}"])
        candidates=[i for i in info if i.filename.rsplit("/",1)[-1].lower()=="vendor.img"]
        if len(candidates)!=1:
            return lines+[f"UNSUPPORTED: expected one vendor.img; found {len(candidates)}"]
        source=candidates[0]
        lines.append(f"vendor.img bytes: {source.file_size}")
        if source.file_size>5_000_000_000:
            return lines+["REFUSED: vendor image exceeds audit safety cap"]
        tmp=Path("inputs/unpacked_vendor.img")
        with z.open(source) as src, tmp.open("wb") as dst:
            shutil.copyfileobj(src,dst,2*MIB)
    kind=image_format(tmp)
    lines.append(f"vendor.img format: {kind}")
    if kind=="Android sparse image":
        if not shutil.which("simg2img"):
            return lines+["Sparse vendor detected; simg2img unavailable. No filesystem inspection."]
        raw=Path("inputs/unpacked_vendor_raw.img")
        subprocess.run(["simg2img",str(tmp),str(raw)],check=True,timeout=90)
        tmp.unlink()
        tmp=raw
        kind=image_format(tmp)
        lines.append(f"Expanded vendor image format: {kind}")
    if kind!="raw ext4":
        return lines+["No ext4 metadata inspection performed (unsupported filesystem)."]
    if shutil.which("resize2fs"):
        estimate=subprocess.run(["resize2fs","-P",str(tmp)],capture_output=True,text=True,errors="replace",timeout=60)
        lines.append("Ext4 minimum size estimate (read-only): "+(estimate.stdout+estimate.stderr).strip()[:1200])
    lines.append("Read-only debugfs inspection:")
    props={}
    for prop in ("/build.prop","/vendor/build.prop","/default.prop","/etc/build.prop"):
        data=debugfs_text(tmp,prop)
        if not data: continue
        props.update(property_extract(data))
        lines.append(f"Found property file: {prop}")
    if props:
        lines.extend(f"- {k}={v[:500]}" for k,v in sorted(props.items()))
    else:
        lines.append("WARNING: no matching vendor build properties found")
    lines.append("VINTF directory listing (truncated):")
    for path in ("/etc/vintf","/vendor/etc/vintf"):
        listing=debugfs_ls(tmp,path)
        if listing:
            lines.append(f"{path}:")
            lines.extend(f"  {line}" for line in listing.splitlines()[:40])
    manifest_paths=["/etc/vintf/manifest.xml","/vendor/etc/vintf/manifest.xml"]
    for manifest in manifest_paths:
        data=debugfs_text(tmp,manifest)
        if not data:continue
        lines.append(f"VINTF manifest: {manifest}, bytes={len(data.encode())}")
        try:
            root=ElementTree.fromstring(data)
            lines.append(f"- manifest target-level: {root.attrib.get('target-level','not specified')}")
            hal_names=[]
            for hal in root.findall(".//hal"):
                name=hal.findtext("name")
                if name and name not in hal_names: hal_names.append(name)
            lines.append(f"- HAL names ({len(hal_names)}): {', '.join(hal_names[:100])}")
        except ElementTree.ParseError as e:
            lines.append(f"- VINTF XML parse error: {e}")
    return lines

def main():
    if len(sys.argv)!=5:
        sys.exit("Usage: script.py boot.img dtbo.img vendor.zip output.md")
    boot,dtbo,vendor,report=map(Path,sys.argv[1:])
    lines=[
       "# A21s SM-A217F One UI 9 hardware preflight",
       "", "Unmodified target inputs only. No ROM was built, no partitions were flashed.",
       "Donor image partition metadata (earlier audit): system=4878610432 bytes, product=676745216 bytes, odm=20971520 bytes.",
       "Vendor VNDK and Android VINTF compatibility still require explicit comparison with donor OS.",
       ""
    ]
    lines+=audit_boot(boot)+[""]
    lines+=inspect_boot_ramdisk(boot)+[""]
    lines+=audit_dtbo(dtbo)+[""]
    lines+=audit_vendor(vendor)+[""]
    lines+=["## Verdict","This report is diagnostic only. Flash-ready status: NO.",
            "A21s super block-device size and its LP metadata must be checked before a new super image is generated.",
            "Donor M21/M31 boot, dtbo and vendor MUST NOT be substituted for A21s hardware images.",""]
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text("\n".join(lines))
    print(report.read_text())

if __name__=="__main__":
    main()
