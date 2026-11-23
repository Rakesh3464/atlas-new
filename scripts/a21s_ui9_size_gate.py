#!/usr/bin/env python3
"""Read-only super sizing gate for an UNTESTED Samsung A21s One UI 9 port."""
import json
from pathlib import Path

# Values measured by prior donor LP metadata and A21s vendor.zip audit.
DONOR_PARTITIONS = {"system": 4878610432, "product": 676745216, "odm": 20971520}
TARGET_VENDOR_BYTES = 846389248
ALIGNMENT = 1048576
CONSERVATIVE_RESERVE = 32 * ALIGNMENT

def aligned(n):
    return ((n + ALIGNMENT - 1) // ALIGNMENT) * ALIGNMENT

def calculate(super_bytes):
    inputs = {**DONOR_PARTITIONS, "vendor": TARGET_VENDOR_BYTES}
    padded = {name: aligned(size) for name, size in inputs.items()}
    allocated = sum(padded.values())
    return {
        "assumed_super_bytes": super_bytes,
        "partition_bytes": inputs,
        "padded_partition_bytes": padded,
        "aligned_partition_sum": allocated,
        "reserve_bytes": CONSERVATIVE_RESERVE,
        "remaining_after_reserve_bytes": super_bytes - allocated - CONSERVATIVE_RESERVE,
        "fits_size_budget_only": allocated + CONSERVATIVE_RESERVE <= super_bytes,
    }

def main():
    out = Path("reports")
    out.mkdir(exist_ok=True)
    decimal = calculate(10_000_000_000)
    binary = calculate(10 * (1024 ** 3))
    info = {
        "target": "Samsung A21s SM-A217F",
        "source": "Donor SkyUI Cirrus 9; A21s VNDK31 vendor",
        "warning": "User-reported 10 GB is not verified exact physical partition size",
        "cases": {"decimal_10GB": decimal, "binary_10GiB": binary},
        "flashable": False,
    }
    (out / "a21s-super-fit.json").write_text(json.dumps(info, indent=2) + "\n")
    lines = [
        "# A21s One UI 9 preliminary super partition fit report",
        "",
        "READ-ONLY analysis. This is NOT a built ROM or flashable super image.",
        "",
        "The reported super size is 10 GB. The exact partition size in bytes has not been verified on the phone.",
        "",
        "| Partition | Image size (bytes) | 1 MiB-aligned allocation (bytes) |",
        "|---|---:|---:|",
    ]
    for name, size in decimal["partition_bytes"].items():
        lines.append(f"| {name} | {size:,} | {decimal['padded_partition_bytes'][name]:,} |")
    lines += [
        "",
        f"Total aligned images: {decimal['aligned_partition_sum']:,} bytes",
        f"Conservative calculation reserve: {CONSERVATIVE_RESERVE:,} bytes",
        "",
        "| Interpretation | Super bytes | Remaining after reserve | Arithmetic fit |",
        "|---|---:|---:|---|",
    ]
    for name, result in [("10 GB decimal", decimal), ("10 GiB binary", binary)]:
        lines.append(f"| {name} | {result['assumed_super_bytes']:,} | {result['remaining_after_reserve_bytes']:,} | {result['fits_size_budget_only']} |")
    lines += [
        "",
        "## Validation blockers before flash-ready build",
        "",
        "1. Confirm exact actual A21s physical super bytes using blockdev --getsize64 against the correct by-name partition.",
        "2. Extract target LP metadata: metadata slots, partition groups, geometry and alignment; do not copy donor geometry blindly.",
        "3. Compare donor system/product/odm with target VNDK31 / Android 12 / VINTF target-level 4 and SELinux mappings.",
        "4. Preserve A21s-specific boot.img, dtbo.img, vendor/HALs, camera and radio. Never flash M21/M31 donor super to A21s.",
        "",
        "VERDICT: Arithmetic fit is feasible if A21s really has a 10 GB physical super partition; bootability is not established.",
        "",
    ]
    report = "\n".join(lines)
    (out / "a21s-super-fit.md").write_text(report)
    print(report)
    if not decimal["fits_size_budget_only"]:
        raise SystemExit("Conservative decimal 10 GB fit failed")

if __name__ == "__main__":
    main()
