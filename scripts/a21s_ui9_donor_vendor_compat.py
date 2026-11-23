#!/usr/bin/env python3
"""A21s (SM-A217F) vs SkyUI Cirrus 9 (M21/M31) read-only compatibility scan.
Input images are user-shared, untrusted, and NEVER modified or flashed.
"""
import argparse
import hashlib
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MiB=1024*1024
GB=1000*1000*1000

def u32(b,pos):
    return struct.unpack_from("<I",b,pos)[0]

def tables(buf,base,hsize,tsize,at,minimum):
    off,count,size=struct.unpack_from("<III",buf,base+at)
    if not (0<=count<1024 and minimum<=size<1024 and off+count*size<=tsize):
        raise ValueError("Invalid liblp table descriptor at "+str(at))
    start=base+hsize+off
    if start+count*size>len(buf):
        raise ValueError("Incomplete liblp table prefix")
    return [(start+i*size,size) for i in range(count)]

def lp_partitions(path):
    with path.open("rb") as fp:
        buf=fp.read(1024*1024)
    if len(buf)<65536 or u32(buf,4096)!=0x616c4467:
        raise ValueError("Missing raw super.img liblp geometry")
    gsize=u32(buf,4100)
    if gsize!=52:
        raise ValueError("Unexpected liblp geometry size "+str(gsize))
    geom=bytearray(buf[4096:4096+gsize])
    h=bytes(geom[8:40]); geom[8:40]=b"\0"*32
    if hashlib.sha256(geom).digest()!=h:
        raise ValueError("Invalid geometry SHA256")
    base=12288
    if u32(buf,base)!=0x414c5030:raise ValueError("Invalid liblp header magic")
    major,minor,hsize=struct.unpack_from("<HHI",buf,base+4)
    if major!=10:raise ValueError("Unsupported liblp major version "+str(major))
    tsize=u32(buf,base+44)
    head=bytearray(buf[base:base+hsize]); expected=bytes(head[12:44]);head[12:44]=b"\0"*32
    if hashlib.sha256(head).digest()!=expected:raise ValueError("Header SHA mismatch")
    if hashlib.sha256(buf[base+hsize:base+hsize+tsize]).digest()!=buf[base+48:base+80]:
        raise ValueError("Table SHA mismatch")
    p=tables(buf,base,hsize,tsize,80,52)
    e=tables(buf,base,hsize,tsize,92,24)
    device=tables(buf,base,hsize,tsize,116,64)
    if len(device)!=1:raise ValueError("Expected one donor block device")
    actual=path.stat().st_size
    result={}
    for off,_ in p:
        name=buf[off:off+36].split(b"\0",1)[0].decode("ascii","replace")
        attrs,first,nex,group=struct.unpack_from("<IIII",buf,off+36)
        if nex!=1 or first>=len(e):
            raise ValueError("Only contiguous single-extent donor partitions are supported: "+name)
        ex,_=e[first]
        sectors,typ,sector,source=struct.unpack_from("<QIQI",buf,ex)
        if typ!=0 or source!=0:raise ValueError("Nonlinear/non-super extent: "+name)
        offset=sector*512
        size=sectors*512
        if offset+size>actual:raise ValueError("Partition outside source super.img: "+name)
        result[name]={"offset":offset,"bytes":size,"attrs":attrs,"group_index":group}
    return result

