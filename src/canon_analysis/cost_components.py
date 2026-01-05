"""
Cost component extraction for CLVM generators.

Extracts the raw components needed for the cost formula:
- atom_bytes: total bytes of unique atom data
- atom_count: number of unique atoms
- pair_count: number of unique pairs
- sha_blocks: total SHA256 64-byte blocks for tree hashing
- sha_invocations: number of SHA256 calls (one per unique node)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from clvm_rs import Program

from canon_analysis.intern import intern_tree
from canon_analysis.tree_hash import count_sha_work


@dataclass
class CostComponents:
    """
    Raw cost components extracted from an interned generator.

    These are the inputs to the cost formula.
    """

    # Size components
    atom_bytes: int
    atom_count: int
    pair_count: int

    # SHA components
    sha_blocks: int
    sha_invocations: int

    # Metadata
    tree_hash: Optional[bytes] = None

    @property
    def total_nodes(self) -> int:
        """Total unique nodes (atoms + pairs)."""
        return self.atom_count + self.pair_count

    def __str__(self) -> str:
        return (
            f"CostComponents(\n"
            f"  atom_bytes={self.atom_bytes:,},\n"
            f"  atom_count={self.atom_count:,},\n"
            f"  pair_count={self.pair_count:,},\n"
            f"  sha_blocks={self.sha_blocks:,},\n"
            f"  sha_invocations={self.sha_invocations:,}\n"
            f")"
        )


def cost_components(program: Program) -> CostComponents:
    """
    Extract cost components from a CLVM program.

    The program is interned to ensure we count unique nodes only,
    producing deterministic results regardless of serialization format.

    Args:
        program: A clvm_rs Program (typically a generator)

    Returns:
        CostComponents with all raw values for the cost formula
    """
    # Intern the tree to deduplicate
    interned = intern_tree(program)

    # Count SHA work
    sha_blocks, sha_invocations = count_sha_work(program)

    # Get tree hash
    tree_hash_bytes = bytes(program.tree_hash())

    return CostComponents(
        atom_bytes=interned.atom_bytes,
        atom_count=interned.atom_count,
        pair_count=interned.pair_count,
        sha_blocks=sha_blocks,
        sha_invocations=sha_invocations,
        tree_hash=tree_hash_bytes,
    )


def cost_components_from_bytes(data: bytes, use_backrefs: bool = True) -> CostComponents:
    """
    Extract cost components from serialized CLVM data.

    Args:
        data: Serialized CLVM program bytes
        use_backrefs: If True, parse with backref support (default)

    Returns:
        CostComponents for the deserialized program
    """
    if use_backrefs:
        program = Program.from_bytes(data)
    else:
        # clvm_rs doesn't expose non-backref parsing directly,
        # but from_bytes handles both formats
        program = Program.from_bytes(data)

    return cost_components(program)
