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

# The A21s-specific adaptations are already committed to the manual-port branch.
# Skip upstream diffs for ONLY these fully integrated files, and require
# their markers before doing so. All other patch hunks remain fail-closed.
grep -Fqx 'obj-$(CONFIG_KSU_SUSFS) += susfs.o' fs/Makefile || {
  echo "Missing manually ported fs/Makefile integration"; exit 1;
}
grep -Fq 'ANDROID_KABI_USE(4, u64 susfs_mnt_id_backup)' include/linux/mount.h || {
  echo "Missing manually ported mount KABI field"; exit 1;
}
grep -Fq 'susfs_spoof_uname(&tmp);' kernel/sys.c || {
  echo "Missing manually ported uname hook"; exit 1;
}
python3 - "$kernel_patch" "$work/a21s-kernel.patch" <<'PY'
import re
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text()
manual = {"fs/Makefile", "include/linux/mount.h", "kernel/sys.c"}
parts = re.split(r"(?=^diff --git a/)", raw, flags=re.MULTILINE)
found = set()
kept = []
for part in parts:
    match = re.match(r"diff --git a/(\S+) b/", part)
    if match and match.group(1) in manual:
        found.add(match.group(1))
        continue
    kept.append(part)
if found != manual:
    raise SystemExit("Missing expected upstream diff sections: " + repr(manual-found))
Path(sys.argv[2]).write_text("".join(kept))
PY
kernel_patch="$work/a21s-kernel.patch"

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
