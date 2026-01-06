"""
Tree interning (deduplication) for CLVM trees.

Interning ensures that identical subtrees share the same node,
producing a canonical representation where:
- Identical atoms share the same reference
- Identical subtrees share the same reference

This is essential for making cost a pure function of tree content,
independent of serialization format.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from clvm_rs import Program


@dataclass
class InternStats:
    """Statistics collected during interning."""

    atom_count: int = 0
    pair_count: int = 0
    atom_bytes: int = 0


def count_unique_nodes(program: Program) -> Tuple[int, int, int]:
    """
    Count unique nodes in a program using tree hashes.

    Uses iterative traversal with explicit stack.

    Args:
        program: A clvm_rs Program

    Returns:
        Tuple of (atom_count, pair_count, atom_bytes)
    """
    seen: set[bytes] = set()
    atom_data_seen: set[bytes] = set()
    atom_count = 0
    pair_count = 0
    atom_bytes = 0

    stack = [program]

    while stack:
        node = stack.pop()
        node_hash = bytes(node.tree_hash())

        if node_hash in seen:
            continue
        seen.add(node_hash)

        pair = node.pair
        if pair is None:
            # Atom
            data = bytes(node.atom) if node.atom is not None else b''
            if data not in atom_data_seen:
                atom_data_seen.add(data)
                atom_count += 1
                atom_bytes += len(data)
        else:
            # Pair
            pair_count += 1
            first, rest = pair
            stack.append(rest)
            stack.append(first)

    return atom_count, pair_count, atom_bytes


def intern_tree(program: Program) -> InternStats:
    """
    Intern a CLVM program tree and return statistics.

    This deduplicates all identical subtrees by tree hash,
    counting unique atoms and pairs.

    Args:
        program: A clvm_rs Program to intern

    Returns:
        InternStats with counts of unique nodes
    """
    atom_count, pair_count, atom_bytes = count_unique_nodes(program)
    return InternStats(
        atom_count=atom_count,
        pair_count=pair_count,
        atom_bytes=atom_bytes,
    )
