# Lean 4 Formalization: serde_2026 Upper Bound

Formal proof scaffold for the theorem:

```
serde_2026_bytes ≤ atom_bytes + 2·U_a + 3·U_p + 5
```

## Status

**Scaffold only** — key lemmas and theorem statements are in place, several
proofs are `sorry`-ed. The main theorem's arithmetic core (`omega`) should go
through once Lean is installed; the component bound lemmas need the most work.

## Structure

- `Serde2026UpperBound.lean` — single-file proof with:
  - Varint encoding model
  - Tree structure definitions
  - Instruction count lemma (I = 2·U_p + 1)
  - Atom table overhead bound (≤ 2·U_a + 1)
  - Instruction stream overhead bound (≤ 3·U_p + 4)
  - **Main theorem**: combined bound
  - P=3 minimality (P=2 counterexample)
  - Theoretical edge case (atom ≥ 128 MB)

## Setup

```bash
# Install Lean 4 via elan
curl https://elan.lean-lang.org/install.sh -sSf | sh
# Initialize lake project
cd lean4
lake init serde2026proof
# Copy .lean file into lakefile structure, then:
lake build
```

## What needs doing

1. Fill in `sorry` proofs — especially `serde2026_bound_for_generators`
   (showing the extra U_p term from P=3 absorbs the +5 constant)
2. Formalize the varint size bound lemma properly
3. The P=2 counterexample needs concrete witness construction
4. Consider whether Mathlib's `omega` is sufficient or if custom tactics
   are needed for the case splits
