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
from typing import Dict, Optional, Tuple, Union

from clvm_rs import Program


@dataclass(frozen=True)
class InternedAtom:
    """An interned atom node."""

    data: bytes

    def __hash__(self) -> int:
        return hash(self.data)


@dataclass(frozen=True)
class InternedPair:
    """An interned pair node."""

    first: InternedNode
    rest: InternedNode

    def __hash__(self) -> int:
        return hash((id(self.first), id(self.rest)))


InternedNode = Union[InternedAtom, InternedPair]


class InternedTree:
    """
    A fully interned CLVM tree.

    All identical subtrees share the same node reference.
    This provides a canonical representation for cost calculation.
    """

    def __init__(self, root: InternedNode, stats: "InternStats"):
        self.root = root
        self.stats = stats

    @property
    def atom_count(self) -> int:
        """Number of unique atoms in the tree."""
        return self.stats.atom_count

    @property
    def pair_count(self) -> int:
        """Number of unique pairs in the tree."""
        return self.stats.pair_count

    @property
    def atom_bytes(self) -> int:
        """Total bytes of unique atom data."""
        return self.stats.atom_bytes


@dataclass
class InternStats:
    """Statistics collected during interning."""

    atom_count: int = 0
    pair_count: int = 0
    atom_bytes: int = 0


def intern_tree(program: Program) -> InternedTree:
    """
    Intern a CLVM program tree.

    This deduplicates all identical subtrees, producing a canonical
    representation where identical content shares the same node.

    Args:
        program: A clvm_rs Program to intern

    Returns:
        An InternedTree with deduplicated nodes and statistics
    """
    # Cache: serialized form -> interned node
    # We use serialization as the key for equality comparison
    atom_cache: Dict[bytes, InternedAtom] = {}
    pair_cache: Dict[Tuple[int, int], InternedPair] = {}
    stats = InternStats()

    def intern_node(node: Program) -> InternedNode:
        pair = node.pair
        if pair is None:
            # It's an atom
            data = bytes(node.atom)
            if data in atom_cache:
                return atom_cache[data]

            interned = InternedAtom(data)
            atom_cache[data] = interned
            stats.atom_count += 1
            stats.atom_bytes += len(data)
            return interned
        else:
            # It's a pair
            first, rest = pair
            interned_first = intern_node(first)
            interned_rest = intern_node(rest)

            # Use object ids as key since nodes are already interned
            key = (id(interned_first), id(interned_rest))
            if key in pair_cache:
                return pair_cache[key]

            interned = InternedPair(interned_first, interned_rest)
            pair_cache[key] = interned
            stats.pair_count += 1
            return interned

    root = intern_node(program)
    return InternedTree(root, stats)


def count_nodes(program: Program) -> Tuple[int, int, int]:
    """
    Count unique nodes in a program WITHOUT full interning.

    This is a lighter-weight alternative when you only need counts,
    not the interned structure itself.

    Args:
        program: A clvm_rs Program

    Returns:
        Tuple of (atom_count, pair_count, atom_bytes)
    """
    atom_set: set[bytes] = set()
    pair_set: set[Tuple[int, int]] = set()
    atom_bytes = 0

    # Map from serialized form to a unique id for pair deduplication
    node_ids: Dict[bytes, int] = {}
    next_id = 0

    def get_node_id(node: Program) -> int:
        nonlocal next_id, atom_bytes

        # Use tree hash as unique identifier
        node_hash = bytes(node.tree_hash())

        if node_hash in node_ids:
            return node_ids[node_hash]

        node_id = next_id
        next_id += 1
        node_ids[node_hash] = node_id

        pair = node.pair
        if pair is None:
            # Atom
            data = bytes(node.atom)
            if data not in atom_set:
                atom_set.add(data)
                atom_bytes += len(data)
        else:
            # Pair - recursively process children
            first, rest = pair
            first_id = get_node_id(first)
            rest_id = get_node_id(rest)
            pair_set.add((first_id, rest_id))

        return node_id

    get_node_id(program)
    return len(atom_set), len(pair_set), atom_bytes
