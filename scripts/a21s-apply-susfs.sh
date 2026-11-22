#!/usr/bin/env bash
# A21s Linux 4.19 SUSFS test integration. Never flash this source-only build.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
test -f Makefile && test -d KernelSU/kernel || { echo "Missing kernel tree or KernelSU"; exit 1; }
cfg="arch/arm64/configs/exynos850-a21snsxx_defconfig"
test -f "$cfg" || { echo "Missing A21s defconfig"; exit 1; }

SUSFS_REPO="https://github.com/XxRagulxX/Susfs-patch.git"
SUSFS_BRANCH="kernel-4.19"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone --depth 1 --single-branch --branch "$SUSFS_BRANCH" "$SUSFS_REPO" "$work/susfs"
src="$work/susfs/kernel_patches"
kernel_patch="$src/50_add_susfs_in_kernel-4.19.patch"
for f in "$kernel_patch" "$src/fs/susfs.c" "$src/include/linux/susfs.h" "$src/include/linux/susfs_def.h"; do
  test -s "$f" || { echo "Missing required SUSFS source: $f"; exit 1; }
done

# Pin a SUSFS-integrated KernelSU revision in CI only. The default KernelSU
# revision has a different API and rejects 10_enable_susfs_for_ksu.patch.
# Do not modify the repository's submodule pointer or booted V2 kernel.
legacy_ksu_sha="6b1ce5d1fbf9068744b4b7023c7049e14e2e0fcd"
git -C KernelSU fetch --depth 1 https://github.com/rksuorg/KernelSU.git refs/heads/deprecated/susfs-legacy
git -C KernelSU checkout --detach "$legacy_ksu_sha"
test "$(git -C KernelSU rev-parse HEAD)" = "$legacy_ksu_sha"
grep -q '^config KSU_SUSFS$' KernelSU/kernel/Kconfig || {
  echo "Pinned legacy KernelSU lacks native SUSFS integration"; exit 1;
}
echo "Pinned SUSFS-enabled KernelSU checkout succeeded."

cp "$src/fs/susfs.c" fs/susfs.c
cp "$src/include/linux/susfs.h" include/linux/susfs.h
cp "$src/include/linux/susfs_def.h" include/linux/susfs_def.h
if test -f "$src/fs/sus_su.c"; then cp "$src/fs/sus_su.c" fs/sus_su.c; fi
if test -f "$src/include/linux/sus_su.h"; then cp "$src/include/linux/sus_su.h" include/linux/sus_su.h; fi

# Apply remaining upstream SUSFS hunks and A21s-specific fs_context mounts.
python3 scripts/a21s-port-susfs.py "$kernel_patch"

# Keep existing A21s manual root hooks; avoid a duplicate SUS_SU hook.
if grep -q '^CONFIG_KSU_MANUAL_HOOK=y' "$cfg"; then
  printf '\n# CONFIG_KSU_SUSFS_SUS_SU is not set\n' >> "$cfg"
fi
printf '\nCONFIG_KSU=y\nCONFIG_KSU_SUSFS=y\n' >> "$cfg"
echo "SUSFS integration applied in temporary CI tree; compilation and boot validation required."
