#!/usr/bin/env python3
"""
Analyze generators and compare old vs new cost formulas.

Usage:
    python scripts/analyze_generators.py path/to/generator.bin
    python scripts/analyze_generators.py ./data/generators/ --batch --csv results.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Optional

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from canon_analysis import cost_components, calculate_cost, CostCoefficients
from canon_analysis.formula import compare_formulas
from clvm_rs import Program


def analyze_file(path: Path, coeffs: CostCoefficients) -> Optional[dict]:
    """Analyze a single generator file."""
    try:
        data = path.read_bytes()
        program = Program.from_bytes(data)
        components = cost_components(program)
        return compare_formulas(components, len(data), coeffs)
    except Exception as e:
        print(f"Error processing {path}: {e}", file=sys.stderr)
        return None


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Analyze generator costs")
    parser.add_argument("path", type=Path, help="Generator file or directory")
    parser.add_argument("--batch", action="store_true", help="Process directory")
    parser.add_argument("--csv", type=Path, help="Output CSV file")
    parser.add_argument("--B", type=int, default=1, help="Atom byte coefficient")
    parser.add_argument("--A", type=int, default=2, help="Atom count coefficient")
    parser.add_argument("--P", type=int, default=2, help="Pair count coefficient")
    parser.add_argument("--S", type=int, default=1, help="SHA block coefficient")
    parser.add_argument("--I", type=int, default=8, help="SHA invocation coefficient")

    args = parser.parse_args()

    coeffs = CostCoefficients(B=args.B, A=args.A, P=args.P, S=args.S, I=args.I)

    if args.batch or args.path.is_dir():
        # Batch mode
        files = sorted(args.path.glob("*.bin"))
        if not files:
            print(f"No .bin files found in {args.path}")
            return

        results = []
        ratios = []

        for path in files:
            result = analyze_file(path, coeffs)
            if result:
                result["filename"] = path.name
                results.append(result)
                if result["cost_ratio"]:
                    ratios.append(result["cost_ratio"])

        if not results:
            print("No generators successfully processed")
            return

        # Print summary
        print(f"\nProcessed {len(results)} generators")
        print(f"  Min ratio:  {min(ratios):.3f}")
        print(f"  Avg ratio:  {sum(ratios) / len(ratios):.3f}")
        print(f"  Max ratio:  {max(ratios):.3f}")

        # Outliers
        low = [r for r in results if r["cost_ratio"] and r["cost_ratio"] < 0.7]
        high = [r for r in results if r["cost_ratio"] and r["cost_ratio"] > 1.1]

        if low:
            print(f"\nLow ratio outliers (<0.7): {len(low)}")
            for r in sorted(low, key=lambda x: x["cost_ratio"])[:5]:
                print(f"  {r['filename']}: {r['cost_ratio']:.3f}")

        if high:
            print(f"\nHigh ratio outliers (>1.1): {len(high)}")
            for r in sorted(high, key=lambda x: -x["cost_ratio"])[:5]:
                print(f"  {r['filename']}: {r['cost_ratio']:.3f}")

        # Write CSV
        if args.csv:
            with open(args.csv, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
            print(f"\nWrote {args.csv}")

    else:
        # Single file mode
        result = analyze_file(args.path, coeffs)
        if not result:
            return

        print(f"\nGenerator: {args.path.name}")
        print(f"Serialized: {result['serialized_len']:,} bytes")
        print()
        print("Cost Components:")
        print(f"  atom_bytes:       {result['atom_bytes']:,}")
        print(f"  atom_count:       {result['atom_count']:,}")
        print(f"  pair_count:       {result['pair_count']:,}")
        print(f"  sha_blocks:       {result['sha_blocks']:,}")
        print(f"  sha_invocations:  {result['sha_invocations']:,}")
        print()
        print("Cost Comparison:")
        print(f"  Estimated length: {result['estimated_len']:,}")
        print(f"  Old cost:         {result['old_cost']:,}")
        print(f"  New cost:         {result['new_cost']:,}")
        print(f"  Ratio (new/old):  {result['cost_ratio']:.3f}")
        print(f"  Size fraction:    {result['size_fraction']:.1%}")
        print(f"  SHA fraction:     {result['sha_fraction']:.1%}")


if __name__ == "__main__":
    main()
