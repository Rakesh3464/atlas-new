#!/usr/bin/env python3
"""Prepare official FCM level 4 SOURCE ONLY for A21s OneUI9 compatibility work.

No vendor/fcm spoofing. No system image modifications. No flash or install scripts.
Source is AOSP Android 14 historical FCM4. NOT equivalent to a boot-ready fix.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import json
from pathlib import Path
import sys
import urllib.request
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

AOSP_TAG="android-14.0.0_r11"
AOSP_URL=(
    "https://android.googlesource.com/platform/hardware/interfaces/+/"
    + AOSP_TAG + "/compatibility_matrices/compatibility_matrix.4.xml?format=TEXT"
)

def main():
    if len(sys.argv)!=2:
        raise SystemExit("Usage: a21s_ui9_prepare_fcm4.py OUTPUT_DIRECTORY")
    output=Path(sys.argv[1])
    output.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(AOSP_URL,headers={"User-Agent":"A21sUI9-compat-research/1.0"})
    with urllib.request.urlopen(req,timeout=45) as r:
        downloaded=r.read(8_000_000)
    if downloaded.startswith(b"<?xml"):
        xml_bytes=downloaded
    else:
        xml_bytes=base64.b64decode(downloaded,validate=True)
    root=ET.fromstring(xml_bytes)
    if root.tag!="compatibility-matrix" or root.attrib.get("level")!="4" or root.attrib.get("type")!="framework":
        raise ValueError("Downloaded file is not an AOSP framework FCM level 4")
    if len(xml_bytes)<200 or len(xml_bytes)>2_000_000:
        raise ValueError("Suspicious official FCM4 size")
    if not any(tag.tag=="hal" for tag in root):
        raise ValueError("Official FCM4 file lacks HAL requirements")
    patchname="compatibility_matrix.4.xml"
    digest=sha256(xml_bytes).hexdigest()
    official=output/patchname
    official.write_bytes(xml_bytes)
    info={
       "purpose":"prepare authoritative historical FCM4 for offline compatibility analysis",
       "source":AOSP_URL,
       "source_tag":AOSP_TAG,
       "sha256":digest,
       "bytes":len(xml_bytes),
       "a21s_vendor_target_fcm":"4 (previous audit)",
       "a21s_vendor_vndk":"31 (previous audit)",
       "android17_donor_matrix_levels_seen":["7","8","202404","202504","202604"],
       "warning":"Not proven accepted by Android 17 framework. Must validate with libvintf/checkvintf.",
       "vndk31_status":"MISSING from inspected donor system; no trusted matching signed APEX binary in available inputs",
       "patched_rom":False,
       "flash_ready":False,
    }
    (output/"FCM4-provenance.json").write_text(json.dumps(info,indent=2)+"\n")
    readme="""SAMSUNG A21s SM-A217F — ONE UI 9 FCM4 PREPARATION
===================================================
NOT A FLASHABLE FIX. NO PARTITIONS WERE CHANGED.

Included:
- Historical official AOSP framework compatibility_matrix.4.xml
- Provenance and SHA256

DO NOT copy this onto a running phone without inspecting donor framework
compatibility, supported HAL APIs, and SELinux policy. The Android 17
framework may no longer expose older HAL interfaces even if an XML file
claims they are supported.

KNOWN UNRESOLVED:
1. A21s Android12 / VNDK31 vendor requires real matching arm64 VNDK31
   native libraries and APEX integration. NO signed working VNDK31 APEX
   was found in inputs. FCM XML is not a replacement for this.
2. Full checkvintf / libvintf of merged manifests, framework matrices,
   vendor HALs and kernel FCM level.
3. Exact physical super partition layout metadata, AVB / boot process,
   SELinux mapping and init service dependencies.
4. Boot test on physical SM-A217F device and recovery strategy.

Do NOT flash experimental super images. This ZIP only prepares the
historical FCM4 XML for development.
"""
    (output/"READ_ME_NOT_FLASHABLE.txt").write_text(readme)
    destination=output/"A21s-OneUI9-FCM4-SOURCE-PREP-NOT-FLASHABLE.zip"
    with ZipFile(destination,"w",compression=ZIP_DEFLATED) as z:
        for filename in (patchname,"FCM4-provenance.json","READ_ME_NOT_FLASHABLE.txt"):
            z.write(output/filename,arcname=filename)
    print(json.dumps(info,indent=2))
    print("Prepared source ZIP:",destination, destination.stat().st_size)

if __name__=="__main__":
    main()
