#!/usr/bin/env python3
"""
DoS analysis for the cost formula.

Creates adversarial generator structures and verifies the cost formula
charges appropriately for the work required.

Key principle: All adversarial structures should cost MORE (or similar)
compared to the old formula, ensuring no DoS vector is undercharged.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clvm_rs import Program

from canon_analysis import cost_components, calculate_cost, CostCoefficients


@dataclass
class AdversarialCase:
    """An adversarial test case."""

    name: str
    description: str
    builder: Callable[[int], Program]
    target_size: int = 100_000  # Target ~100KB


def build_nil_atoms(count: int) -> Program:
    """Build a list of nil atoms (zero-byte atoms)."""
    # (nil nil nil ... nil)
    result = Program.to(None)
    for _ in range(count):
        result = Program.to((None, result))
    return result


def build_deep_nesting(depth: int) -> Program:
    """Build deeply nested pairs: ((((...nil)...)))"""
    result = Program.to(None)
    for _ in range(depth):
        result = Program.to((result, None))
    return result


def build_hash_atoms(count: int) -> Program:
    """Build a list of 32-byte atoms (hash-sized)."""
    result = Program.to(None)
    for i in range(count):
        # Create unique 32-byte atoms
        atom = i.to_bytes(32, "big")
        result = Program.to((atom, result))
    return result


def build_tiny_atoms(count: int) -> Program:
    """Build a list of 1-byte atoms."""
    result = Program.to(None)
    for i in range(count):
        atom = bytes([i % 256])
        result = Program.to((atom, result))
    return result


def build_huge_atom(size: int) -> Program:
    """Build a single large atom."""
    return Program.to(bytes(size))


def build_balanced_tree(depth: int) -> Program:
    """Build a balanced binary tree."""
    if depth == 0:
        return Program.to(b"leaf")

    left = build_balanced_tree(depth - 1)
    right = build_balanced_tree(depth - 1)
    return Program.to((left, right))


def build_repeated_subtree(repetitions: int, subtree_size: int = 10) -> Program:
    """Build a structure with many references to the same subtree."""
    # Create a subtree
    subtree = Program.to(None)
    for i in range(subtree_size):
        subtree = Program.to((bytes([i]), subtree))

    # Reference it many times
    result = Program.to(None)
    for _ in range(repetitions):
        result = Program.to((subtree, result))
    return result


# Define test cases
ADVERSARIAL_CASES = [
    AdversarialCase(
        name="million_nil_atoms",
        description="Many zero-byte atoms (high invocation count)",
        builder=lambda n: build_nil_atoms(n),
        target_size=50_000,  # ~50K nil atoms
    ),
    AdversarialCase(
        name="deep_nesting",
        description="Deeply nested pairs",
        builder=lambda n: build_deep_nesting(n),
        target_size=50_000,
    ),
    AdversarialCase(
        name="hash_sized_atoms",
        description="Many 32-byte atoms (typical puzzle data)",
        builder=lambda n: build_hash_atoms(n),
        target_size=3000,  # 3K × 32 bytes ≈ 100KB
    ),
    AdversarialCase(
        name="tiny_atoms",
        description="Many 1-byte atoms",
        builder=lambda n: build_tiny_atoms(n),
        target_size=30_000,
    ),
    AdversarialCase(
        name="single_huge_atom",
        description="One large atom (low node count)",
        builder=lambda n: build_huge_atom(n),
        target_size=100_000,
    ),
    AdversarialCase(
        name="balanced_tree",
        description="Balanced binary tree (moderate depth)",
        builder=lambda n: build_balanced_tree(n),
        target_size=15,  # depth 15 = 32K leaves
    ),
    AdversarialCase(
        name="repeated_subtree",
        description="Many references to same subtree",
        builder=lambda n: build_repeated_subtree(n, 20),
        target_size=5000,
    ),
]


def time_tree_hash(program: Program, iterations: int = 100) -> float:
    """Time tree hash computation."""
    # Warm up
    for _ in range(10):
        program.tree_hash()

    start = time.perf_counter()
    for _ in range(iterations):
        program.tree_hash()
    elapsed = time.perf_counter() - start

    return elapsed / iterations * 1000  # ms


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="DoS analysis for cost formula")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show details")
    parser.add_argument("--time", "-t", action="store_true", help="Include timing")
    args = parser.parse_args()

    coeffs = CostCoefficients()

    print("DoS Analysis: Adversarial Generator Structures")
    print("=" * 70)
    print()
    print("Testing cost formula against adversarial inputs...")
    print("Ratio > 1.0 means new formula charges MORE (safer)")
    print("Ratio < 1.0 means new formula charges LESS (potential DoS)")
    print()

    results = []

    for case in ADVERSARIAL_CASES:
        print(f"Building {case.name}...", end=" ", flush=True)

        try:
            program = case.builder(case.target_size)
            serialized = bytes(program)
            serialized_len = len(serialized)

            components = cost_components(program)
            breakdown = calculate_cost(components, coeffs, serialized_len)

            result = {
                "name": case.name,
                "description": case.description,
                "serialized_len": serialized_len,
                "atom_bytes": components.atom_bytes,
                "atom_count": components.atom_count,
                "pair_count": components.pair_count,
                "old_cost": breakdown.old_cost,
                "new_cost": breakdown.total_cost,
                "ratio": breakdown.cost_ratio,
                "size_frac": breakdown.size_fraction,
                "sha_frac": breakdown.sha_fraction,
            }

            if args.time:
                result["hash_time_ms"] = time_tree_hash(program)

            results.append(result)
            print(f"done ({serialized_len:,} bytes)")

        except Exception as e:
            print(f"ERROR: {e}")
            continue

    print()
    print("Results")
    print("-" * 70)

    # Sort by ratio (lowest first - most concerning)
    results.sort(key=lambda r: r["ratio"])

    for r in results:
        ratio = r["ratio"]
        if ratio < 0.8:
            status = "⚠️  LOW"
        elif ratio < 1.0:
            status = "⚠️ "
        elif ratio > 2.0:
            status = "✅ HIGH"
        else:
            status = "✅"

        print(f"{status} {r['name']:<25} ratio={ratio:.2f}x  "
              f"(size={r['size_frac']:.0%} sha={r['sha_frac']:.0%})")

        if args.verbose:
            print(f"     {r['description']}")
            print(f"     serialized={r['serialized_len']:,}  "
                  f"atoms={r['atom_count']:,}  pairs={r['pair_count']:,}  "
                  f"atom_bytes={r['atom_bytes']:,}")
            print(f"     old_cost={r['old_cost']:,}  new_cost={r['new_cost']:,}")
            if args.time and "hash_time_ms" in r:
                print(f"     hash_time={r['hash_time_ms']:.2f}ms")
            print()

    print()
    print("Summary")
    print("-" * 70)

    low_ratio = [r for r in results if r["ratio"] < 1.0]
    high_ratio = [r for r in results if r["ratio"] >= 2.0]

    if low_ratio:
        print(f"⚠️  {len(low_ratio)} cases with ratio < 1.0 (charged LESS than before):")
        for r in low_ratio:
            print(f"   - {r['name']}: {r['ratio']:.2f}x")
        print()

    if high_ratio:
        print(f"✅ {len(high_ratio)} cases with ratio >= 2.0 (charged MORE than before)")

    # Check for dangerous cases
    dangerous = [r for r in results if r["ratio"] < 0.5]
    if dangerous:
        print()
        print("🚨 DANGER: Cases with ratio < 0.5 (charged HALF or less):")
        for r in dangerous:
            print(f"   - {r['name']}: {r['ratio']:.2f}x")
        print("   These could be DoS vectors!")
    else:
        print()
        print("✅ No dangerous cases found (all ratios >= 0.5)")


if __name__ == "__main__":
    main()
