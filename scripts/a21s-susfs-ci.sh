#!/usr/bin/env bash
# Samsung A21s / Exynos850 / Linux 4.19 — SUSFS source build, NOT FLASHABLE.
set -Eeuo pipefail
ROOT="$(pwd)"
REPORT="$ROOT/artifacts"
mkdir -p "$REPORT"
stage="initialization"
cleanup() {
  code=$?
  {
    echo "Stage: $stage"
    echo "Exit code: $code"
    echo "Repository: Rakesh3464/atlas-new"
    echo "Kernel: 4.19.325"
    echo "Output is NOT a flash-ready boot.img; device boot has not been verified."
    if [[ -d "$ROOT/susfs4ksu/.git" ]]; then git -C "$ROOT/susfs4ksu" rev-parse HEAD || true; fi
    if [[ -d "$ROOT/KernelSU" ]]; then git -C "$ROOT/KernelSU" rev-parse HEAD || true; fi
  } > "$REPORT/status.txt"
}
trap cleanup EXIT
echo "A21s SUSFS integration test, not a flashable package."
stage="checking KernelSU submodule"
test -f KernelSU/kernel/Kconfig || { echo "::error::KernelSU submodule is missing. Aborting."; exit 1; }
test -L drivers/kernelsu || { echo "::error::Expected drivers/kernelsu symlink missing."; exit 1; }
test -f arch/arm64/configs/exynos850-a21snsxx_defconfig || { echo "::error::A21s defconfig missing."; exit 1; }

stage="retrieving upstream SUSFS 4.19"
git clone --depth 1 --single-branch --branch kernel-4.19 https://gitlab.com/simonpunk/susfs4ksu.git susfs4ksu
test -f susfs4ksu/kernel_patches/fs/susfs.c || { echo "::error::Missing upstream SUSFS source."; exit 1; }
test -f susfs4ksu/kernel_patches/50_add_susfs_in_kernel-4.19.patch
test -f susfs4ksu/kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch
cp -v susfs4ksu/kernel_patches/fs/susfs.c fs/susfs.c
for f in susfs4ksu/kernel_patches/include/linux/susfs*.h; do
  test -f "$f" || { echo "::error::Missing SUSFS header."; exit 1; }
  cp -v "$f" include/linux/
done

stage="kernel SUSFS patch"
patch --batch --dry-run -p1 < susfs4ksu/kernel_patches/50_add_susfs_in_kernel-4.19.patch
patch --batch -p1 < susfs4ksu/kernel_patches/50_add_susfs_in_kernel-4.19.patch

stage="KernelSU SUSFS patch"
if grep -Rq '^config KSU_SUSFS' KernelSU/kernel/Kconfig; then
  echo "KernelSU already defines CONFIG_KSU_SUSFS; upstream KernelSU patch skipped."
else
  (cd KernelSU && patch --batch --dry-run -p1 < ../susfs4ksu/kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch)
  (cd KernelSU && patch --batch -p1 < ../susfs4ksu/kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch)
fi
grep -Rq '^config KSU_SUSFS' KernelSU/kernel/Kconfig || { echo "::error::KernelSU SUSFS Kconfig not found."; exit 1; }
{
  echo "Upstream SUSFS commit: $(git -C susfs4ksu rev-parse HEAD)"
  echo "KernelSU commit: $(git -C KernelSU rev-parse HEAD)"
  echo "Kernel source commit: $(git rev-parse HEAD)"
} > "$REPORT/source-revisions.txt"

stage="setting A21s defconfig"
export ARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-
export CROSS_COMPILE_COMPAT=arm-linux-gnueabihf-
export CLANG_TRIPLE=aarch64-linux-gnu-
export CC=clang-14
export LD=ld.lld-14
make O=out ARCH=arm64 exynos850-a21snsxx_defconfig
scripts/config --file out/.config --enable KSU --enable KSU_SUSFS
make O=out ARCH=arm64 olddefconfig
cp out/.config "$REPORT/kernel.config"
grep -qx 'CONFIG_KSU=y' out/.config || { echo "::error::CONFIG_KSU not enabled."; exit 1; }
grep -qx 'CONFIG_KSU_SUSFS=y' out/.config || { echo "::error::CONFIG_KSU_SUSFS not enabled. Dependency or patch failure."; exit 1; }

stage="compiling A21s ARM64 kernel"
make O=out ARCH=arm64 -j2 Image.gz dtbs
test -s out/arch/arm64/boot/Image.gz || { echo "::error::Kernel Image.gz not produced."; exit 1; }
cp out/arch/arm64/boot/Image.gz "$REPORT/Image.gz-UNTESTED"
sha256sum "$REPORT/Image.gz-UNTESTED" > "$REPORT/SHA256SUMS"
stage="source integration and kernel compilation succeeded (boot image NOT built)"
echo "Build passed, but no boot.img is produced; One UI 9 compatibility is NOT verified."
