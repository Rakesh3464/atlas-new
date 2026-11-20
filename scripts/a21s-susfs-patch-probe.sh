#!/usr/bin/env bash
# A21s Linux 4.19 SUSFS patch compatibility probe (READ-ONLY, NO FLASHABLE OUTPUT)
set -Eeuo pipefail
mkdir -p artifacts/susfs-probe
report="artifacts/susfs-probe/results.tsv"
printf 'susfs_ref\tcore_patch_exit\tksu_patch_exit\tfailed_hunks\n' > "$report"
for ref in kernel-4.19 1.4.2-kernel-4.19; do
  echo "::group::Inspect SUSFS ref $ref"
  out="artifacts/susfs-probe/${ref}"
  mkdir -p "$out"
  if ! git clone -q --depth 1 --single-branch --branch "$ref" \
       https://gitlab.com/simonpunk/susfs4ksu.git "susfs-probe-${ref}" 2>"$out/clone.err"; then
    echo "Clone failed for $ref"
    cat "$out/clone.err"
    printf '%s\tCLONE_FAILED\tNOT_CHECKED\tN/A\n' "$ref" >> "$report"
    echo "::endgroup::"
    continue
  fi
  src="susfs-probe-${ref}"
  git -C "$src" rev-parse HEAD > "$out/upstream-sha.txt"
  patch_path="$src/kernel_patches/50_add_susfs_in_kernel-4.19.patch"
  ksu_path="$src/kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch"
  if [[ ! -s "$patch_path" ]]; then
    echo "Missing kernel patch file"
    printf '%s\tMISSING\tNOT_CHECKED\tN/A\n' "$ref" >> "$report"
    echo "::endgroup::"
    continue
  fi
  set +e
  patch --batch --dry-run --fuzz=2 -p1 < "$patch_path" > "$out/kernel-patch.log" 2>&1
  a=$?
  if [[ -s "$ksu_path" ]]; then
    (cd KernelSU && patch --batch --dry-run --fuzz=2 -p1 < "../$ksu_path") > "$out/ksu-patch.log" 2>&1
    b=$?
  else
    b=99
    echo "Missing KernelSU patch" > "$out/ksu-patch.log"
  fi
  set -e
  failed="$(grep -Ec 'FAILED at|FAILED to apply|out of|malformed patch|can.t find file' "$out/kernel-patch.log" || true)"
  printf '%s\t%s\t%s\t%s\n' "$ref" "$a" "$b" "$failed" >> "$report"
  echo "Kernel SUSFS patch status: $a, KernelSU patch status: $b, rejected hunks: $failed"
  grep -E '(FAILED|Hunk|checking file)' "$out/kernel-patch.log" | tail -n 85 || true
  echo "::endgroup::"
done
echo "No file was flashed or changed. Patch compatibility only."
cat "$report"
