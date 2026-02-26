#!/usr/bin/env python3
"""
Empirical test: verify that size_component >= serde_2026_bytes for all generators.

Tests two formula variants:
  Old (A=2, P=2): atom_bytes + 2*atom_count + 2*pair_count
  Fix (A=2, P=3): atom_bytes + 2*atom_count + 3*pair_count

Usage:
  uv run scripts/test_serde2026_upper_bound.py
"""

import subprocess
import sys
from pathlib import Path

CLVM_SERDE = Path.home() / "projects/clvm_rs/serde_2026.messy/serde_2026/target/release/clvm-serde"
GENERATORS_DIR = Path.home() / "projects/clvm_rs/bench_large_generator/benches"


def run_clvm_serde(gen_path: Path) -> dict | None:
    """Run clvm-serde on a generator file and parse the output."""
    try:
        result = subprocess.run(
            [str(CLVM_SERDE), str(gen_path), "--sizes", "--stats"],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return None

    if result.returncode != 0:
        print(f"  ERROR: clvm-serde returned {result.returncode}", file=sys.stderr)
        return None

    data = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if "2026:" in line and "bytes" in line:
            data["serde_2026"] = int(line.split()[1])
        elif "classic:" in line and "bytes" in line:
            data["classic"] = int(line.split()[1])
        elif "atom_count:" in line:
            data["atom_count"] = int(line.split()[1])
        elif "pair_count:" in line:
            data["pair_count"] = int(line.split()[1])
        elif "atom_bytes:" in line:
            data["atom_bytes"] = int(line.split()[1])
        elif "size_component =" in line:
            # Format: "size_component = 1×N + 2×M + 2×P = X"
            data["size_comp_a2p2"] = int(line.split("=")[-1].strip())

    required = {"serde_2026", "atom_count", "pair_count", "atom_bytes", "size_comp_a2p2"}
    if not required.issubset(data):
        print(f"  ERROR: missing fields: {required - set(data)}", file=sys.stderr)
        return None

    # Compute A=2, P=3 formula
    data["size_comp_a2p3"] = (
        data["atom_bytes"] + 2 * data["atom_count"] + 3 * data["pair_count"]
    )
    return data


def main():
    if not CLVM_SERDE.exists():
        print(f"ERROR: clvm-serde not found at {CLVM_SERDE}", file=sys.stderr)
        print("Build with: cd ~/projects/clvm_rs/serde_2026.messy/serde_2026 &&", file=sys.stderr)
        print("           cargo build --release -p clvm-rs-test-tools --bin clvm-serde", file=sys.stderr)
        sys.exit(1)

    if not GENERATORS_DIR.exists():
        print(f"ERROR: generators not found at {GENERATORS_DIR}", file=sys.stderr)
        sys.exit(1)

    generators = sorted(GENERATORS_DIR.glob("*.generator"))
    if not generators:
        print(f"ERROR: no *.generator files in {GENERATORS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Testing {len(generators)} generators\n")

    # Header
    hdr = f"{'file':<20} {'classic':>8} {'serde_26':>9} {'sc(A2P2)':>9} {'A2P2≥?':>7} {'sc(A2P3)':>9} {'A2P3≥?':>7} {'margin':>8}"
    print(hdr)
    print("-" * len(hdr))

    all_pass_old = True
    all_pass_new = True
    results = []

    for gen in generators:
        data = run_clvm_serde(gen)
        if data is None:
            print(f"{gen.name:<20}  (failed to parse)")
            continue

        serde = data["serde_2026"]
        classic = data.get("classic", 0)
        sc_old = data["size_comp_a2p2"]
        sc_new = data["size_comp_a2p3"]
        pass_old = sc_old >= serde
        pass_new = sc_new >= serde

        if not pass_old:
            all_pass_old = False
        if not pass_new:
            all_pass_new = False

        margin = sc_new - serde
        results.append((gen.name, data, pass_old, pass_new, margin))

        print(
            f"{gen.name:<20} {classic:>8,} {serde:>9,} {sc_old:>9,} "
            f"{'PASS' if pass_old else 'FAIL':>7} {sc_new:>9,} "
            f"{'PASS' if pass_new else 'FAIL':>7} {margin:>8,}"
        )

    print()
    print("Summary:")
    print(f"  A=2, P=2 formula (original): {'ALL PASS' if all_pass_old else 'FAILS'}")
    print(f"  A=2, P=3 formula (proposed): {'ALL PASS' if all_pass_new else 'FAILS'}")

    if results:
        min_margin = min(m for _, _, _, _, m in results)
        max_margin = max(m for _, _, _, _, m in results)
        print(f"\n  A=2, P=3 margins: min={min_margin:,}  max={max_margin:,}")

    if not all_pass_new:
        print("\nERROR: proposed formula A=2,P=3 does not hold!", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nOK: formula A=2, P=3 is an upper bound for all test generators.")


if __name__ == "__main__":
    main()
