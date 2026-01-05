#!/usr/bin/env python3
"""
Benchmark SHA256 to determine the I/S ratio (invocation overhead vs per-block cost).

This ratio is critical for the cost formula - it determines how much to charge
for many small hashes vs fewer large hashes.

The formula uses:
    sha_component = S × sha_blocks + I × sha_invocations

Where I/S should match the measured ratio of invocation overhead to per-block cost.
"""

from __future__ import annotations

import hashlib
import statistics
import time


def benchmark_sha256(sizes: list[int], iterations: int = 10000) -> list[dict]:
    """
    Benchmark SHA256 at various input sizes.

    Returns list of {size, blocks, ns_total, ns_per_block} dicts.
    """
    results = []

    for size in sizes:
        data = bytes(size)

        # Warm up
        for _ in range(100):
            hashlib.sha256(data).digest()

        # Timed run
        start = time.perf_counter_ns()
        for _ in range(iterations):
            hashlib.sha256(data).digest()
        elapsed = time.perf_counter_ns() - start

        ns_per_hash = elapsed / iterations

        # SHA256 block count: input + 1 (0x80) + 8 (length), rounded up to 64
        padded_len = size + 9
        blocks = (padded_len + 63) // 64

        results.append({
            "size": size,
            "blocks": blocks,
            "ns": ns_per_hash,
            "ns_per_block": ns_per_hash / blocks,
        })

    return results


def fit_linear_model(results: list[dict]) -> tuple[float, float]:
    """
    Fit a linear model: time = invocation + blocks × per_block

    Returns (per_block_cost, invocation_overhead)
    """
    x = [r["blocks"] for r in results]
    y = [r["ns"] for r in results]

    n = len(x)
    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)

    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

    per_block = numerator / denominator if denominator else 0
    invocation = mean_y - per_block * mean_x

    return per_block, invocation


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark SHA256 timing")
    parser.add_argument("--iterations", type=int, default=10000, help="Iterations per size")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all results")
    args = parser.parse_args()

    print("SHA256 Timing Benchmark")
    print("=" * 60)
    print()

    # Test sizes that cross SHA256 block boundaries
    # Block boundary is at 55 bytes (56+ needs 2 blocks)
    # Next boundary at 119 bytes (120+ needs 3 blocks)
    sizes = [
        1,      # 1 block, minimal data
        32,     # 1 block, common hash size
        55,     # 1 block, maximum
        56,     # 2 blocks, minimum
        64,     # 2 blocks
        65,     # 2 blocks, tree hash pair size (1 + 32 + 32)
        100,    # 2 blocks
        119,    # 2 blocks, maximum
        120,    # 3 blocks, minimum
        128,    # 3 blocks
        200,    # 4 blocks
        500,    # 8 blocks
        1000,   # 16 blocks
        4000,   # 63 blocks
        16000,  # 251 blocks
        65536,  # 1025 blocks
    ]

    print(f"Testing {len(sizes)} sizes, {args.iterations:,} iterations each...")
    print()

    results = benchmark_sha256(sizes, args.iterations)

    # Display results
    if args.verbose:
        print(f"{'Size':>8} {'Blocks':>7} {'Time (ns)':>12} {'ns/block':>10}")
        print("-" * 40)
        for r in results:
            print(f"{r['size']:>8} {r['blocks']:>7} {r['ns']:>12.1f} {r['ns_per_block']:>10.1f}")
        print()

    # Fit linear model
    per_block, invocation = fit_linear_model(results)

    print("Linear Model Fit")
    print("-" * 40)
    print(f"Per-block cost (S):      {per_block:>8.1f} ns")
    print(f"Invocation overhead (I): {invocation:>8.1f} ns")
    print()
    print(f"I/S ratio:               {invocation / per_block:>8.1f}")
    print()

    # Recommendation
    ratio = invocation / per_block
    recommended_I = round(ratio)

    print("Recommendation")
    print("-" * 40)
    print(f"Use I = {recommended_I} (rounded from {ratio:.1f})")
    print()

    # Validate fit
    print("Fit Validation")
    print("-" * 40)
    errors = []
    for r in results:
        predicted = invocation + per_block * r["blocks"]
        error = abs(r["ns"] - predicted) / r["ns"] * 100
        errors.append(error)
        if args.verbose:
            print(f"Size {r['size']:>5}: actual={r['ns']:.1f}, predicted={predicted:.1f}, error={error:.1f}%")

    print(f"Mean error: {statistics.mean(errors):.1f}%")
    print(f"Max error:  {max(errors):.1f}%")


if __name__ == "__main__":
    main()
