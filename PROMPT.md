# Task: Update generator-identity-hf-analysis docs

## Context

The repo `~/projects/generator-identity-hf-analysis/main/` contains documentation for the Chia generator identity hard fork. Several docs are out of date — the code has evolved and key decisions have been made since they were written.

## Current state of the hard fork implementation

The implementation lives in two PRs on `Chia-Network/chia_rs`:

- **PR #1371** — Split cost model: `cost = size * 6000 + sha * 4500`
- **PR #1377** — Pure storage model: `cost = size * 12000` (SHA component removed entirely)

Both use the same size formula: `size = atom_bytes + 2*atom_count + 3*pair_count`

Key facts that the docs must reflect:
- **P=3** (pair coefficient), not P=2. Changed because P=2 failed to upper-bound serialized byte count for 2 of 6 real generators. P=3 passes all with margin ≥403 bytes.
- The `INTERNED_GENERATOR` consensus flag activates at `hard_fork2_height`
- Generators are deserialized, interned (deduplicated), then cost is computed from the canonical tree
- `run_block_generator2` dispatches to the interned path when `INTERNED_GENERATOR` is set
- The interned path uses `run_block_generator_inner` (shared execution logic extracted to avoid duplication)
- `run_spendbundle` also uses interned cost for mempool validation
- There is NO `run_block_generator3` — it's all done via `run_block_generator2` with flag dispatch
- The upper bound proof for P=3 is in `docs/SERDE2026_UPPER_BOUND.md` (has uncommitted updates)

## Your tasks

1. **Read ALL docs** in `~/projects/generator-identity-hf-analysis/main/docs/`:
   - `GENERATOR_IDENTITY_HARDFORK.md` — the main doc
   - `SERDE2026_UPPER_BOUND.md` — proof that P=3 gives upper bound
   - `ANALYSIS_WORKFLOW.md` — benchmark workflow
   - `GENERATOR_AS_WITNESS_PROPOSAL.md` — alternative proposal
   - `SERIALIZATION_DOS_ANALYSIS.md` — DoS analysis

2. **Also read** `README.md` in the repo root.

3. **Update docs to be accurate**:
   - Fix P=2 → P=3 everywhere
   - Fix any references to `run_block_generator3` (doesn't exist)
   - Update the constants table if it shows wrong values
   - Make sure the formula explanation matches reality
   - Add cross-references between docs where useful (e.g., GENERATOR_IDENTITY_HARDFORK.md should reference SERDE2026_UPPER_BOUND.md for the P=3 proof)
   - Note that both cost model variants (split and pure storage) exist as competing PRs
   - Fix any stale references to branches, PRs, or code locations
   - Remove speculation about things that have been decided

4. **Commit uncommitted changes** first (the existing modifications to README.md and SERDE2026_UPPER_BOUND.md, plus untracked files), then make your doc updates as a separate commit.

5. **Push to origin** when done.

6. **Write a summary** of all changes made to `~/CONTROL-CENTER/inbox/update-analysis-docs.md`.

## Important
- Don't rewrite docs from scratch — make targeted fixes
- Keep the docs' existing structure and voice
- The `lean4/` directory is a Lean 4 proof project — leave it alone but it's fine to reference it
- The `scripts/test_formula_comprehensive.py` is a test script — commit it but don't modify it
- Cross-reference: GENERATOR_IDENTITY_HARDFORK.md should link to SERDE2026_UPPER_BOUND.md for the P=3 proof
- The two PRs (#1371 split model, #1377 pure storage) should be mentioned as the implementation options
