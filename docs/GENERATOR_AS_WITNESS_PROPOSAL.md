# Proposal: Generator as Pure Witness

## Summary

This document explores a potential simplification to Chia's consensus model: treating the block generator as a **witness** rather than a consensus-critical artifact. Instead of committing to the generator itself (via hash), we would only commit to its **output** — the coin state transitions and authorization.

> **Note**: This is a more radical alternative to the current Generator Identity Hard Fork plan. It's presented here for discussion and future consideration, but is not part of the current implementation plan.

## Background

### Current State

Blocks currently commit to multiple related values:

| Field | Location | Purpose |
|-------|----------|---------|
| `generator_root` | `transactions_info` | Hash of serialized generator |
| `additions_root` | `foliage_transaction_block` | Merkle root of created coins |
| `removals_root` | `foliage_transaction_block` | Merkle root of spent coins |
| `aggregated_signature` | `transactions_info` | BLS signature authorizing spends |
| `cost` | `transactions_info` | Declared execution cost |

### Planned Hard Fork (generator-identity-hf)

The current hard fork plan changes `generator_root` from:
- **Old**: `sha256(serialized_generator_bytes)`
- **New**: `sha256tree(interned_canonical_generator)`

This decouples serialization format from consensus while still committing to the generator code.

## The Proposal

Go further: **don't commit to the generator at all**.

The generator becomes a pure witness — a proof that it's possible to achieve the declared state transition. Consensus cares only about:

1. `additions_root` — what coins were created
2. `removals_root` — what coins were spent
3. `aggregated_signature` — that the spends were authorized

### Implementation

The hard fork could be simplified to:
1. Set `generator_root` to a constant (e.g., `0x00...00`) and skip validation
2. Optionally: skip verification that declared `cost` matches actual execution cost (just enforce `max_cost` limit)

## Analysis

### Why This Is Sound

**The generator is already practically a witness:**
- Full nodes don't need generators after validation — they only store them to help other nodes sync
- The actual consensus state is the coin set, derived from `additions_root` and `removals_root`
- Generators are validated once, then (optionally) discarded

**Signature binding prevents substitution attacks:**
- The BLS `aggregated_signature` is verified against messages derived from AGG_SIG conditions
- Different AGG_SIG conditions → different messages → signature verification fails
- Finding alternative conditions that verify against the same signature would break BLS security

**Other conditions don't need separate commitment:**
- `CREATE_COIN` → captured in `additions_root`
- `RESERVE_FEE` → redundant with `inputs - outputs`
- `ASSERT_*` (timelocks, etc.) → validation rules that pass or fail; no need to record which checks were present
- Announcements/Messages → inter-spend coordination, pass or fail

**Multiple valid witnesses are acceptable:**
- If two different generators produce identical `(additions_root, removals_root)` and pass signature verification, they are economically equivalent
- There's no reason to prefer one over the other

### Benefits

1. **Complete VM decoupling**: CLVM becomes entirely non-consensus. The execution environment could be changed, optimized, or replaced without hard forks.

2. **Path to succinct proofs**: This architecture enables future zkSNARK integration — prove state transitions are valid with a compact proof instead of re-executing the generator.

3. **Cleaner abstraction**: Separates "what happened" (coins changed, authorization provided) from "how we proved it" (generator execution).

4. **Simpler hard fork**: Instead of changing *how* the generator is hashed, simply stop hashing it.

5. **Future flexibility**: Alternative proof systems, optimized execution paths, or compiled generators become possible.

### Concerns and Mitigations

