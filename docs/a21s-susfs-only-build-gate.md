# A21s SUSFS-only feasibility gate

Target: Samsung Galaxy A21s SM-A217F / Linux 4.19.325.
User requirement: **SUSFS present, KernelSU absent.**

## Verified blockers

- Current `atlas-new` source links `drivers/kernelsu` to the `KernelSU` git submodule, but the uploaded source ZIP contains an empty `KernelSU/`.
- Existing `scripts/a21s-apply-susfs.sh` patches `KernelSU/kernel`; it is **not a SUSFS-only solution**.
- Upstream `XxRagulxX/Susfs-patch` `kernel-4.19` SUSFS userspace interfaces and kernel source reference KernelSU domains, config symbols and helpers. Removing KernelSU from the build configuration alone does not make these functions standalone.
- A local source `make ... exynos850-a21snsxx_defconfig` attempt stopped because `bison` is not installed. This is independent of SUSFS.
- The port branch also contains unmerged Samsung-specific SUSFS hunk changes; no completed compile or tested boot image exists.

## Acceptance conditions before producing boot.img

1. Implement an independent SUSFS Kconfig option with all required access control and kernel hooks; remove or replace KernelSU-specific helper calls, without silently disabling requested SUSFS functionality.
2. Port all SUSFS filesystem changes to the A21s kernel and resolve `fs/namespace.c`, `fs/stat.c` and all remaining patch conflicts.
3. Compile `exynos850-a21snsxx_defconfig` with `CONFIG_KSU` unset and the standalone SUSFS option enabled; verify `Image` links.
4. Package with original boot header, ramdisk, device tree and other image parameters, preserve backup.
5. Validate device boot; do not label any untested build flash-ready.

This document records current blockers; it is **not** a port or a flashable output.
