#!/usr/bin/env python3
"""
Comprehensive test for serde_2026 upper bound formula.

Tests both real-world generators and extreme/pathological cases to ensure
the formula `size_component = atom_bytes + 2×atom_count + 3×pair_count`
provides an upper bound on serde_2026 serialized size.
"""

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from clvm_rs import Program


class TestResult(NamedTuple):
    """Results from testing one generator."""
    name: str
    serde2026_size: int
    size_component: int
    passes: bool
    margin: int


def build_extreme_cases():
    """Build extreme test cases that stress different aspects of the formula."""
    cases = {}
    
    # One large atom (minimal atom_count, pair_count)
    cases["one_large_atom"] = Program.to(bytes(1_000_000))
    
    # Many tiny atoms (maximizes atom_count, minimizes atom_bytes)
    tiny_atoms = [i.to_bytes(1, "big") for i in range(50_000)]
    cases["many_tiny_atoms"] = Program.to(tiny_atoms)
    
    # Deep nesting with unique atoms (maximizes pair_count relative to atom_count)
    result = Program.to(b'')
    for i in range(10_000):
        result = Program.to((result, i.to_bytes(4, 'big')))
    cases["deep_nesting"] = result
    
    # Balanced tree with all unique leaves (balanced atom_count and pair_count)
    depth = 10  # 2^10 = 1024 leaves
    nodes = [Program.to(i.to_bytes(4, 'big')) for i in range(2 ** depth)]
    while len(nodes) > 1:
        new_nodes = []
        for i in range(0, len(nodes), 2):
            if i + 1 < len(nodes):
                new_nodes.append(Program.to((nodes[i], nodes[i + 1])))
            else:
                new_nodes.append(nodes[i])
        nodes = new_nodes
    cases["unique_balanced_tree"] = nodes[0]
    
    # List of 32-byte hashes (typical generator atom size)
    hash_atoms = [i.to_bytes(32, "big") for i in range(20_000)]
    cases["hash_atom_list"] = Program.to(hash_atoms)
    
    return cases


def test_generator_file(clvm_serde_path: Path, gen_file: Path) -> TestResult:
    """Test one generator file."""
    result = subprocess.run(
        [str(clvm_serde_path), "--sizes", "--stats", str(gen_file)],
        capture_output=True,
        text=True,
        check=True,
    )
    
    lines = result.stdout.strip().split('\n')
    for line in lines:
        if gen_file.name in line:
            parts = line.split()
            serde2026 = int(parts[2].replace(',', ''))
            atom_bytes = int(parts[3].replace(',', ''))
            atom_count = int(parts[4].replace(',', ''))
            pair_count = int(parts[5].replace(',', ''))
            
            # Formula with P=3
            size_component = atom_bytes + 2 * atom_count + 3 * pair_count
            passes = size_component >= serde2026
            margin = size_component - serde2026
            
            return TestResult(
                name=gen_file.stem,
                serde2026_size=serde2026,
                size_component=size_component,
                passes=passes,
                margin=margin,
            )
    
    raise ValueError(f"Could not parse output for {gen_file.name}")


def test_extreme_case(clvm_serde_path: Path, name: str, program: Program) -> TestResult:
    """Test one extreme case by writing to a temp file."""
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=".generator", delete=False) as f:
        temp_path = Path(f.name)
        f.write(bytes(program))
    
    try:
        result = subprocess.run(
            [str(clvm_serde_path), "--sizes", "--stats", str(temp_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if temp_path.name in line:
                parts = line.split()
                serde2026 = int(parts[2].replace(',', ''))
                atom_bytes = int(parts[3].replace(',', ''))
                atom_count = int(parts[4].replace(',', ''))
                pair_count = int(parts[5].replace(',', ''))
                
                size_component = atom_bytes + 2 * atom_count + 3 * pair_count
                passes = size_component >= serde2026
                margin = size_component - serde2026
                
                return TestResult(
                    name=name,
                    serde2026_size=serde2026,
                    size_component=size_component,
                    passes=passes,
                    margin=margin,
                )
    finally:
        temp_path.unlink()
    
    raise ValueError(f"Could not parse output for {name}")


def main():
    # Find serde-summary binary
    serde_summary = Path.home() / "projects/clvm_rs/serde_2026/target/release/serde-summary"
    if not serde_summary.exists():
        print(f"Error: serde-summary not found at {serde_summary}")
        print("Build it with: cd ~/projects/clvm_rs/serde_2026 && cargo build --release -p clvm-rs-test-tools --bin serde-summary")
        sys.exit(1)
    
    # Test real generators
    bench_dir = Path.home() / "projects/clvm_rs/bench_large_generator/benches"
    real_generators = sorted(bench_dir.glob("*.generator"))
    
    print("Testing Real Generators (A=2, P=3):")
    print("=" * 80)
    
    real_results = []
    for gen_file in real_generators:
        result = test_generator_file(serde_summary, gen_file)
        real_results.append(result)
        status = "✓ PASS" if result.passes else "✗ FAIL"
        print(f"{result.name:20s} {status:8s} sc={result.size_component:9,d} s2026={result.serde2026_size:9,d} margin={result.margin:+7,d}")
    
    # Test extreme cases
    print("\nBuilding extreme test cases...")
    extreme_cases = build_extreme_cases()
    
    print("\nTesting Extreme Cases (A=2, P=3):")
    print("=" * 80)
    
    extreme_results = []
    for name, program in extreme_cases.items():
        result = test_extreme_case(serde_summary, name, program)
        extreme_results.append(result)
        status = "✓ PASS" if result.passes else "✗ FAIL"
        print(f"{result.name:20s} {status:8s} sc={result.size_component:9,d} s2026={result.serde2026_size:9,d} margin={result.margin:+7,d}")
    
    # Summary
    all_results = real_results + extreme_results
    num_pass = sum(1 for r in all_results if r.passes)
    num_fail = len(all_results) - num_pass
    min_margin = min(r.margin for r in all_results if r.passes) if any(r.passes for r in all_results) else 0
    max_margin = max(r.margin for r in all_results if r.passes) if any(r.passes for r in all_results) else 0
    
    print("\n" + "=" * 80)
    print(f"Results: {num_pass} pass, {num_fail} fail (out of {len(all_results)} total)")
    if num_pass > 0:
        print(f"Margins: min={min_margin:+,d}  max={max_margin:+,d}")
    
    if num_fail > 0:
        print("\nFailing cases:")
        for r in all_results:
            if not r.passes:
                print(f"  {r.name}: over by {-r.margin:,d} bytes")
        sys.exit(1)
    else:
        print("\n✓ All tests pass! Formula A=2, P=3 is correct.")
        sys.exit(0)


if __name__ == "__main__":
    main()