def run_cmd(args,timeout=60):
    try:
        return subprocess.run(args,capture_output=True,timeout=timeout,check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return None

def debugfs_read(img,path):
    r=run_cmd((["sudo"] if str(img).startswith("/dev/loop") else [])+["debugfs","-R","cat "+path,str(img)],timeout=45)
    if r is None or r.returncode!=0 or not r.stdout:
        return ""
    return r.stdout[:1500000].decode("utf-8","replace")

def debugfs_ls(img,path):
    r=run_cmd((["sudo"] if str(img).startswith("/dev/loop") else [])+["debugfs","-R","ls -p "+path,str(img)],timeout=30)
    if r is None or r.returncode!=0:
        return ""
    return r.stdout[:25000].decode("utf-8","replace")

def select_props(contents):
    keys=("ro.build.version.sdk","ro.build.version.release","ro.build.version.codename",
          "ro.system.build.version.sdk","ro.system.build.version.release",
          "ro.product.build.version.sdk","ro.product.build.version.release",
          "ro.vndk.version","ro.vendor.build.version.sdk","ro.vendor.build.version.release",
          "ro.vendor.build.fingerprint","ro.product.vendor.device",
          "ro.board.platform","ro.product.board","ro.product.device",
          "ro.build.version.min_supported_target_sdk","ro.build.version.security_patch")
    vals={}
    for line in contents.splitlines():
        if "=" in line and not line.startswith("#"):
            k,v=line.split("=",1)
            if k.strip() in keys: vals[k.strip()]=v.strip()
    return vals

def read_report_for_fs(label,img,lines):
    lines.extend(["","## "+label,f"Image: {img}"])
    with Path(img).open("rb") as f:
        f.seek(1080)
        magic=f.read(2)
    lines.append(f"ext4 magic at 1080: {magic.hex()}"+(" PASS" if magic==b"\x53\xef" else " OTHER"))
    if magic!=b"\x53\xef":
        lines.append("Unsupported filesystem for debugfs-based property audit")
        return {},[]
    props={}
    for prop in ("/build.prop","/system/build.prop","/product/build.prop",
                 "/vendor/build.prop","/odm/build.prop"):
        content=debugfs_read(img,prop)
        if content:
            lines.append(f"Property file read: {prop}")
            props.update(select_props(content))
    for k,v in sorted(props.items()):
        lines.append(f"- {k}={v[:250]}")
    if not props:lines.append("WARNING: no matching build properties found")
    hal_names=[]
    for prefix in ("/etc/vintf","/system/etc/vintf","/vendor/etc/vintf"):
        listing=debugfs_ls(img,prefix)
        if not listing:continue
        names=re.findall(r"/([^/\n]+)/(?:\d+)?/?",listing)
        if names:
            lines.append(f"VINTF path {prefix}: "+", ".join(dict.fromkeys(names[:60])))
        for candidate in (prefix+"/manifest.xml",prefix+"/compatibility_matrix.xml"):
            content=debugfs_read(img,candidate)
            if not content:continue
            try:
                root=ET.fromstring(content)
                lines.append(f"VINTF XML {candidate}: root={root.tag}, level={root.attrib.get('level',root.attrib.get('target-level','unspecified'))}")
                for hal in root.findall(".//hal"):
                    name=hal.findtext("name")
                    if name and name not in hal_names:hal_names.append(name)
            except ET.ParseError:
                lines.append("VINTF XML not parsed: "+candidate)
    for prefix in ("/lib64/vndk-31","/system/lib64/vndk-31","/apex/com.android.vndk.v31",
                   "/etc/selinux","/system/etc/selinux"):
        listing=debugfs_ls(img,prefix)
        if listing:lines.append(f"Exists: {prefix} (debugfs listing returned)")
    if hal_names:lines.append("VINTF HALs: "+", ".join(hal_names[:100]))
    return props,hal_names

def expose_partition(super_path,name,extent,scratch,lines):
    offset,size=extent["offset"],extent["bytes"]
    loop=None
    try:
        call=run_cmd(["sudo","losetup","--find","--show","--read-only",
                      "--offset",str(offset),"--sizelimit",str(size),str(super_path)],timeout=30)
        if call and call.returncode==0:
            loop=call.stdout.decode().strip()
            if loop and Path(loop).exists():
                lines.append(f"Mapped {name} with read-only loop device (offset={offset}, bytes={size})")
                return Path(loop),loop
            loop=None
        lines.append(f"Read-only loop unavailable for {name}: "+
                     ((call.stderr.decode("utf-8","replace")[:300]) if call else "tool not available"))
        free=shutil.disk_usage(scratch).free
        if free < size+128*MiB:
            lines.append(f"Insufficient free scratch disk for safe {name} fallback (need {size}, free {free})")
            return None,None
        img=scratch / (name+".img")
        with super_path.open("rb") as f, img.open("wb") as w:
            f.seek(offset)
            remain=size
            while remain:
                chunk=f.read(min(16*MiB,remain))
                if not chunk: raise EOFError("Source donor super truncated")
                w.write(chunk)
                remain-=len(chunk)
        lines.append(f"Prepared temporary read-only-in-use {name} image copy")
        return img,None
    except Exception as exc:
        lines.append(f"Error preparing {name}: {type(exc).__name__}: {str(exc)[:200]}")
        return None,None

def audit(super_img,vendor_zip,outdir):
    outdir.mkdir(parents=True,exist_ok=True)
    lines=[
        "# SkyUI One UI 9 donor / Samsung A21s VNDK31 compatibility",
        "",
        "This is a READ-ONLY audit; it does not build, sign or flash a ROM.",
        "The donor is for M21/M31/M31s/F41, NOT A21s SM-A217F.",
        ""
    ]
    parts=lp_partitions(super_img)
    lines.append("## Donor super.img contiguous extents")
    for n,p in parts.items():
        lines.append(f"- {n}: offset {p['offset']}, length {p['bytes']}")
    with zipfile.ZipFile(vendor_zip) as z:
        matches=[x for x in z.infolist() if x.filename.rsplit("/",1)[-1].lower()=="vendor.img"]
        if len(matches)!=1:raise ValueError("Expected one vendor.img in user zip")
        with z.open(matches[0]) as f, (outdir/"a21s_vendor.img").open("wb") as target:
            shutil.copyfileobj(f,target,8*MiB)
    vendor=outdir/"a21s_vendor.img"
    vprops,vhal=read_report_for_fs("A21s Android 12 VNDK31 vendor",vendor,lines)
    props_by={}
    for name in ("system","product","odm"):
        if name not in parts:
            lines.append("MISSING DONOR PARTITION: "+name)
            continue
        image,loop=expose_partition(super_img,name,parts[name],outdir,lines)
        if image is None:continue
        try:
            props,hal=read_report_for_fs("Donor "+name,image,lines)
            props_by[name]=props
        finally:
            if loop:
                run_cmd(["sudo","losetup","-d",loop],timeout=30)
            else:
                try:image.unlink()
                except OSError: pass
    vendor.unlink(missing_ok=True)
    lines += ["","## Cross-version risk assessment",
              f"A21s vendor VNDK: {vprops.get('ro.vndk.version','not found')}",
              f"A21s vendor Android SDK: {vprops.get('ro.vendor.build.version.sdk','not found')}",
              f"Donor system SDK: {props_by.get('system',{}).get('ro.build.version.sdk',props_by.get('system',{}).get('ro.system.build.version.sdk','not found'))}",
              "An OS framework / vendor ABI mismatch requires explicit VINTF/SELinux and service checks; it cannot be fixed by simple image concatenation.",
              "The user reported a 10 GB physical super partition but exact measured LP metadata is not present.",
              "Do not flash any image from this audit; generated ROM: NO."]
    report=outdir/"donor-vndk31-compat.md"
    report.write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("super",type=Path)
    p.add_argument("vendor_zip",type=Path)
    p.add_argument("report_dir",type=Path)
    a=p.parse_args()
    audit(a.super,a.vendor_zip,a.report_dir)
