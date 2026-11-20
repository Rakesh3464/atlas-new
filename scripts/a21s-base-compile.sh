#!/usr/bin/env bash
# Build prerequisite check for A21s Atlas 4.19; NO boot.img, NO flashing.
set -Eeuo pipefail
mkdir -p artifacts
step="initial"
finish() {
  rc=$?
  {
    printf 'stage=%s\n' "$step"
    printf 'exit_code=%d\n' "$rc"
    printf 'kernel_repo=%s\n' "Rakesh3464/atlas-new"
    printf 'kernel_commit=%s\n' "$(git rev-parse HEAD)"
    printf 'kernel_su_commit=%s\n' "$(git -C KernelSU rev-parse HEAD 2>/dev/null || echo missing)"
    printf 'flash_ready=no\n'
    printf 'susfs_integrated=no\n'
  } > artifacts/status.txt
}
trap finish EXIT
step="source preflight"
test -f Makefile
test -f arch/arm64/configs/exynos850-a21snsxx_defconfig
test -f KernelSU/kernel/Kconfig
test -L drivers/kernelsu
echo "Compiler versions:"
clang-14 --version | head -n 1
ld.lld-14 --version
aarch64-linux-gnu-gcc --version | head -n 1
step="A21s defconfig"
make O=out ARCH=arm64 CC=clang-14 LD=ld.lld-14 \
 CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_COMPAT=arm-linux-gnueabihf- \
 exynos850-a21snsxx_defconfig
cp out/.config artifacts/a21s.config
grep -E '^(CONFIG_KSU|# CONFIG_KSU|CONFIG_LTO|CONFIG_CC_IS_CLANG|CONFIG_KSU_SUSFS)' out/.config | tee artifacts/build-config-summary.txt || true
step="compile original A21s 4.19 kernel (without SUSFS)"
make O=out ARCH=arm64 CC=clang-14 LD=ld.lld-14 \
 CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_COMPAT=arm-linux-gnueabihf- \
 -j2 Image.gz
test -s out/arch/arm64/boot/Image.gz
cp out/arch/arm64/boot/Image.gz artifacts/atlas-a21s-base-Image.gz-UNTESTED
sha256sum artifacts/atlas-a21s-base-Image.gz-UNTESTED > artifacts/SHA256SUMS
step="base A21s kernel compilation complete (NOT boot tested, NOT SUSFS)"
