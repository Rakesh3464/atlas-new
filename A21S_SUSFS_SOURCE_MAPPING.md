# A21s SUSFS port — source mapping (verified from CI artifacts)

Artifacts inspected: `a21s-susfs-port-staging.zip` and `a21s-susfs-conflict-source-context.zip`.

## Current KernelSU build structure

`KernelSU/kernel/ksu.c` is a unity-build translation unit; it includes implementation files directly, including:

| Older SUSFS reference target | Current source location |
| --- | --- |
| `kernel/allowlist.c` | `kernel/policy/allowlist.c` |
| `kernel/ksud.c` | `kernel/runtime/ksud.c` |
| `kernel/sucompat.c` | `kernel/feature/sucompat.c` |
| `kernel/throne_tracker.c` | `kernel/manager/throne_tracker.c` |
| `kernel/core_hook.c` | **No direct file of that name**; inspect `kernel/hook/lsm_hook.c`, `kernel/supercall/`, and `kernel/ksu.c` for equivalent functionality before porting |

This is a source-path map, **not** a claim that the old patch's code can be copied unchanged. Its function signatures, policy, SELinux behavior, and initialization must be reconciled.

## Known kernel conflicts

- `fs/namespace.c`: 4 rejected hunks
- `fs/proc/task_mmu.c`: 1 rejected hunk
- `include/linux/mount.h`: 1 rejected hunk
- `include/linux/sched.h`: 1 rejected hunk
- `kernel/sys.c`: 1 rejected hunk

## Safe next implementation

1. Work on a dedicated integration branch, not master.
2. Resolve filesystem rejected hunks against the current Samsung code, keeping existing vendor semantics.
3. Rebase the SUSFS/KernelSU glue onto the current unity-build implementation, not the obsolete file paths.
4. Enable SUSFS config only after source and headers are integrated; compile and inspect warnings.
5. Boot-test on hardware with a known recovery path before labeling anything flash-ready.

The pinned reference in the staging artifact is SUSFS 1.5.5 for 4.19, **not SUSFS 2.4.0**. No functional SUSFS kernel is demonstrated by these artifacts.
