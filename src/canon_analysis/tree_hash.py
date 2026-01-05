"""
SHA256 tree hash computation for CLVM trees.

The tree hash provides content-addressable identity:
- Same logical tree content = same hash
- Independent of serialization format

Tree hash algorithm:
- Atom: SHA256(0x01 || atom_data)
- Pair: SHA256(0x02 || tree_hash(first) || tree_hash(rest))
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Dict, Optional

from clvm_rs import Program

if TYPE_CHECKING:
    from canon_analysis.intern import InternedNode, InternedTree


# Prefix bytes for tree hash
ATOM_PREFIX = b"\x01"
PAIR_PREFIX = b"\x02"


def tree_hash(program: Program) -> bytes:
    """
    Compute the SHA256 tree hash of a CLVM program.

    This uses clvm_rs's built-in tree_hash method.

    Args:
        program: A clvm_rs Program

    Returns:
        32-byte tree hash
    """
    return bytes(program.tree_hash())


def tree_hash_with_stats(program: Program) -> tuple[bytes, int, int]:
    """
    Compute tree hash while counting SHA256 operations.

    Args:
        program: A clvm_rs Program

    Returns:
        Tuple of (tree_hash, sha_blocks, sha_invocations)
    """
    cache: Dict[bytes, bytes] = {}
    sha_blocks = 0
    sha_invocations = 0

    def hash_node(node: Program) -> bytes:
        nonlocal sha_blocks, sha_invocations

        # Use the node's tree hash as cache key
        node_key = bytes(node.tree_hash())
        if node_key in cache:
            return cache[node_key]

        pair = node.pair
        if pair is None:
            # Atom: SHA256(0x01 || data)
            data = bytes(node.atom)
            preimage = ATOM_PREFIX + data
        else:
            # Pair: SHA256(0x02 || hash(first) || hash(rest))
            first, rest = pair
            first_hash = hash_node(first)
            rest_hash = hash_node(rest)
            preimage = PAIR_PREFIX + first_hash + rest_hash

        # Count SHA256 work
        sha_invocations += 1
        # SHA256 processes 64-byte blocks; need to account for padding
        # Padding adds 1 byte (0x80) + length (8 bytes) + padding to 64-byte boundary
        padded_len = len(preimage) + 9  # +1 for 0x80, +8 for length
        sha_blocks += (padded_len + 63) // 64

        result = hashlib.sha256(preimage).digest()
        cache[node_key] = result
        return result

    root_hash = hash_node(program)
    return root_hash, sha_blocks, sha_invocations


def tree_hash_interned(tree: "InternedTree") -> bytes:
    """
    Compute tree hash of an already-interned tree.

    This is more efficient because identical subtrees are only hashed once.

    Args:
        tree: An InternedTree

    Returns:
        32-byte tree hash
    """
    from canon_analysis.intern import InternedAtom, InternedPair

    cache: Dict[int, bytes] = {}

    def hash_node(node: "InternedNode") -> bytes:
        node_id = id(node)
        if node_id in cache:
            return cache[node_id]

        if isinstance(node, InternedAtom):
            preimage = ATOM_PREFIX + node.data
        else:
            assert isinstance(node, InternedPair)
            first_hash = hash_node(node.first)
            rest_hash = hash_node(node.rest)
            preimage = PAIR_PREFIX + first_hash + rest_hash

        result = hashlib.sha256(preimage).digest()
        cache[node_id] = result
        return result

    return hash_node(tree.root)


def count_sha_work(program: Program) -> tuple[int, int]:
    """
    Count SHA256 work required for tree hashing WITHOUT computing hashes.

    This counts unique nodes and their SHA block requirements.

    Args:
        program: A clvm_rs Program

    Returns:
        Tuple of (sha_blocks, sha_invocations)
    """
    seen: set[bytes] = set()
    sha_blocks = 0
    sha_invocations = 0

    def count_node(node: Program) -> None:
        nonlocal sha_blocks, sha_invocations

        node_hash = bytes(node.tree_hash())
        if node_hash in seen:
            return
        seen.add(node_hash)

        sha_invocations += 1

        pair = node.pair
        if pair is None:
            # Atom: preimage is 1 + len(data) bytes
            data_len = len(bytes(node.atom))
            preimage_len = 1 + data_len
        else:
            # Pair: preimage is 1 + 32 + 32 = 65 bytes
            preimage_len = 65
            first, rest = pair
            count_node(first)
            count_node(rest)

        # SHA256 block counting with padding
        padded_len = preimage_len + 9
        sha_blocks += (padded_len + 63) // 64

    count_node(program)
    return sha_blocks, sha_invocations
