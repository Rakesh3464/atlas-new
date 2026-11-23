#!/usr/bin/env python3
"""Exhaustive targeted VNDK31 / FCM4 location scan of OneUI9 donor.

All partitions are mounted read-only in an ephemeral GitHub runner.
No files are edited and NO image is flashed or repacked.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from xml.etree import ElementTree as ET
from a21s_ui9_donor_vendor_compat import lp_partitions, expose_partition

EXPECTED_SUPER=6382682112
MIB=1048576

def run(cmd):
    return subprocess.run([str(x) for x in cmd],capture_output=True,
                          text=True,errors="replace",timeout=60,check=False)

def inspect_tree(root,partition):
    apex_directories=[
      "apex","system/apex","system_ext/apex","system/system_ext/apex",
      "product/apex","odm/apex",
    ]
    vintf_directories=[
      "etc/vintf","system/etc/vintf","system_ext/etc/vintf",
      "system/system_ext/etc/vintf","product/etc/vintf","odm/etc/vintf",
    ]
    legacy_directories=[
      "lib64/vndk-31","lib/vndk-31","system/lib64/vndk-31","system/lib/vndk-31",
      "system_ext/lib64/vndk-31","system/system_ext/lib64/vndk-31",
    ]
    result={"partition":partition,"apex_paths_checked":[],"vndk31_apex":[],"apex_name_matches":[],
            "legacy_vndk31_dirs":[],"vintf_paths_checked":[],
            "fcm4_matrices":[],"framework_matrix_levels":[],"vendor_ndk_declarations":[]}
    for sub in apex_directories:
        path=root/sub
        if not path.is_dir():
            continue
        result["apex_paths_checked"].append(sub)
        for child in sorted(path.iterdir()):
            name=child.name
            if "vndk" in name.lower():
                match={"path":str(child.relative_to(root)),"file_bytes":child.stat().st_size if child.is_file() else None}
                result["apex_name_matches"].append(match)
                if re.search(r"com\.android\.vndk\.v31(?:\.|$)",name,re.IGNORECASE):
                    result["vndk31_apex"].append(match)
    for sub in legacy_directories:
        if (root/sub).is_dir():
            result["legacy_vndk31_dirs"].append(sub)
    for sub in vintf_directories:
        base=root/sub
        if not base.is_dir():
            continue
        result["vintf_paths_checked"].append(sub)
        for path in sorted(base.glob("compatibility_matrix*.xml")):
            if not path.is_file():continue
            name=path.name
            if not re.fullmatch(r"compatibility_matrix(?:\.[^/]+)?\.xml",name):continue
            try:
                tree=ET.parse(path)
                elem=tree.getroot()
                level=elem.attrib.get("level")
            except Exception as exc:
                level="UNPARSEABLE: "+str(exc)[:100]
            result["framework_matrix_levels"].append({"path":str(path.relative_to(root)),"level":level})
            if level=="4" or name=="compatibility_matrix.4.xml":
                result["fcm4_matrices"].append({"path":str(path.relative_to(root)),"level":level})
        for path in sorted(base.glob("manifest*.xml")):
            if path.stat().st_size>3*MIB:continue
            try:
                elem=ET.parse(path).getroot()
                for ndk in elem.findall(".//vendor-ndk"):
                    versions=[(v.text or "").strip() for v in ndk.findall("version")]
                    result["vendor_ndk_declarations"].append({"path":str(path.relative_to(root)),"versions":versions})
            except Exception:
                continue
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("super",type=Path)
    p.add_argument("reportdir",type=Path)
    args=p.parse_args()
    donor=args.super.resolve()
    if donor.stat().st_size!=EXPECTED_SUPER:
        raise ValueError("Unverified donor super.img size")
    args.reportdir.mkdir(parents=True,exist_ok=True)
    parts=lp_partitions(donor)
    sections=[]
    with tempfile.TemporaryDirectory(prefix="a21s-vndk-scan-") as dirname:
        work=Path(dirname)
        for partition in ("system","product","odm"):
            if partition not in parts:
                sections.append({"partition":partition,"error":"missing in donor LP"})
                continue
            image,loop=expose_partition(donor,partition,parts[partition],work,[])
            if image is None:
                sections.append({"partition":partition,"error":"could not expose filesystem read-only"})
                continue
            mount=work/("mnt_"+partition)
            mount.mkdir()
            # EROFS product was confirmed in earlier official conversion run.
            fs_type="erofs" if partition=="product" else "ext4"
            options="ro,nodev,nosuid" if fs_type=="erofs" else "ro,noload,nodev,nosuid"
            mounted=False
            try:
                opts=options if loop else options+",loop"
                response=run(["sudo","mount","-t",fs_type,"-o",opts,image,mount])
                if response.returncode!=0:
                    sections.append({"partition":partition,"error":"read-only mount failed","detail":response.stderr[:350]})
                    continue
                mounted=True
                result=inspect_tree(mount,partition)
                result["filesystem"]=fs_type
                sections.append(result)
            finally:
                if mounted:
                    unmount=run(["sudo","umount",mount])
                    if unmount.returncode!=0:
                        raise RuntimeError("read-only mount cleanup failed: "+unmount.stderr[:300])
                if loop:
                    detach=run(["sudo","losetup","-d",loop])
                    if detach.returncode!=0:
                        raise RuntimeError("read-only loop cleanup failed: "+detach.stderr[:300])
                else:
                    try: image.unlink()
                    except OSError: pass
    present=any(x.get("vndk31_apex") or x.get("legacy_vndk31_dirs") for x in sections)
    fcm=any(x.get("fcm4_matrices") for x in sections)
    data={"target":"A21s SM-A217F / Android12 VNDK31 FCM4",
          "donor":"SkyUI Cirrus 9 Android17 M21 M31 family",
          "source":"verified donor super.img",
          "scan":sections,
          "vndk31_location_detected":present,
          "fcm4_location_detected":fcm,
          "full_vintf_test_performed":False,
          "flash_ready":False,
          "note":"Targeted paths, not full ELF dependency analysis; rootfs APEX runtime not tested."}
    (args.reportdir/"a21s-vndk31-fcm4-paths.json").write_text(json.dumps(data,indent=2)+"\n")
    lines=["# A21s One UI9 VNDK31 and FCM4 full-path scan","",
           "**READ ONLY; this report does not certify bootability.**",
           "","A21s original vendor: Android 12 (VNDK31), FCM4.",
           f"VNDK31 found in donor inspected partition locations: **{present}**",
           f"FCM4 matrix found in donor inspected partition locations: **{fcm}**",""]
    for section in sections:
        lines.extend(["## "+section["partition"],""])
        if "error" in section:
            lines.append("Unable to fully scan: "+section["error"]+" "+section.get("detail",""))
            continue
        for item in ("apex_paths_checked","vndk31_apex","apex_name_matches",
                     "legacy_vndk31_dirs","vintf_paths_checked",
                     "fcm4_matrices","framework_matrix_levels","vendor_ndk_declarations"):
            lines.append("### "+item)
            lines.extend(["- "+json.dumps(x,ensure_ascii=False) for x in section[item][:80]] or ["- none"])
        lines.append("")
    lines+=["## Decision",
            "A source-only historical FCM4 XML has been prepared separately; adding it without checkvintf cannot fix framework ABI.",
            "If VNDK31 remains absent, obtain and verify real arm64 com.android.vndk.v31.apex from a compatible firmware/working ROM.",
            "Do not rename another APEX, spoof FCM, or flash the experimental ROM.",""]
    (args.reportdir/"a21s-vndk31-fcm4-paths.md").write_text("\n".join(lines))
    print("\n".join(lines))
if __name__=="__main__":
    main()
