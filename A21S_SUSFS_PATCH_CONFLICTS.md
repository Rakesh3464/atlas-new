# SUSFS 4.19 patch dry-run #2 — confirmed conflicts

Source: uploaded `a21s-susfs-419-patch-dry-run (1).zip`.
Reference SUSFS revision: `001e69919c6271f690fd00b17e4c721c9e599152` (SUSFS 1.5.5 reference, **not v2.4.0**).

## Results
- Kernel patch dry run: exit code **1**.
- KernelSU patch dry run: exit code **1**.
- Neither patch was applied; no Image built.

### Kernel-side failed hunks
| File | Failed / total hunks |
| --- | --- |
| fs/namespace.c | 4 / 16 |
| fs/proc/task_mmu.c | 1 / 3 |
| include/linux/mount.h | 1 / 1 |
| include/linux/sched.h | 1 / 2 |
| kernel/sys.c | 1 / 1 |

Other hunks applied in dry-run with offsets or fuzz and require review.

### KernelSU-side mismatches
- `kernel/Makefile`: 2/2 hunks failed.
- `kernel/ksu.c`: 4/5 hunks failed.
- `kernel/selinux/rules.c`: 3/3 hunks failed.
- `kernel/selinux/selinux.c`: 6/7 hunks failed.
- `kernel/selinux/selinux.h`: 1/1 hunk failed.
- Several expected source files were missing, including `kernel/allowlist.c`, `kernel/core_hook.c`, `kernel/ksud.c`, `kernel/sucompat.c` and `kernel/throne_tracker.c`.

## Next safe implementation step
Compare the exact KernelSU submodule revision `648e5988cf421172769f80ce07f86331b548c053` with the patch's expected KernelSU source revision; identify an appropriate SUSFS-compatible KernelSU baseline before manually porting hooks. Do not blindly force patch hunks or distribute a flashable Image. Porting SUSFS v2.4.0 is a separate uncompleted task.
