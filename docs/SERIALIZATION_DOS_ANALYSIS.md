# Serialization DOS Attack Analysis

This document analyzes a potential denial-of-service vulnerability in generator deserialization and proposes a mitigation based on a provable size bound.

## Important: This is a Peer Protocol Issue, Not Consensus

**This DOS vulnerability exists at the peer protocol layer, not the consensus layer.**

- **Consensus** defines what makes a block *valid* (generator content, cost limits, etc.)
- **Peer protocol** defines how nodes *communicate* (message formats, size limits, etc.)

A peer sending a 125 MB bloated serialization isn't sending an invalid generator - they're sending a wasteful *encoding* of a potentially valid generator. Since any valid generator can be re-serialized to ≤ 2 MB, we can reject oversized messages at the peer layer without affecting consensus validity.

**Implications:**
1. **No hard fork required** - this is a peer protocol update, not a consensus change
2. **Flexible rollout** - nodes can adopt the fix independently
3. **Adjustable limits** - can tune thresholds without consensus implications
4. **Zero consensus risk** - cannot accidentally invalidate valid blocks
5. **Scamp peers can be rejected** - misbehaving peers can be disconnected

If a peer insists on sending bloated serializations, we simply reject them and optionally disconnect. A well-behaved peer can always re-encode their valid generator to fit within limits.

---

## The Problem

When a peer sends a serialized generator, the receiving node must:

1. **Deserialize** the bytes into an in-memory CLVM tree
2. **Intern** the tree (deduplicate atoms and pairs)
3. **Calculate cost** based on the interned structure
4. **Reject** if cost exceeds the 11B limit

The concern: **Steps 1-3 happen before step 4**. An attacker could send a very large serialization that takes significant time to process, even though it will ultimately be rejected.

### The Attack Vector

The backref serialization format allows referencing previously-defined nodes. An attacker can exploit this by:

1. Creating ~210,000 node definitions (which fits within the 11B cost budget)
2. Adding ~62.3 million backrefs pointing to those nodes
3. Total serialization: **~125 MB**
4. After interning: only ~210,000 unique nodes, cost ≈ 11B ✓

The deserializer processes all 62.5M elements before cost is calculated, creating a DOS opportunity.

## The Solution: Canonical Size Bound

**Key insight:** We don't need different limits for different formats. Instead, we can establish a single upper bound based on the **maximum size of the most compact representation** of any valid generator.

Any well-behaved peer can rewrite their serialization to be under this bound. Anything larger is either:
1. A generator that exceeds cost (will be rejected anyway), or
2. An inefficient/malicious encoding that could be rewritten smaller

## Constants

| Constant | Value | Description |
|----------|-------|-------------|
| MAX_COST | 11,000,000,000 | Maximum generator cost |
| SIZE_COST_PER_BYTE | 6,000 | Size component multiplier |
| SHA_COST_PER_UNIT | 4,500 | SHA component multiplier |
| B | 1 | Per byte of atom data |
| A | 2 | Per-atom overhead |
| P | 2 | Per-pair overhead |
| S | 1 | Per SHA256 block |
| I | 8 | Per SHA256 invocation |

## Cost Formula

```
size_component = B × atom_bytes + A × atom_count + P × pair_count
sha_component  = S × sha_blocks + I × sha_invocations
total_cost     = size_component × SIZE_COST_PER_BYTE + sha_component × SHA_COST_PER_UNIT
```

## Proof: Maximum Minimal Serialization Size

### What is "Minimal Serialization"?

For any CLVM tree, the **minimal serialization** is the smallest possible byte representation. This is achieved by:
- Classic format: each unique node serialized exactly once
- Backref format: using backrefs only when they reduce size (referencing subtrees larger than the backref itself)

Since backrefs exist to *compress*, a well-formed backref serialization is always ≤ the classic serialization of the same tree. Therefore, the **classic serialization size is an upper bound for both formats**.

### Minimum Cost Per Serialization Byte

The cost formula charges different amounts per byte depending on structure:

