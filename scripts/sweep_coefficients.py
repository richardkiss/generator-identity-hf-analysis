#!/usr/bin/env python3
"""
Sweep cost formula coefficients to find optimal values.

Tests different B, A, P combinations against a set of generators
to find values that produce average cost ratio ≈ 1.0.

Usage:
    python scripts/sweep_coefficients.py ./data/generators/
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from clvm_rs import Program

from canon_analysis import cost_components, CostCoefficients
from canon_analysis.formula import compare_formulas


def load_generators(directory: Path) -> list[tuple[str, Program, int]]:
    """Load all generators from a directory."""
    generators = []
    for path in sorted(directory.glob("*.bin")):
        try:
            data = path.read_bytes()
            program = Program.from_bytes(data)
            generators.append((path.name, program, len(data)))
        except Exception as e:
            print(f"Warning: Failed to load {path.name}: {e}", file=sys.stderr)
    return generators


def evaluate_coefficients(
    generators: list[tuple[str, Program, int]],
    B: int,
    A: int,
    P: int,
    S: int = 1,
    I: int = 8,
) -> dict:
    """Evaluate coefficient combination against generators."""
    coeffs = CostCoefficients(B=B, A=A, P=P, S=S, I=I)

    ratios = []
    for name, program, serialized_len in generators:
        try:
            components = cost_components(program)
            result = compare_formulas(components, serialized_len, coeffs)
            if result["cost_ratio"]:
                ratios.append(result["cost_ratio"])
        except Exception:
            continue

    if not ratios:
        return {"B": B, "A": A, "P": P, "count": 0}

    return {
        "B": B,
        "A": A,
        "P": P,
        "S": S,
        "I": I,
        "count": len(ratios),
        "min": min(ratios),
        "avg": sum(ratios) / len(ratios),
        "max": max(ratios),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Sweep cost formula coefficients")
    parser.add_argument("directory", type=Path, help="Directory of generator files")
    parser.add_argument("--B-range", type=str, default="1", help="B values (e.g., '1' or '1,2')")
    parser.add_argument("--A-range", type=str, default="0,1,2,3", help="A values")
    parser.add_argument("--P-range", type=str, default="1,2,3,4,5", help="P values")
    parser.add_argument("--S", type=int, default=1, help="SHA block coefficient")
    parser.add_argument("--I", type=int, default=8, help="SHA invocation coefficient")
    parser.add_argument("--target", type=float, default=1.0, help="Target average ratio")

    args = parser.parse_args()

    B_values = [int(x) for x in args.B_range.split(",")]
    A_values = [int(x) for x in args.A_range.split(",")]
    P_values = [int(x) for x in args.P_range.split(",")]

    print(f"Loading generators from {args.directory}...")
    generators = load_generators(args.directory)
    print(f"Loaded {len(generators)} generators")
    print()

    if not generators:
        print("No generators found!")
        return

    print(f"Sweeping: B={B_values}, A={A_values}, P={P_values}")
    print(f"Target average ratio: {args.target}")
    print()

    results = []
    total = len(B_values) * len(A_values) * len(P_values)
    current = 0

    for B in B_values:
        for A in A_values:
            for P in P_values:
                current += 1
                print(f"Testing B={B}, A={A}, P={P} ({current}/{total})...", end="\r")
                result = evaluate_coefficients(generators, B, A, P, args.S, args.I)
                results.append(result)

    print()
    print()

    # Sort by distance from target
    results.sort(key=lambda r: abs(r.get("avg", 999) - args.target))

    print(f"{'B':>3} {'A':>3} {'P':>3} {'Min':>7} {'Avg':>7} {'Max':>7} {'Dist':>7}")
    print("-" * 45)

    for r in results[:20]:  # Top 20
        if "avg" not in r:
            continue
        dist = abs(r["avg"] - args.target)
        marker = " *" if dist < 0.02 else ""
        print(f"{r['B']:>3} {r['A']:>3} {r['P']:>3} "
              f"{r['min']:>7.3f} {r['avg']:>7.3f} {r['max']:>7.3f} "
              f"{dist:>7.3f}{marker}")

    print()
    print("* = within 0.02 of target")

    # Best result
    best = results[0]
    if "avg" in best:
        print()
        print(f"Best combination: B={best['B']}, A={best['A']}, P={best['P']}")
        print(f"  Average ratio: {best['avg']:.3f}")
        print(f"  Range: {best['min']:.3f} - {best['max']:.3f}")


if __name__ == "__main__":
    main()
