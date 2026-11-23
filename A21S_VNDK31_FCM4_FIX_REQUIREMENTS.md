# Samsung A21s (SM-A217F) One UI 9 — VNDK31 / FCM4 compatibility patch status

**Not flashable. A complete fix has NOT been built or tested.**

## Confirmed facts from tested target and donor

- Original A21s vendor: Android 12 / API 31; ro.vndk.version=31; VINTF target-level=4; A21s camera works with this vendor.
- SkyUI Cirrus 9 donor: Android 17 / API 37, originally for M21/M31/M31s/F41 (different SoC).
- Inspected donor system lacks a visible `com.android.vndk.v31` APEX or legacy VNDK31 directories.
- Donor system includes FCM levels 7, 8, 202404, 202504, 202604, but inspection found no FCM4 matrix.
- The experimental super image hashes match the assembled images. There is no proof of device bootability.

## Verified FCM4 source

AOSP Android 14 historical source:
https://android.googlesource.com/platform/hardware/interfaces/+/android-14.0.0_r11/compatibility_matrices/compatibility_matrix.4.xml

Validated source SHA-256:
`1df3df6bc7efe4a3d9bdc3d64148d00b871a5a7b590f0423fad11216d125d153`

Build: https://github.com/Rakesh3464/atlas-new/actions/runs/45166004780

The official XML is a SOURCE file, not sufficient to enable obsolete HAL implementations on an Android 17 framework. Its compatibility must be evaluated using libvintf/checkvintf on a correct image tree.

## Genuine VNDK31 APEX provenance from an existing Samsung port build

ProjectDozG's documented [VNDK script](https://github.com/ProjectDozG/ProjectDozG/blob/main/unica/patches/vndk/customize.sh) uses:

```sh
ADD_TO_WORK_DIR "b0qxxx" "system_ext" "apex/com.android.vndk.v31.apex" 0 0 644 "u:object_r:system_file:s0"
```

This indicates that the port build uses a **real Samsung firmware VNDK31 APEX** in `system_ext`, not an empty placeholder or a renamed VNDK33/34 APEX.

## Required input to complete the patch

Acquire the original **arm64 `com.android.vndk.v31.apex`** from the user's *already-working compatible One UI 8.5 ROM* or a verified matching Samsung firmware's `system_ext/apex` partition, along with its original SHA-256/provenance.

**Never** fabricate an APEX from a renamed VNDK32/33/34 image. Do not append a fake FCM4 matrix, change `ro.vndk.version`, or spoof target-level 4 to 7/8.

## Remaining validation

1. Check that the APEX manifest actually advertises `com.android.vndk.v31` and includes the expected **arm64** libraries.
2. Integrate the correct signed APEX into a compatible system_ext mounting path with exact file permissions, SELinux labels and requisite `vendor-ndk` framework manifest declarations.
3. Merge and validate device and framework manifests/matrices with libvintf/checkvintf, including kernel requirements.
4. Validate SELinux mapping/AVB, boot image init and recovery plan; test the ROM on an SM-A217F before claiming compatibility.

**The current ROM is still NOT FLASH-READY.**
