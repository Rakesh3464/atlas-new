# Samsung A21s SM-A217F — One UI 9 Port status (23 Nov 2026)

**Status: experimental, untested, DO NOT FLASH.**

## Confirmed artifacts

- Previous donor/target assembly GitHub run: https://github.com/Rakesh3464/atlas-new/actions/runs/45159177148
- Prototype LP images: donor Android 17 system (ext4), donor product (converted EROFS→ext4), donor odm (ext4), Samsung A21s Android 12 vendor (ext4).
- SHA-256 partition verification passed (4/4); only payload integrity was checked.
- Target original A21s boot.img and dtbo.img were kept unchanged.
- Assumed physical super geometry was **9,999,998,976 bytes** after 4096-byte alignment of a user-reported 10 GB. This is a **guess, not measured from the target device**.
- Boot, AVB, hardware camera, VINTF and SELinux integration were NOT tested.

## New verified donor/system preflight

GitHub run: https://github.com/Rakesh3464/atlas-new/actions/runs/45161957287

| Check | Observed | Implication |
|---|---|---|
| Donor platform | Android 17, API 37 | Higher version than target vendor |
| A21s vendor | Android 12, VNDK 31 | Keep target hardware HALs for camera/radio |
| Vendor FCM level | 4 | Need framework compatibility for FCM4 |
| Donor VNDK31 APEX / legacy vndk-31 directories | Not found in inspected system paths | Older vendor linkage support remains UNCONFIRMED |
| Donor framework compatibility matrices listed | 7, 8, 202404, 202504, 202604 | No FCM level-4 matrix found in inspected system |
| Donor SELinux policy mapping files | 31.0, 32.0, 33.0, 34.0, 202404, 202504, 202604 | Presence alone does not validate target vendor policy |

**A missing APEX or matrix in the scanned paths is not, by itself, a proof of impossible boot.** Vendor/system compatibility needs full libvintf checks, shipped APEX inspection, policy validation and physical device boot logs.

## To progress safely

1. Read **exact** A21s physical super block-device byte size and LP metadata from the phone; no more rounding. A read-only helper is at [a21s_collect_super_layout.sh](tools/a21s_collect_super_layout.sh).
2. Identify a validated Android 17 framework build capable of supporting the target VNDK31/FCM4 stack, or port the required verified system components with correct SELinux policies.
3. Rebuild super using actual target LP partition geometry and verify all partition hashes.
4. Check AVB/vbmeta, mount configuration and boot logs. A checked artifact is not equivalent to a bootable ROM.

**Flash-ready approval: NOT GIVEN. Do not flash experimental 10 GB super.img.**