| Concern | Assessment |
|---------|------------|
| **Block substitution attack** | Not viable — attacker would need different generator producing identical coin transitions with valid signature |
| **Validation time unpredictability** | Real but bounded — worst case is `max_cost`, same as today. Operational concern, not security. |
| **Cost field reliability** | If not checked, becomes informational only. Nodes can still compute/populate it for tooling. |
| **Mempool prioritization** | Nodes already compute cost locally during mempool admission. Minor complexity increase. |
| **Tooling/Analytics** | Block explorers may need updates. Not a consensus issue. |
| **Future soft-fork optionality** | Lose ability to add generator-hash-based rules. Acceptable tradeoff. |
| **Light client proofs** | Can't prove "what timelocks were present" without generator. Rarely needed. |
| **Forensics/Audit trail** | Lose guarantee of "this exact code ran." Nodes can still store generators voluntarily. |

### What About Committing to Conditions?

We considered whether to commit to the full conditions output (not just coins). Conclusion: **not necessary**.

- AGG_SIG conditions are implicitly committed via signature verification
- Other conditions are pass/fail validation rules — if the block is valid, they passed
- No security benefit to recording which checks were present

## Implementation Sketch

### Consensus Changes

```python
# Before (current)
if std_hash(bytes(block.transactions_generator)) != block.transactions_info.generator_root:
    return Err.INVALID_TRANSACTIONS_GENERATOR_HASH

# After (proposed)
if block.height >= WITNESS_FORK_HEIGHT:
    if block.transactions_info.generator_root != bytes32.zeros:
        return Err.INVALID_TRANSACTIONS_GENERATOR_HASH
else:
    # Old validation for historical blocks
    if std_hash(bytes(block.transactions_generator)) != block.transactions_info.generator_root:
        return Err.INVALID_TRANSACTIONS_GENERATOR_HASH
```

### Cost Field (Optional Simplification)

```python
# Before
if block.transactions_info.cost != actual_cost:
    return Err.INVALID_BLOCK_COST

# After
if actual_cost > constants.MAX_BLOCK_COST_CLVM:
    return Err.BLOCK_COST_EXCEEDS_MAX
# (declared cost not verified, just informational)
```

### Block Creation

When creating blocks, set:
- `generator_root = bytes32.zeros`
- `cost` = actual computed cost (for tooling, even if not consensus-verified)

## Comparison with Current Hard Fork Plan

| Aspect | Current Plan (tree hash) | This Proposal (witness) |
|--------|-------------------------|------------------------|
| Generator format | Non-consensus | Non-consensus |
| Generator content | Consensus (tree hash) | Non-consensus |
| CLVM semantics | Consensus | Consensus (for validation) |
| Future VM changes | Hard fork required | No fork required |
| zkSNARK path | Blocked | Open |
| Implementation complexity | Moderate | Simpler |

## Open Questions

1. **Should cost remain consensus-verified?** Removing the check simplifies things but loses a useful signal. Could keep the check with minimal overhead.

2. **Transition timeline**: Could do this as the planned hard fork, or as a follow-up. Doing it now is simpler (one fork instead of two).

3. **Tooling impact**: Need to assess which tools rely on `generator_root` or `cost` being consensus-verified.

## Relationship to Generator Identity Hard Fork

This proposal represents a more radical alternative to the current Generator Identity Hard Fork:

- **Current plan**: Decouple serialization from consensus by using tree hash instead of serialized bytes hash
- **This proposal**: Decouple generator entirely from consensus by not committing to it at all

Both approaches achieve the goal of making consensus independent of serialization format, but this proposal goes further by making the generator itself non-consensus.

## Conclusion

Treating the generator as a pure witness is a sound architectural choice that:
- Aligns with how full nodes already operate (generators discarded after validation)
- Maintains all security properties (coins and signatures still fully validated)
- Opens significant future optionality (alternative VMs, succinct proofs)
- Simplifies the planned hard fork

The main tradeoffs are operational (validation time unpredictability, tooling updates) rather than security-related. Given that a hard fork is already planned, this simplification appears to be a reasonable path forward, though it represents a more significant architectural change than the current plan.

---

**Source**: This proposal was originally discussed in the Chia blockchain repository. It's included here for discussion and future consideration as a potential alternative or follow-up to the Generator Identity Hard Fork.
