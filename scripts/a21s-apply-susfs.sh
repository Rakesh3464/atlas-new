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

# The pinned KernelSU main commit has an incompatible API: the v1.5.8
# SUSFS KernelSU patch targets files absent from this checkout.
# Test the legacy branch that already carries integrated SUSFS hooks instead.
# This is isolated to the Actions workspace; NEVER alter the submodule pointer.
legacy_ksu_sha="6b1ce5d1fbf9068744b4b7023c7049e14e2e0fcd"
git -C KernelSU fetch --depth 1 https://github.com/rksuorg/KernelSU.git refs/heads/deprecated/susfs-legacy
git -C KernelSU checkout --detach "$legacy_ksu_sha"
test "$(git -C KernelSU rev-parse HEAD)" = "$legacy_ksu_sha"
grep -q '^config KSU_SUSFS
cp "$src/fs/susfs.c" fs/susfs.c
cp "$src/include/linux/susfs.h" include/linux/susfs.h
cp "$src/include/linux/susfs_def.h" include/linux/susfs_def.h
if test -f "$src/fs/sus_su.c"; then cp "$src/fs/sus_su.c" fs/sus_su.c; fi
if test -f "$src/include/linux/sus_su.h"; then cp "$src/include/linux/sus_su.h" include/linux/sus_su.h; fi
if test -f "$src/KernelSU/kernel/sucompat.h"; then cp "$src/KernelSU/kernel/sucompat.h" KernelSU/kernel/sucompat.h; fi

python3 scripts/a21s-port-susfs.py "$kernel_patch"
# Native SUSFS hooks already present in the selected KernelSU legacy branch.

# A21s already uses manual hooks: avoid double SUS_SU hook where available.
cfg="arch/arm64/configs/exynos850-a21snsxx_defconfig"
if grep -q '^CONFIG_KSU_MANUAL_HOOK=y' "$cfg"; then
  printf '\n# Keep existing A21s manual root hooks\n# CONFIG_KSU_SUSFS_SUS_SU is not set\n' >> "$cfg"
fi
printf '\nCONFIG_KSU=y\nCONFIG_KSU_SUSFS=y\n' >> "$cfg"
echo "SUSFS patches applied in CI working tree. Build and runtime validation still required."
 KernelSU/kernel/Kconfig || {
  echo "Pinned legacy KernelSU does not include native SUSFS support"; exit 1;
}
echo "Using pinned KernelSU integrated SUSFS legacy branch for CI trial"

cp "$src/fs/susfs.c" fs/susfs.c
cp "$src/include/linux/susfs.h" include/linux/susfs.h
cp "$src/include/linux/susfs_def.h" include/linux/susfs_def.h
if test -f "$src/fs/sus_su.c"; then cp "$src/fs/sus_su.c" fs/sus_su.c; fi
if test -f "$src/include/linux/sus_su.h"; then cp "$src/include/linux/sus_su.h" include/linux/sus_su.h; fi
if test -f "$src/KernelSU/kernel/sucompat.h"; then cp "$src/KernelSU/kernel/sucompat.h" KernelSU/kernel/sucompat.h; fi

python3 scripts/a21s-port-susfs.py "$kernel_patch"
(cd KernelSU && patch -p1 --batch --forward < "$ksu_patch")

# A21s already uses manual hooks: avoid double SUS_SU hook where available.
cfg="arch/arm64/configs/exynos850-a21snsxx_defconfig"
if grep -q '^CONFIG_KSU_MANUAL_HOOK=y' "$cfg"; then
  printf '\n# Keep existing A21s manual root hooks\n# CONFIG_KSU_SUSFS_SUS_SU is not set\n' >> "$cfg"
fi
printf '\nCONFIG_KSU=y\nCONFIG_KSU_SUSFS=y\n' >> "$cfg"
echo "SUSFS patches applied in CI working tree. Build and runtime validation still required."