**Large atoms** (most bytes per unit cost):
```
For atom of N bytes:
  size_component  = N + 2
  sha_blocks      = ceil((N + 10) / 64) ≈ N/64 for large N
  sha_invocations = 1
  sha_component   = N/64 + 8 + 1 ≈ N/64 + 9

  total_cost = (N + 2) × 6000 + (N/64 + 9) × 4500
             = 6000N + 12000 + 70.3N + 40500
             ≈ 6070N + 52500

  serialized_size ≈ N + 3  (data + size prefix)
```

**Cost per serialization byte ≈ 6,070** (for large atoms)

**Small atoms/pairs** (fewer bytes per unit cost):
```
Nil atom:
  serialized_size = 1 byte
  cost = 52,500
  cost per byte = 52,500

Pair marker:
  serialized_size = 1 byte
  cost = 57,000
  cost per byte = 57,000
```

**Key observation:** Large atoms give the **best bytes-per-cost ratio**. You cannot get more serialization bytes per unit cost than ~1 byte per 6,070 cost.

### The Bound

Since the minimum cost per serialization byte is ~6,070:

```
max_serialization_size = MAX_COST / min_cost_per_byte
                       = 11,000,000,000 / 6,070
                       ≈ 1,812,000 bytes
                       ≈ 1.81 MB
```

**Theorem:** The minimal serialization of any generator within the 11B cost limit is at most **~1.81 MB**.

**Proof:** 
- The minimum cost per serialization byte is ~6,070 (achieved by large atoms)
- Any structure with more bytes would require more cost
- At 11B cost limit: max bytes = 11B / 6,070 ≈ 1.81 MB
- Adding small atoms or pairs only increases cost without proportionally increasing serialization size
- Therefore, no valid generator can have a minimal serialization larger than ~1.81 MB ∎

**Corollary:** Any serialization (classic OR backref) larger than 2 MB can be safely rejected because:
1. If the underlying generator fits within cost, it can be rewritten to ≤ 1.81 MB
2. If it cannot be rewritten smaller, the generator exceeds cost anyway

## Recommended Implementation

### Single Size Limit for All Formats

```rust
/// Maximum serialization size for any generator.
/// 
/// Proof: The minimum cost per serialization byte is ~6,070 (large atoms).
/// At MAX_COST = 11B: max_size = 11B / 6070 ≈ 1.81 MB.
/// We use 2 MB to provide margin for size prefix overhead.
/// 
/// Any serialization larger than this either:
/// 1. Represents a generator exceeding the cost limit, or
/// 2. Is an inefficient encoding that could be rewritten smaller
/// 
/// A well-behaved peer can always represent a valid generator in ≤ 2 MB.
const MAX_SERIALIZATION_SIZE: usize = 2_000_000;  // 2 MB

pub fn node_from_bytes(allocator: &mut Allocator, b: &[u8]) -> Result<NodePtr> {
    if b.len() > MAX_SERIALIZATION_SIZE {
        return Err(EvalErr::SerializationTooLarge);
    }
    // ... existing deserialization code
}

pub fn node_from_bytes_backrefs(allocator: &mut Allocator, b: &[u8]) -> Result<NodePtr> {
    if b.len() > MAX_SERIALIZATION_SIZE {
        return Err(EvalErr::SerializationTooLarge);
    }
    // ... existing deserialization code
}
```

### Why One Limit Works for Both Formats

| Format | Relationship to Minimal Size |
|--------|------------------------------|
| Classic | IS the minimal size (each node once) |
| Backref | ≤ minimal size (backrefs only compress) |

A backref serialization larger than the classic equivalent contains unnecessary backrefs that add bytes without benefit. Such a serialization can always be rewritten smaller by removing the useless backrefs.

Therefore, **the same 2 MB limit applies to both formats**.

## Impact Analysis

### Legitimate Generators

| Generator Type | Typical Size | Status |
|----------------|--------------|--------|
| Average mainnet | 100-500 KB | ✅ Well under limit |
| Large mainnet | ~1 MB | ✅ Under limit |
| Maximum valid | ~1.81 MB | ✅ Under limit |

The 2 MB limit provides ~10% headroom above the theoretical maximum.

### Attack Mitigation

