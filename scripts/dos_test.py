#!/usr/bin/env python3
"""
DoS analysis for the cost formula.

Creates adversarial generator structures and verifies the cost formula
charges appropriately for the work required.

Key insight: The new formula charges based on UNIQUE nodes. Structures with
lots of sharing (like balanced trees with identical leaves) correctly get
lower costs because they require less work to hash.

True DoS vectors would be structures where:
- Many unique nodes (high work)
- But compact serialization (low old cost)

This is hard to achieve because more unique nodes = larger serialization.
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
class TestCase:
    """A test case for cost formula analysis."""

    name: str
    description: str
    builder: Callable[[int], Program]
    target_size: int


def build_nil_list(count: int) -> Program:
    """Build a long list of nil atoms."""
    items = [b'' for _ in range(count)]
    return Program.to(items)


def build_deep_nesting(depth: int) -> Program:
    """Build deeply nested pairs with UNIQUE atoms at each level."""
    result = Program.to(b'')
    for i in range(depth):
        # Use unique atom at each level to prevent sharing
        result = Program.to((result, i.to_bytes(4, 'big')))
    return result


def build_hash_atoms(count: int) -> Program:
    """Build a list of unique 32-byte atoms."""
    items = [i.to_bytes(32, "big") for i in range(count)]
    return Program.to(items)


def build_tiny_unique_atoms(count: int) -> Program:
    """Build a list of unique small atoms (1-4 bytes)."""
    items = [i.to_bytes((i.bit_length() + 7) // 8 or 1, "big") for i in range(count)]
    return Program.to(items)


def build_huge_atom(size: int) -> Program:
    """Build a single large atom."""
    return Program.to(bytes(size))


def build_unique_balanced_tree(depth: int) -> Program:
    """Build a balanced tree where EVERY leaf is unique (no sharing)."""
    # Create 2^depth unique leaves
    leaf_count = 2 ** depth
    nodes = [Program.to(i.to_bytes(4, 'big')) for i in range(leaf_count)]

    while len(nodes) > 1:
        new_nodes = []
        for i in range(0, len(nodes), 2):
            if i + 1 < len(nodes):
                new_nodes.append(Program.to((nodes[i], nodes[i + 1])))
            else:
                new_nodes.append(nodes[i])
        nodes = new_nodes

    return nodes[0]


def build_shared_balanced_tree(depth: int) -> Program:
    """Build a balanced tree with identical leaves (maximum sharing)."""
    nodes = [Program.to(b"leaf") for _ in range(2 ** depth)]
    while len(nodes) > 1:
        new_nodes = []
        for i in range(0, len(nodes), 2):
            if i + 1 < len(nodes):
                new_nodes.append(Program.to((nodes[i], nodes[i + 1])))
            else:
                new_nodes.append(nodes[i])
        nodes = new_nodes
    return nodes[0]


def build_many_small_pairs(count: int) -> Program:
    """Build many independent pairs with unique values."""
    items = [(i * 2, i * 2 + 1) for i in range(count)]
    return Program.to(items)


# Test cases
TEST_CASES = [
    # High node count cases (potential DoS vectors)
    TestCase(
        name="nil_list",
        description="Long list of nil atoms - high pair count, minimal data",
        builder=lambda n: build_nil_list(n),
        target_size=10_000,
    ),
    TestCase(
        name="deep_unique_nesting",
        description="Deeply nested pairs with unique atoms",
        builder=lambda n: build_deep_nesting(n),
        target_size=10_000,
    ),
    TestCase(
        name="tiny_unique_atoms",
        description="Many unique small atoms",
        builder=lambda n: build_tiny_unique_atoms(n),
        target_size=10_000,
    ),
    TestCase(
        name="many_small_pairs",
        description="Many independent pairs with unique values",
        builder=lambda n: build_many_small_pairs(n),
        target_size=5_000,
    ),

    # Data-heavy cases (low work per byte)
    TestCase(
        name="hash_sized_atoms",
        description="Many 32-byte atoms (typical puzzle data)",
        builder=lambda n: build_hash_atoms(n),
        target_size=3_000,
    ),
    TestCase(
        name="single_huge_atom",
        description="One large atom - minimal hashing work",
        builder=lambda n: build_huge_atom(n),
        target_size=100_000,
    ),

    # Sharing comparison
    TestCase(
        name="unique_balanced_tree",
        description="Balanced tree with unique leaves (no sharing)",
        builder=lambda n: build_unique_balanced_tree(n),
        target_size=10,  # depth 10 = 1024 unique leaves
    ),
    TestCase(
        name="shared_balanced_tree",
        description="Balanced tree with identical leaves (max sharing)",
        builder=lambda n: build_shared_balanced_tree(n),
        target_size=12,  # depth 12, but only ~13 unique nodes
    ),
]


def time_tree_hash(program: Program, iterations: int = 100) -> float:
    """Time tree hash computation in milliseconds."""
    for _ in range(10):  # warm up
        program.tree_hash()

    start = time.perf_counter()
    for _ in range(iterations):
        program.tree_hash()
    elapsed = time.perf_counter() - start

    return elapsed / iterations * 1000


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="DoS analysis for cost formula")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show details")
    parser.add_argument("--time", "-t", action="store_true", help="Include timing")
    args = parser.parse_args()

    coeffs = CostCoefficients()

    print("Cost Formula Analysis: Various Generator Structures")
    print("=" * 70)
    print()
    print("Ratio = new_cost / old_cost")
    print("  > 1.0: New formula charges MORE (protects against this structure)")
    print("  < 1.0: New formula charges LESS (may be intentional for efficient structures)")
    print()

    results = []

    for case in TEST_CASES:
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
                "total_nodes": components.total_nodes,
                "old_cost": breakdown.old_cost,
                "new_cost": breakdown.total_cost,
                "ratio": breakdown.cost_ratio,
                "size_frac": breakdown.size_fraction,
                "sha_frac": breakdown.sha_fraction,
            }

            if args.time:
                result["hash_time_ms"] = time_tree_hash(program)
                # Work per cost ratio: ms per billion cost units
                result["work_per_cost"] = result["hash_time_ms"] / (breakdown.total_cost / 1e9)

            results.append(result)
            print(f"done ({serialized_len:,} bytes, {components.total_nodes:,} unique nodes)")

        except Exception as e:
            print(f"ERROR: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            continue

    print()
    print("Results (sorted by ratio)")
    print("-" * 70)

    results.sort(key=lambda r: r["ratio"] if r["ratio"] else 999)

    for r in results:
        ratio = r["ratio"]
        nodes = r["total_nodes"]

        # Categorize
        if ratio < 0.5:
            marker = "⚠️  MUCH LESS"
        elif ratio < 1.0:
            marker = "📉 less"
        elif ratio < 1.5:
            marker = "≈  similar"
        elif ratio < 2.0:
            marker = "📈 more"
        else:
            marker = "✅ MUCH MORE"

        print(f"{marker:14} {r['name']:<25} ratio={ratio:.2f}x  nodes={nodes:,}")

        if args.verbose:
            print(f"    {r['description']}")
            print(f"    serialized={r['serialized_len']:,}  "
                  f"atoms={r['atom_count']:,}  pairs={r['pair_count']:,}  "
                  f"atom_bytes={r['atom_bytes']:,}")
            print(f"    old_cost={r['old_cost']:,}  new_cost={r['new_cost']:,}")
            print(f"    size_component={r['size_frac']:.0%}  sha_component={r['sha_frac']:.0%}")
            if args.time and "hash_time_ms" in r:
                print(f"    hash_time={r['hash_time_ms']:.3f}ms  "
                      f"work_per_cost={r['work_per_cost']:.3f} ms/Gcost")
            print()

    print()
    print("Analysis")
    print("-" * 70)

    # Find structures where new cost is lower
    low_ratio = [r for r in results if r["ratio"] and r["ratio"] < 0.8]
    high_ratio = [r for r in results if r["ratio"] and r["ratio"] > 1.5]

    if low_ratio:
        print("Structures costing LESS under new formula:")
        for r in low_ratio:
            # Check if it's due to sharing or data-heavy
            if r["atom_bytes"] > r["serialized_len"] * 0.5:
                reason = "(data-heavy, low hash work)"
            elif r["total_nodes"] < 100:
                reason = "(high sharing, few unique nodes)"
            else:
                reason = ""
            print(f"  - {r['name']}: {r['ratio']:.2f}x {reason}")
        print()

    if high_ratio:
        print("Structures costing MORE under new formula (DoS protection):")
        for r in high_ratio:
            print(f"  - {r['name']}: {r['ratio']:.2f}x")
        print()

    # Summary
    print("Key insight: The new formula rewards efficient structures (sharing, data-heavy)")
    print("and penalizes structures with many small unique nodes (high hash work).")


if __name__ == "__main__":
    main()
