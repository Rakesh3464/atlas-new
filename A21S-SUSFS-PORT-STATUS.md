# Samsung A21s / Atlas Linux 4.19.325 — SUSFS Port Status

> **DO NOT FLASH.** This repository branch does not contain a compiled, validated SUSFS kernel or a flash-ready `boot.img`.

## Context
- Device: Samsung Galaxy A21s (Exynos 850)
- Kernel source: `Rakesh3464/atlas-new`, branch `a21s-susfs-oneui9-build`
- Kernel version: 4.19.325
- Existing KernelSU source: `rsuntk/KernelSU` submodule, pinned by the repository.
- Goal: One UI 9 kernel with KernelSU and SUSFS.

## CI evidence (2026-11-20)
- First build attempt: https://github.com/Rakesh3464/atlas-new/actions/runs/44673928448
  - Failed at incorrect SUSFS source path, now corrected.
- Second build attempt: https://github.com/Rakesh3464/atlas-new/actions/runs/44674230961
  - Upstream SUSFS `kernel-4.19` kernel patch rejects multiple Atlas-specific hunks.
- Compatibility probe: https://github.com/Rakesh3464/atlas-new/actions/runs/44674923833
  - `kernel-4.19`: kernel patch and KernelSU patch both rejected.
  - `1.4.2-kernel-4.19`: kernel patch has fewer incompatibilities, but KernelSU patch rejected.
- Context probe: https://github.com/Rakesh3464/atlas-new/actions/runs/44675251813
  - Whitespace context adjustment does not resolve all remaining kernel patch rejects.
  - KernelSU patch still rejects several hunks across its source.
  - No kernel image has been compiled; a passing CI *diagnostic* job is not a successful kernel build.

## Required before a usable image can be considered
1. Manually port the remaining SUSFS 4.19 kernel hooks into Atlas with semantics reviewed for its vendor differences.
2. Integrate a KernelSU SUSFS implementation **matching** the pinned KernelSU hooks and APIs; do not blindly apply incompatible patch hunks.
3. Compile an ARM64 A21s kernel with `CONFIG_KSU=y` and `CONFIG_KSU_SUSFS=y`, and verify ABI/DTB alignment with the target ROM.
4. Repack the **target A21s One UI 9 boot image** while preserving correct kernel placement, DTB, ramdisk, header, partition-size and AVB constraints.
5. Perform a recoverable on-device boot test before calling any artifact flash-ready.

Never bypass failed patches with `patch --force`, remove failed hunks silently, or rename an untested image to flash-ready.
