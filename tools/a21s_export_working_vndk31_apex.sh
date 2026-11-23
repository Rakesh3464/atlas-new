#!/system/bin/sh
# A21s VNDK31 APEX read-only export from a KNOWN WORKING Android 12 vendor ROM.
# Run on the Samsung A21s itself, with root/recovery permissions.
# Does not alter system, vendor, boot, super, vbmeta, or any device partitions.
set -eu
OUT="/sdcard/Download/A21s-VNDK31-Source"
mkdir -p "$OUT"
printf '%s\n' 'A21s VNDK31 APEX source audit (read-only)' > "$OUT/source-info.txt"
printf 'device: ' >> "$OUT/source-info.txt"
getprop ro.product.device >> "$OUT/source-info.txt" 2>/dev/null || true
printf 'vendor_vndk: ' >> "$OUT/source-info.txt"
getprop ro.vndk.version >> "$OUT/source-info.txt" 2>/dev/null || true
FOUND=""
for ROOT in /system_ext/apex /system/system_ext/apex /system/apex /apex; do
  for FILE in "$ROOT/com.android.vndk.v31.apex" "$ROOT/com.android.vndk.v31.capex"; do
    if [ -f "$FILE" ]; then
      FOUND="$FILE"
      break
    fi
  done
  if [ -n "$FOUND" ]; then break; fi
done
if [ -z "$FOUND" ]; then
  printf '%s\n' 'VNDK31 APEX not present in common paths. Do not copy VNDK33 instead.' | tee -a "$OUT/source-info.txt"
  exit 2
fi
DEST="$OUT/$(basename "$FOUND")"
cp "$FOUND" "$DEST"
chmod 644 "$DEST" 2>/dev/null || true
printf 'original_path: %s\n' "$FOUND" >> "$OUT/source-info.txt"
printf 'file_bytes: %s\n' "$(wc -c < "$DEST" | tr -d ' ')" >> "$OUT/source-info.txt"
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$DEST" > "$OUT/SHA256SUMS.txt"
fi
echo "Export complete: $DEST"
echo 'Only read operations occurred on the system partitions.'
echo 'Share the APEX binary plus source-info.txt for validation, NOT for flashing.'
