# A21s SUSFS 4.19 compatibility audit (2026-11-21)

**Target:** `Rakesh3464/atlas-new` / Exynos 850 / Linux 4.19.325 / `exynos850-a21snsxx_defconfig`.

**Candidate upstream patch:** `XxRagulxX/Susfs-patch` branch `kernel-4.19`, `kernel_patches/50_add_susfs_in_kernel-4.19.patch`.

A source-level preflight compared the **original/removal lines of each unified-diff hunk** against the current GitHub file text. These comparisons are **not an actual `patch --dry-run` or a successful compiler test**. Some contexts may be solvable by fuzz or a manual port.

## Hunk preflight

| Source path | Matched hunks | Mismatched hunks |
| --- | ---: | ---: |
| fs/Makefile | 0 | 1 |
| fs/dcache.c | 3 | 0 |
| fs/namei.c | 23 | 0 |
| fs/namespace.c | 15 | 4 |
| fs/notify/fdinfo.c | 4 | 0 |
| fs/proc/cmdline.c | 1 | 0 |
| fs/proc/fd.c | 3 | 0 |
| fs/proc/task_mmu.c | 3 | 0 |
| fs/proc_namespace.c | 4 | 0 |
| fs/readdir.c | 23 | 0 |
| fs/stat.c | 3 | 1 |
| fs/statfs.c | 3 | 0 |
| include/linux/mount.h | 0 | 1 |
| include/linux/stat.h | 1 | 0 |
| kernel/kallsyms.c | 1 | 0 |
| kernel/sys.c | 0 | 1 |

**Caution:** `include/linux/mount.h` patch expects particular Android KABI reserve macros/fields; `kernel/sys.c` and `fs/namespace.c` require careful integration with Samsung A21s changes. Do **not** force-apply with `--reject`, silently discard hunks, or package a boot image before successful compile and device validation.

## Recommended sequence

1. Capture the actual SUSFS kernel and KernelSU patch dry-run logs in GitHub Actions.
2. Manually port the mismatched hunks against this tree, preserving Samsung mount/namespace behavior.
3. Validate the linked `rsuntk/KernelSU` submodule revision and test the separate KernelSU patch.
4. Confirm `CONFIG_KSU=y` and `CONFIG_KSU_SUSFS=y` in generated `out/.config`, compile `Image`, inspect DTB/DTBO, then package using the original A21s boot-image header/ramdisk.
5. **Until all checks pass, no flash-ready boot.img exists.**

The repository build script is fail-closed on patch conflicts. This audit is diagnostic only.
