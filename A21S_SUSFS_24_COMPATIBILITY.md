# A21s 4.19.325 — SUSFS v2.4 compatibility checkpoint

Source: user-provided `a21s-susfs-compatibility-audit.zip` (GitHub Actions audit).

## Verified

- Kernel version: `4.19.325`.
- KernelSU submodule revision: `648e5988cf421172769f80ce07f86331b548c053`.
- `drivers/Kconfig` references `drivers/kernelsu/Kconfig`.
- `drivers/Makefile` includes `obj-$(CONFIG_KSU) += kernelsu/`.
- KernelSU Kconfig contains `KSU`, `KSU_MANUAL_HOOK`, `KSU_FEATURE_ADBROOT`, `KSU_DEBUG`.
- No SUSFS files found in scanned `KernelSU`, `fs`, or `include/linux` locations.
- No `CONFIG_KSU_SUSFS`, `CONFIG_SUSFS`, or `susfs_` references found in audited paths.
- `fs/namespace.c`, `fs/open.c`, `fs/stat.c`, `fs/readdir.c`, `fs/proc/cmdline.c`, and `fs/exec.c` are present.

## Integration blockers

1. Select a specific SUSFS v2.4.0 source revision and verify that its kernel-4.19 patch exists or determine required backports.
2. Compare SUSFS hooks against the *actual* KernelSU revision and the Samsung 4.19 filesystem implementation.
3. Apply patches to a separate development branch; compile with `CONFIG_KSU=y` and SUSFS options enabled.
4. Confirm runtime compatibility before any flashable image is distributed.

**This document is a checkpoint, not a SUSFS integration.** No SUSFS v2.4 source has been merged, compiled, or tested.
