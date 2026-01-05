"""
Command-line interface for canonical generator analysis.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from canon_analysis.cost_components import cost_components_from_bytes
from canon_analysis.formula import DEFAULT_COEFFICIENTS, calculate_cost, compare_formulas

console = Console()


@click.group()
def main() -> None:
    """Canonical Generator Analysis Tools."""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--batch", is_flag=True, help="Process directory of generators")
@click.option("--csv", type=click.Path(), help="Output CSV file for batch mode")
def analyze(path: str, batch: bool, csv: Optional[str]) -> None:
    """Analyze generator(s) and show cost breakdown."""
    path_obj = Path(path)

    if batch or path_obj.is_dir():
        analyze_batch(path_obj, csv)
    else:
        analyze_single(path_obj)


def analyze_single(path: Path) -> None:
    """Analyze a single generator file."""
    data = path.read_bytes()
    serialized_len = len(data)

    console.print(f"\n[bold]Analyzing:[/bold] {path.name}")
    console.print(f"Serialized size: {serialized_len:,} bytes\n")

    try:
        components = cost_components_from_bytes(data)
    except Exception as e:
        console.print(f"[red]Error parsing generator: {e}[/red]")
        return

    breakdown = calculate_cost(components, serialized_len=serialized_len)

    # Components table
    table = Table(title="Cost Components")
    table.add_column("Component", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("atom_bytes", f"{components.atom_bytes:,}")
    table.add_row("atom_count", f"{components.atom_count:,}")
    table.add_row("pair_count", f"{components.pair_count:,}")
    table.add_row("sha_blocks", f"{components.sha_blocks:,}")
    table.add_row("sha_invocations", f"{components.sha_invocations:,}")

    console.print(table)

    # Cost breakdown table
    cost_table = Table(title="Cost Breakdown")
    cost_table.add_column("Metric", style="cyan")
    cost_table.add_column("Value", justify="right")

    cost_table.add_row("Size component", f"{breakdown.size_component:,}")
    cost_table.add_row("SHA component", f"{breakdown.sha_component:,}")
    cost_table.add_row("Size cost", f"{breakdown.size_cost:,}")
    cost_table.add_row("SHA cost", f"{breakdown.sha_cost:,}")
    cost_table.add_row("", "")
    cost_table.add_row("[bold]New total cost[/bold]", f"[bold]{breakdown.total_cost:,}[/bold]")
    cost_table.add_row("[bold]Old cost[/bold]", f"[bold]{breakdown.old_cost:,}[/bold]")
    cost_table.add_row("", "")
    cost_table.add_row("Cost ratio (new/old)", f"{breakdown.cost_ratio:.3f}")
    cost_table.add_row("Size fraction", f"{breakdown.size_fraction:.1%}")
    cost_table.add_row("SHA fraction", f"{breakdown.sha_fraction:.1%}")

    console.print(cost_table)

    if components.tree_hash:
        console.print(f"\nTree hash: {components.tree_hash.hex()}")


def analyze_batch(directory: Path, csv_path: Optional[str]) -> None:
    """Analyze all generators in a directory."""
    files = sorted(directory.glob("*.bin"))
    if not files:
        console.print(f"[yellow]No .bin files found in {directory}[/yellow]")
        return

    console.print(f"[bold]Analyzing {len(files)} generators...[/bold]\n")

    results = []
    ratios = []

    for path in files:
        data = path.read_bytes()
        try:
            components = cost_components_from_bytes(data)
            comparison = compare_formulas(components, len(data))
            comparison["filename"] = path.name
            results.append(comparison)
            if comparison["cost_ratio"]:
                ratios.append(comparison["cost_ratio"])
        except Exception as e:
            console.print(f"[red]Error processing {path.name}: {e}[/red]")

    if not results:
        console.print("[red]No generators successfully processed[/red]")
        return

    # Summary statistics
    console.print(f"[bold]Summary ({len(results)} generators):[/bold]")
    console.print(f"  Min ratio:  {min(ratios):.3f}")
    console.print(f"  Avg ratio:  {sum(ratios) / len(ratios):.3f}")
    console.print(f"  Max ratio:  {max(ratios):.3f}")

    # Write CSV if requested
    if csv_path:
        import csv

        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        console.print(f"\n[green]Wrote results to {csv_path}[/green]")


@main.command()
@click.option("--iterations", default=1000, help="Iterations per size")
def benchmark_sha(iterations: int) -> None:
    """Benchmark SHA256 to determine I/S ratio."""
    # Import here to avoid startup delay
    import hashlib
    import time

    console.print("[bold]SHA256 Timing Benchmark[/bold]\n")
    console.print(f"Iterations per size: {iterations:,}\n")

    # Test sizes around block boundaries
    sizes = [1, 32, 55, 56, 64, 65, 100, 119, 120, 128, 200, 500, 1000, 4000, 16000, 65536]

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
        blocks = (size + 9 + 63) // 64  # SHA256 block count with padding

        results.append({"size": size, "blocks": blocks, "ns": ns_per_hash})

    # Display results
    table = Table(title="SHA256 Timing Results")
    table.add_column("Size (bytes)", justify="right")
    table.add_column("Blocks", justify="right")
    table.add_column("Time (ns)", justify="right")
    table.add_column("ns/block", justify="right")

    for r in results:
        table.add_row(
            str(r["size"]),
            str(r["blocks"]),
            f"{r['ns']:.1f}",
            f"{r['ns'] / r['blocks']:.1f}",
        )

    console.print(table)

    # Fit linear model: time = invocation_overhead + blocks * per_block_cost
    # Using simple linear regression
    import statistics

    x = [r["blocks"] for r in results]
    y = [r["ns"] for r in results]

    n = len(x)
    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)

    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

    per_block = numerator / denominator if denominator else 0
    invocation = mean_y - per_block * mean_x

    console.print(f"\n[bold]Linear fit:[/bold]")
    console.print(f"  Per-block cost:      {per_block:.1f} ns")
    console.print(f"  Invocation overhead: {invocation:.1f} ns")
    console.print(f"  I/S ratio:           {invocation / per_block:.1f}")


if __name__ == "__main__":
    main()
