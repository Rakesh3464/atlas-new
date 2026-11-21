#!/usr/bin/env bash
# A21s Linux 4.19: SUSFS integration for CI only.
# Not a flashable boot.img. Fail on incomplete / incompatible patch application.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
test -f Makefile && test -d KernelSU/kernel || { echo "Missing kernel tree or KernelSU submodule"; exit 1; }
test -f arch/arm64/configs/exynos850-a21snsxx_defconfig || { echo "Missing A21s defconfig"; exit 1; }

SUSFS_REPO="https://github.com/XxRagulxX/Susfs-patch.git"
SUSFS_BRANCH="kernel-4.19"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone --depth 1 --single-branch --branch "$SUSFS_BRANCH" "$SUSFS_REPO" "$work/susfs"
src="$work/susfs/kernel_patches"
kernel_patch="$src/50_add_susfs_in_kernel-4.19.patch"
ksu_patch="$src/KernelSU/10_enable_susfs_for_ksu.patch"
for f in "$kernel_patch" "$ksu_patch" "$src/fs/susfs.c" "$src/include/linux/susfs.h" "$src/include/linux/susfs_def.h"; do
  test -s "$f" || { echo "SUSFS required file absent: $f"; exit 1; }
done

# This Samsung A21s tree has a diverged fs/Makefile. Its SUSFS object
# is integrated separately on the port branch, so omit ONLY that upstream hunk.
# Preserve every other hunk and fail closed on conflicts.
if grep -Fqx 'obj-$(CONFIG_KSU_SUSFS) += susfs.o' fs/Makefile; then
  python3 - "$kernel_patch" "$work/a21s-kernel.patch" <<'PY'
import sys
from pathlib import Path
patch = Path(sys.argv[1]).read_text()
start = patch.find("diff --git a/fs/Makefile b/fs/Makefile")
next_file = patch.find("diff --git a/fs/dcache.c b/fs/dcache.c", start)
if start < 0 or next_file < 0:
    raise SystemExit("Expected upstream SUSFS Makefile/dcache diff boundaries missing")
Path(sys.argv[2]).write_text(patch[:start] + patch[next_file:])
PY
  kernel_patch="$work/a21s-kernel.patch"
fi

# Check before copying anything. Never silently skip failing hunks.
patch -p1 --dry-run --batch --forward < "$kernel_patch" || {
  echo "A21s 4.19 SUSFS kernel patch conflicts. Manual port required."; exit 1;
}
(cd KernelSU && patch -p1 --dry-run --batch --forward < "$ksu_patch") || {
  echo "KernelSU version is incompatible with selected SUSFS patch. Manual port required."; exit 1;
}

cp "$src/fs/susfs.c" fs/susfs.c
cp "$src/include/linux/susfs.h" include/linux/susfs.h
cp "$src/include/linux/susfs_def.h" include/linux/susfs_def.h
if test -f "$src/fs/sus_su.c"; then cp "$src/fs/sus_su.c" fs/sus_su.c; fi
if test -f "$src/include/linux/sus_su.h"; then cp "$src/include/linux/sus_su.h" include/linux/sus_su.h; fi
if test -f "$src/KernelSU/kernel/sucompat.h"; then cp "$src/KernelSU/kernel/sucompat.h" KernelSU/kernel/sucompat.h; fi

patch -p1 --batch --forward < "$kernel_patch"
(cd KernelSU && patch -p1 --batch --forward < "$ksu_patch")

# A21s already uses manual hooks: avoid double SUS_SU hook where available.
cfg="arch/arm64/configs/exynos850-a21snsxx_defconfig"
if grep -q '^CONFIG_KSU_MANUAL_HOOK=y' "$cfg"; then
  printf '\n# Keep existing A21s manual root hooks\n# CONFIG_KSU_SUSFS_SUS_SU is not set\n' >> "$cfg"
fi
printf '\nCONFIG_KSU=y\nCONFIG_KSU_SUSFS=y\n' >> "$cfg"
echo "SUSFS patches applied in CI working tree. Build and runtime validation still required."
