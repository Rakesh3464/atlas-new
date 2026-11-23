#!/system/bin/sh
# Safe READ-ONLY A21s super geometry collector for rooted Android / recovery.
# No serial, IMEI, account, or private personal information is collected.
# Usage: sh a21s_collect_super_layout.sh > a21s-super-layout.txt

echo 'A21s super partition geometry (READ ONLY)'
echo '========================================'
if command -v getprop >/dev/null 2>&1; then
  printf 'device: '; getprop ro.product.device
  printf 'model: '; getprop ro.product.model
  printf 'slot_suffix: '; getprop ro.boot.slot_suffix
  printf 'dynamic_partitions: '; getprop ro.boot.dynamic_partitions
fi

found=''
for path in /dev/block/by-name/super /dev/block/bootdevice/by-name/super /dev/block/platform/*/by-name/super
do
  if [ -e "$path" ]; then
    found="$path"
    break
  fi
done

if [ -n "$found" ]; then
  echo "super_path: $found"
  resolved=''
  if command -v readlink >/dev/null 2>&1; then
    resolved="$(readlink -f "$found" 2>/dev/null || true)"
    echo "super_device: $resolved"
  fi
  if command -v blockdev >/dev/null 2>&1; then
    size="$(blockdev --getsize64 "$found" 2>/dev/null || true)"
    case "$size" in
      ''|*[!0-9]*) echo 'super_bytes: blockdev unavailable or permission denied' ;;
      *) echo "super_bytes: $size" ;;
    esac
  else
    echo 'super_bytes: blockdev command unavailable'
  fi
  if [ -n "$resolved" ]; then
    devname="$(basename "$resolved")"
    syssectors="/sys/class/block/$devname/size"
    if [ -r "$syssectors" ]; then
      sectors="$(cat "$syssectors" 2>/dev/null || true)"
      case "$sectors" in
        ''|*[!0-9]*) ;;
        *) echo "super_512_byte_sectors: $sectors" ;;
      esac
    fi
  fi
else
  echo 'super_path: NOT FOUND - requires root or custom recovery'
fi

echo '--- liblp metadata ---'
if command -v lpdump >/dev/null 2>&1; then
  lpdump 2>&1 || echo 'lpdump failed (permissions or unsupported version)'
else
  echo 'lpdump: unavailable; run recovery with lpdump installed'
fi
echo '--- end ---'
