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

from clvm_rs import Program


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


def count_sha_work(program: Program) -> tuple[int, int]:
    """
    Count SHA256 work required for tree hashing.

    Traverses unique nodes and counts SHA256 blocks needed.
    Uses iterative traversal with explicit stack.

    Args:
        program: A clvm_rs Program

    Returns:
        Tuple of (sha_blocks, sha_invocations)
    """
    seen: set[bytes] = set()
    sha_blocks = 0
    sha_invocations = 0

    stack = [program]

    while stack:
        node = stack.pop()
        node_hash = bytes(node.tree_hash())

        if node_hash in seen:
            continue
        seen.add(node_hash)

        sha_invocations += 1

        pair = node.pair
        if pair is None:
            # Atom: preimage is 1 + len(data) bytes
            data = bytes(node.atom) if node.atom is not None else b''
            preimage_len = 1 + len(data)
        else:
            # Pair: preimage is 1 + 32 + 32 = 65 bytes
            preimage_len = 65
            first, rest = pair
            stack.append(rest)
            stack.append(first)

        # SHA256 block counting with padding
        # Padding adds 1 byte (0x80) + 8 bytes (length) + padding to 64-byte boundary
        padded_len = preimage_len + 9
        sha_blocks += (padded_len + 63) // 64

    return sha_blocks, sha_invocations