| Metric | Before | After |
|--------|--------|-------|
| Max accepted serialization | ~125 MB | 2 MB |
| Max deserialize operations | 62.5M | ~500K |
| Worst-case parse time | seconds | <50ms |

## Implementation Checklist

Since this is a peer protocol fix (not consensus), implementation can be done incrementally:

### Phase 1: Add Size Checks to clvm_rs (Defense in Depth)
- [ ] Add `MAX_SERIALIZATION_SIZE` constant (2 MB)
- [ ] Add size check at start of `node_from_bytes()`
- [ ] Add size check at start of `node_from_bytes_backrefs()`
- [ ] Add size check at start of `deserialize_2026()`
- [ ] Add new error variant `EvalErr::SerializationTooLarge`
- [ ] Add tests verifying rejection of oversized serializations
- [ ] Add test verifying acceptance of maximum valid generator (~1.81 MB)

### Phase 2: Peer Protocol Enforcement (chia-blockchain)
- [ ] Add size check before deserializing generator in peer message handling
- [ ] Log/metric for rejected oversized messages
- [ ] Consider rate limiting or disconnecting repeat offenders

### Notes
- Phase 1 provides defense in depth even if peer protocol isn't updated immediately
- Phase 2 can reject early (before deserialization) for efficiency
- No consensus changes needed - valid blocks are unaffected
- Peers sending oversized blobs are either buggy or malicious; either way, reject them

---

## Bounds for Other Serialization Formats

The 2 MB bound applies to classic and backref formats. Other formats need their own analysis.

### Classic + zstd (Compressed Classic)

**Flow:** compressed blob → decompress → check size → deserialize

**Bounds:**
1. **Decompressed size limit: 2 MB** (same as classic)
2. **Compressed size limit: 2 MB** (prevents decompression bombs from wasting CPU)

**Implementation:**
```rust
const MAX_COMPRESSED_SIZE: usize = 2_000_000;
const MAX_DECOMPRESSED_SIZE: usize = 2_000_000;

pub fn deserialize_zstd(compressed: &[u8]) -> Result<NodePtr> {
    if compressed.len() > MAX_COMPRESSED_SIZE {
        return Err(EvalErr::SerializationTooLarge);
    }
    
    // Decompress with size limit to prevent decompression bombs
    let decompressed = zstd_decompress_with_limit(compressed, MAX_DECOMPRESSED_SIZE)?;
    
    // Now deserialize the classic format
    node_from_bytes(allocator, &decompressed)
}
```

**Rationale:**
- The decompressed output is classic format, so the 2 MB limit applies
- Compression cannot create valid generators larger than 1.81 MB decompressed
- A well-behaved peer can always compress a valid generator

### serde_2026 Format

**Format structure:**
1. Atom table: all unique atoms, grouped by length
2. Instruction stream: stack-based ops (push atom, cons, push pair ref)

**Key property:** serde_2026 serializes the **interned** tree. Each unique atom and pair appears exactly once. Unlike backref format, there's no way to inflate the serialization with redundant references.

**Bound analysis:**

The serialization size has two components:

1. **Atom table:** ≤ atom_bytes + overhead
   - From cost: max atom_bytes ≈ 1.81 MB
   - Overhead: O(length_groups) varints, negligible

2. **Instruction stream:** bounded by 3 × pair_count
   - Each pair requires: 2 child references + 1 cons
   - From cost: max pairs ≈ 193K (at 57,000 cost each)
   - Max instructions: 3 × 193K = 579K
   - Max instruction bytes: 579K × 3 = 1.74 MB (3-byte varints)

**Critical observation:** These maximums are mutually exclusive!
- Max atom bytes (1.81 MB) requires ~1 huge atom → minimal instruction stream
- Max instructions (579K) requires ~193K pairs → minimal atom bytes

**Proof of 2 MB bound for serde_2026:**

Let A = atom_bytes, P = pair_count.

Cost constraint: `A × 6070 + P × 57000 ≤ 11,000,000,000`

Serialization size: `S ≈ A + 3P × avg_varint_size`

