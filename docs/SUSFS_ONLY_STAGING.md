# SUSFS source staging for Samsung A21s (Linux 4.19.325)

Goal: **SUSFS without KernelSU**, as requested.

Upstream source copied from `XxRagulxX/Susfs-patch` branch `kernel-4.19`:

- `fs/susfs.c`
- `include/linux/susfs.h`
- `include/linux/susfs_def.h`

These are upstream source files only, not a working standalone port. They are staged in this branch, with **no `fs/Makefile` registration and no Kconfig enablement**; therefore **SUSFS is not compiled into the kernel**. Do not merge assuming functionality is enabled.

The staged source references `CONFIG_KSU_SUSFS_*` and KernelSU-specific domain functions. A proper SUSFS-only port must design independent authorization, control interfaces and hooks, reconcile Samsung's 4.19 mount/namespace changes, and validate all code paths in a cross-compile before any boot image can be assembled.

**No flashable boot.img has been produced.** Avoid flashing any output from this branch before successfully compiling and testing a device-specific image.
