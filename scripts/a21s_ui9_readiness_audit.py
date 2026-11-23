#!/usr/bin/env python3
"""Read-only Android17 donor / A21s VNDK31 boot-readiness checklist.

Not a full VINTF checker. Uses debugfs and liblp metadata without mounts/flash.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

from a21s_ui9_donor_vendor_compat import lp_partitions, expose_partition

MIB = 1048576
EXPECTED_SUPER_BYTES = 6382682112
EXPECTED_VENDOR_BYTES = 846389248

def run(cmd):
    p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",timeout=50,check=False)
    return p

def debugfs(img,command):
    cmd=(["sudo"] if str(img).startswith("/dev/loop") else [])+["debugfs","-R",command,str(img)]
    return run(cmd)

def listing(img,dirpath):
    p=debugfs(img,"ls -p "+dirpath)
    if p.returncode!=0 or "File not found" in p.stderr:
        return ""
    return p.stdout

def read(img,file):
    p=debugfs(img,"cat "+file)
    if p.returncode!=0 or "File not found" in p.stderr or "not found" in p.stderr.lower():
        return ""
    return p.stdout[:2000000]

def exists(img,path):
    p=debugfs(img,"stat "+path)
    return p.returncode==0 and "Inode:" in p.stdout and "File not found" not in p.stderr

def keys(img,paths):
    res={}
    for path in paths:
        raw=read(img,path)
        for row in raw.splitlines():
            if row.startswith("#") or "=" not in row:continue
            key,val=row.split("=",1)
            if key in ("ro.vndk.version","ro.build.version.sdk",
                       "ro.build.version.release","ro.vendor.build.version.sdk",
                       "ro.vendor.build.version.release",
                       "ro.system.build.version.sdk","ro.system.build.version.release"):
                res[key]=val
    return res

def hal_names(contents):
    try:
        elem=ET.fromstring(contents)
    except ET.ParseError:
        return {}, None
    names={}
    for hal in elem.findall("hal"):
        name=hal.findtext("name")
        if not name:continue
        optional=hal.attrib.get("optional","false")=="true"
        names[name]=optional
    return names,elem

def get_vendor_archive(zip_path,output):
    with zipfile.ZipFile(zip_path) as z:
        entries=[i for i in z.infolist() if i.filename.rsplit("/",1)[-1]=="vendor.img"]
        if len(entries)!=1 or entries[0].file_size!=EXPECTED_VENDOR_BYTES:
            raise ValueError("Unknown vendor.img entry or size")
        with z.open(entries[0]) as src,output.open("wb") as dst:
            shutil.copyfileobj(src,dst,16*MIB)

def report(super_img,vendor_zip,output):
    output.parent.mkdir(parents=True,exist_ok=True)
    if super_img.stat().st_size!=EXPECTED_SUPER_BYTES:
        raise ValueError("Expected audited SkyUI super.img")
    parts=lp_partitions(super_img)
    if "system" not in parts:
        raise ValueError("Donor system partition missing")
    vendor=output.parent/"a21s_vendor_tmp.img"
    get_vendor_archive(vendor_zip,vendor)
    checks=[]
    # The vendor is an actual A21s stock Android 12 VNDK31 image; check its manifest.
    try:
        vprops=keys(vendor,("/build.prop","/vendor/build.prop"))
        vin=read(vendor,"/etc/vintf/manifest.xml")
        hal,man=hal_names(vin)
        level=man.attrib.get("target-level","unknown") if man is not None else "unparsed"
        checks.extend([
            {"id":"vendor-api", "observed":vprops.get("ro.vendor.build.version.sdk","unknown"),"expected":"31"},
            {"id":"vendor-vndk", "observed":vprops.get("ro.vndk.version","unknown"),"expected":"31"},
            {"id":"vendor-target-fcm", "observed":level,"expected":"4"}
        ])
        # Scan system ext4 partition via read-only loop. Never change source bytes.
        image,loop=expose_partition(super_img,"system",parts["system"],output.parent,[])
        if image is None:
            raise RuntimeError("Cannot read donor system partition")
        try:
            props=keys(image,("/system/build.prop","/build.prop"))
            # Dynamic linker VNDK library delivery could be APEX, system lib or both.
            apexlist=listing(image,"/system/apex")
            legacy_apexlist=listing(image,"/apex")
            apex_source="\n".join([apexlist,legacy_apexlist])
            apex_v31=sorted(set(re.findall(r"com\.android\.vndk\.v31\.(?:apex|capex)",apex_source)))
            vndk_dir=any(exists(image,x) for x in ("/system/lib64/vndk-31","/system/lib/vndk-31",
                                                  "/lib64/vndk-31","/lib/vndk-31"))
            if not apex_v31:
                for path in ("/system/apex/com.android.vndk.v31.apex",
                             "/system/apex/com.android.vndk.v31.capex"):
                    if exists(image,path):
                        apex_v31.append(path)
            dirdata=listing(image,"/system/etc/vintf")+"\n"+listing(image,"/etc/vintf")
            matrix_files=sorted(set(re.findall(r"compatibility_matrix\.[0-9]+\.xml",dirdata)))
            matrix_fcm4=[]
            framework_required=[]
            for root in ("/system/etc/vintf","/etc/vintf"):
                for fname in ("compatibility_matrix.4.xml","compatibility_matrix.xml"):
                    xml=read(image,root+"/"+fname)
                    if not xml:continue
                    names,mat=hal_names(xml)
                    if mat is None:continue
                    matrix_fcm4.append({"path":root+"/"+fname,"level":mat.attrib.get("level","unknown"),"hals":len(names)})
                    if mat.attrib.get("level")=="4" or fname=="compatibility_matrix.4.xml":
                        framework_required += sorted(name for name,optional in names.items() if not optional)
            mapping=listing(image,"/system/etc/selinux/mapping")
            if not mapping:
                mapping=listing(image,"/etc/selinux/mapping")
            mappings=sorted(set(re.findall(r"(?:[0-9]+(?:\.[0-9]+)?)\.cil",mapping)))
            if not mappings:
                for item in ("/system/etc/selinux/mapping/4.0.cil",
                             "/system/etc/selinux/mapping/31.0.cil"):
                    if exists(image,item):mappings.append(item.rsplit("/",1)[-1])
            missing_hal=sorted(set(framework_required)-set(hal))
            checks.extend([
                {"id":"donor-api","observed":props.get("ro.build.version.sdk","unknown"),
                 "expected":"37"},
                {"id":"system-vndk31-library-delivery","observed":{
                    "apex_names":apex_v31,"legacy_vndk_31_dirs_present":vndk_dir
                 },"expected":"Any VNDK31 delivery candidate present"},
                {"id":"framework-fcm4","observed":{
                   "matrix_files":matrix_files,"fcm4_entries":matrix_fcm4
                 },"expected":"FCM 4 compatibility matrix in donor system"},
                {"id":"sepolicy-mapping","observed":{
                   "mapping_files":mappings[:50],
                   "mapping_4_0_found":any("4.0.cil"==x for x in mappings)
                 },"expected":"Mapping appropriate to target vendor policy and platform release"},
                {"id":"framework-fcm4-required-hals-vs-vendor","observed":{
                   "required_count":len(framework_required),
                   "vendor_manifest_hals_count":len(hal),
                   "missing_names":missing_hal[:100]
                 },"expected":"All required relevant HALs satisfied; preliminary name-only check"},
            ])
            blockers=[]
            if not apex_v31 and not vndk_dir:
                blockers.append("No com.android.vndk.v31 APEX or legacy vndk-31 directories found in donor system; assess VNDK31 runtime")
            if not any(m.get("level")=="4" for m in matrix_fcm4):
                blockers.append("No parsed FCM level-4 framework compatibility matrix found in donor system")
            if missing_hal:
                blockers.append("Possible missing mandatory FCM4 HAL names in A21s vendor manifest (must use real libvintf check)")
            if not mappings:
                blockers.append("No parseable SELinux compatibility mapping discovered; inspect platform/vendor policy")
            blockers+= [
              "Exact A21s physical super size and LP groups have not been obtained from device",
              "Android 17 system + A21s Android12 VNDK31 boot, SELinux and VINTF have not been device-tested",
              "AVB/vbmeta chain and kernel/ramdisk mount correctness remain unverified"
            ]
            data={
              "model":"Samsung Galaxy A21s SM-A217F",
              "donor":"SkyUI Cirrus 9 / Android 17",
              "checks":checks,
              "warnings":blockers,
              "method":"File existence and XML manifest name inspection only; NOT full VINTF/ABI/boot test",
              "flash_ready":False,
              "flash_instructions_provided":False
            }
        finally:
            if loop:
                run(["sudo","losetup","-d",loop])
            else:
                image.unlink(missing_ok=True)
    finally:
        vendor.unlink(missing_ok=True)
    (output.parent/"a21s-ui9-readiness.json").write_text(json.dumps(data,indent=2)+"\n")
    lines=[
        "# A21s One UI 9 preliminary boot-readiness audit",
        "",
        "Read-only inspection. **Not a flashable or boot-tested ROM.**",
        "",
        "## Checks",
        ""
    ]
    for c in checks:
        lines.append(f"### {c['id']}")
        lines.append(f"- Observed: \`{str(c['observed'])[:2400]}\`")
        lines.append(f"- Expected: {c['expected']}")
        lines.append("")
    lines.append("## Unresolved issues and stop conditions")
    lines += [f"- {w}" for w in data["warnings"]]
    lines += ["", "**Verdict:** do not flash the current experimental package.", ""]
    output.write_text("\n".join(lines))
    print(output.read_text())

if __name__=="__main__":
    if len(sys.argv)!=4:
        sys.exit("Usage: script.py donor-super.img target-vendor.zip output.md")
    report(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
