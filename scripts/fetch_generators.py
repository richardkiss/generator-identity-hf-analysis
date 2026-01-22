#!/usr/bin/env python3
"""
Fetch real generators from a Chia node for analysis.

Requires a running Chia full node with RPC access.

Usage:
    python scripts/fetch_generators.py --count 500 --output data/generators/
    python scripts/fetch_generators.py --blocks 1000000,2000000,3000000 --output data/generators/
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
from pathlib import Path
from typing import Optional

# Check for chia-blockchain availability
try:
    from chia.rpc.full_node_rpc_client import FullNodeRpcClient
    from chia.util.config import load_config
    from chia.util.default_root import DEFAULT_ROOT_PATH
    from chia.util.ints import uint16, uint32
    CHIA_AVAILABLE = True
except ImportError:
    CHIA_AVAILABLE = False


async def get_generator(
    client: "FullNodeRpcClient",
    height: int,
) -> Optional[bytes]:
    """Fetch generator bytes for a block at given height."""
    block_record = await client.get_block_record_by_height(height)
    if not block_record:
        return None

    block = await client.get_block(block_record.header_hash)
    if not block or not block.transactions_generator:
        return None

    return bytes(block.transactions_generator)


async def fetch_random_generators(
    output_dir: Path,
    count: int,
    min_height: int = 225000,  # After transactions enabled
    max_height: Optional[int] = None,
) -> None:
    """Fetch random generators from the blockchain."""
    if not CHIA_AVAILABLE:
        print("Error: chia-blockchain not installed")
        print("Install with: pip install chia-blockchain")
        return

    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    self_hostname = config["self_hostname"]
    rpc_port = config["full_node"]["rpc_port"]

    client = await FullNodeRpcClient.create(
        self_hostname, uint16(rpc_port), DEFAULT_ROOT_PATH, config
    )

    try:
        # Get current peak
        state = await client.get_blockchain_state()
        peak_height = state["peak"].height if state["peak"] else 0

        if max_height is None:
            max_height = peak_height

        print(f"Blockchain height: {peak_height}")
        print(f"Sampling from heights {min_height} to {max_height}")
        print(f"Target: {count} generators")
        print()

        output_dir.mkdir(parents=True, exist_ok=True)
        fetched = 0
        attempts = 0
        max_attempts = count * 10  # Allow some failures

        while fetched < count and attempts < max_attempts:
            height = random.randint(min_height, max_height)
            attempts += 1

            generator = await get_generator(client, height)
            if generator:
                filename = f"generator_{height:010d}.bin"
                output_path = output_dir / filename
                output_path.write_bytes(generator)
                fetched += 1
                print(f"[{fetched}/{count}] Height {height}: {len(generator):,} bytes")

        print()
        print(f"Fetched {fetched} generators to {output_dir}")

    finally:
        client.close()
        await client.await_closed()


async def fetch_specific_blocks(
    output_dir: Path,
    heights: list[int],
) -> None:
    """Fetch generators for specific block heights."""
    if not CHIA_AVAILABLE:
        print("Error: chia-blockchain not installed")
        print("Install with: pip install chia-blockchain")
        return

    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    self_hostname = config["self_hostname"]
    rpc_port = config["full_node"]["rpc_port"]

    client = await FullNodeRpcClient.create(
        self_hostname, uint16(rpc_port), DEFAULT_ROOT_PATH, config
    )

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        fetched = 0

        for height in heights:
            generator = await get_generator(client, height)
            if generator:
                filename = f"generator_{height:010d}.bin"
                output_path = output_dir / filename
                output_path.write_bytes(generator)
                fetched += 1
                print(f"Height {height}: {len(generator):,} bytes")
            else:
                print(f"Height {height}: no generator (empty block?)")

        print()
        print(f"Fetched {fetched} generators to {output_dir}")

    finally:
        client.close()
        await client.await_closed()


async def fetch_largest_generators(
    output_dir: Path,
    count: int,
    min_height: int = 225000,
    max_height: Optional[int] = None,
    sample_size: int = 10000,
) -> None:
    """Fetch the largest generators by sampling many blocks."""
    if not CHIA_AVAILABLE:
        print("Error: chia-blockchain not installed")
        return

    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    self_hostname = config["self_hostname"]
    rpc_port = config["full_node"]["rpc_port"]

    client = await FullNodeRpcClient.create(
        self_hostname, uint16(rpc_port), DEFAULT_ROOT_PATH, config
    )

    try:
        state = await client.get_blockchain_state()
        peak_height = state["peak"].height if state["peak"] else 0

        if max_height is None:
            max_height = peak_height

        print(f"Sampling {sample_size} blocks to find {count} largest generators...")
        print()

        # Sample blocks and record sizes
        candidates = []
        heights_to_check = random.sample(
            range(min_height, max_height + 1),
            min(sample_size, max_height - min_height + 1)
        )

        for i, height in enumerate(heights_to_check):
            if i % 100 == 0:
                print(f"Checking block {i}/{len(heights_to_check)}...", end="\r")

            generator = await get_generator(client, height)
            if generator:
                candidates.append((height, len(generator), generator))

        print()
        print(f"Found {len(candidates)} blocks with generators")

        # Sort by size and take top N
        candidates.sort(key=lambda x: -x[1])
        top_n = candidates[:count]

        output_dir.mkdir(parents=True, exist_ok=True)

        for height, size, generator in top_n:
            filename = f"generator_{height:010d}.bin"
            output_path = output_dir / filename
            output_path.write_bytes(generator)
            print(f"Height {height}: {size:,} bytes")

        print()
        print(f"Saved {len(top_n)} largest generators to {output_dir}")

    finally:
        client.close()
        await client.await_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch generators from Chia node")
    parser.add_argument("--output", "-o", type=Path, default=Path("data/generators"),
                        help="Output directory")
    parser.add_argument("--count", "-n", type=int, default=100,
                        help="Number of generators to fetch")
    parser.add_argument("--blocks", type=str,
                        help="Comma-separated list of specific block heights")
    parser.add_argument("--largest", action="store_true",
                        help="Fetch largest generators by size")
    parser.add_argument("--sample-size", type=int, default=10000,
                        help="Sample size for --largest mode")
    parser.add_argument("--min-height", type=int, default=225000,
                        help="Minimum block height")
    parser.add_argument("--max-height", type=int,
                        help="Maximum block height")

    args = parser.parse_args()

    if not CHIA_AVAILABLE:
        print("Error: chia-blockchain package not installed")
        print()
        print("To use this script, install chia-blockchain:")
        print("  pip install chia-blockchain")
        print()
        print("And ensure you have a running Chia full node.")
        return

    if args.blocks:
        heights = [int(h.strip()) for h in args.blocks.split(",")]
        asyncio.run(fetch_specific_blocks(args.output, heights))
    elif args.largest:
        asyncio.run(fetch_largest_generators(
            args.output,
            args.count,
            args.min_height,
            args.max_height,
            args.sample_size,
        ))
    else:
        asyncio.run(fetch_random_generators(
            args.output,
            args.count,
            args.min_height,
            args.max_height,
        ))


if __name__ == "__main__":
    main()