To find max S, we solve the linear program:
- Maximize: A + 3P × 3 (assuming 3-byte varints)
- Subject to: 6070A + 57000P ≤ 11B

Corner solutions:
- A = 1.81M, P = 0: S ≈ 1.81 MB
- A = 0, P = 193K: S ≈ 579K × 3 = 1.74 MB

**Maximum serde_2026 size ≈ 1.81 MB** ✓

**Recommended limit: 2 MB** (same as other formats)

```rust
pub fn deserialize_2026(allocator: &mut Allocator, data: &[u8]) -> Result<NodePtr> {
    if data.len() > MAX_SERIALIZATION_SIZE {
        return Err(EvalErr::SerializationTooLarge);
    }
    // ... existing deserialization code
}
```

### Summary: Bounds by Format

| Format | Max Minimal Size | Recommended Limit | Notes |
|--------|------------------|-------------------|-------|
| Classic | 1.81 MB | 2 MB | Each node serialized once |
| Backref | 1.81 MB | 2 MB | Same tree, backrefs only compress |
| Classic + zstd | 1.81 MB (decompressed) | 2 MB each | Check both compressed and decompressed |
| serde_2026 | 1.81 MB | 2 MB | Inherently bounded (no inflation possible) |

### Future Formats

For any new serialization format, establish bounds by answering:

1. **What is the minimum cost per serialization byte?**
   - This gives the theoretical max size for valid generators

2. **Can the format be inflated beyond the minimal representation?**
   - Classic: No (each node once)
   - Backref: Yes (redundant backrefs) → but minimal form ≤ classic
   - serde_2026: No (interned, each node once)
   - Compressed formats: Check decompressed size

3. **Is there decompression/expansion that could be exploited?**
   - Compression: limit both compressed and decompressed size
   - Any expansion step: apply size limit before expansion

**General principle:** The 2 MB limit is derived from the cost formula, not the format. Any format representing a valid generator can be rewritten to ≤ 2 MB in its most compact form. Apply this limit universally.

---

## Summary

| Question | Answer |
|----------|--------|
| Is there a DOS vulnerability? | Yes - backref can inflate to 125 MB with valid cost |
| Can we bound serialization size? | Yes - 2 MB maximum for all formats |
| Is the bound format-independent? | Yes - derived from cost formula |
| Will legitimate generators be rejected? | No - max valid is ~1.81 MB |
| Is the bound provable? | Yes - minimum cost per byte is ~6,070 |

## Benchmark Results

Run the benchmark tool to verify these findings on your hardware:

```bash
cd /path/to/canonical-generator-analysis/tools
cargo run --release --bin serialization-dos-bench
```

Sample results (Apple M-series):

| Test Case | Classic Size | Backref Size | Compression | Deserialize | Intern |
|-----------|-------------|--------------|-------------|-------------|--------|
| many_nil_atoms (190K pairs) | 380 KB | 190 KB | 2x | ~1ms | ~17ms |
| huge_atom (1.8 MB) | 1.80 MB | 1.80 MB | 1x | <0.1ms | <0.5ms |
| deep_pairs (180K) | 360 KB | 180 KB | 2x | ~1ms | ~17ms |
| balanced_tree (depth 17) | 262 KB | **52 B** | **5041x** | ~0.5ms | ~10ms |
| hash_sized_atoms (35K) | 1.19 MB | 1.19 MB | 1x | <0.5ms | ~7ms |
| backref_sharing (depth 18) | 524 KB | **55 B** | **9532x** | ~1ms | ~20ms |

**Key observations:**
- All edge-of-budget generators process in <25ms total
- The 2 MB limit catches all valid generators
- Backref compression can be dramatic (9500x) for shared structures
- Without size limit, a 125 MB attack would require processing 62.5M elements

## References

- GENERATOR_IDENTITY_HARDFORK.md - Cost formula derivation
- src/serde/de.rs - Classic deserialization
- src/serde/de_br.rs - Backref deserialization
- src/serde_2026/mod.rs - 2026 format (in serde_2026 branch)
- canonical-generator-analysis/tools/src/bin/serialization-dos-bench.rs - Benchmark tool
