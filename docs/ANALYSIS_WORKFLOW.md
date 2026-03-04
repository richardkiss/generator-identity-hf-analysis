# Cost Formula Analysis Workflow

This document provides a complete step-by-step guide to run the cost formula analysis from scratch. It covers data collection, analysis, and validation of all parameters used in the Generator Identity Hard Fork.

> **Note**: For the complete technical specification and design rationale, see [GENERATOR_IDENTITY_HARDFORK.md](GENERATOR_IDENTITY_HARDFORK.md).

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Phase 1: Data Collection](#phase-1-data-collection)
3. [Phase 2: Analysis](#phase-2-analysis)
4. [Expected Results](#expected-results)
5. [Validation Checklist](#validation-checklist)
6. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

1. **Chia blockchain database** - A synced Chia full node with the blockchain database
   (typically at `~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite`)

2. **chia-scan** - Tools for extracting and analyzing blocks:
   ```bash
   pip install git+https://github.com/richardkiss/chia-scan.git
   # Or if you have it locally:
   cd /path/to/chia-scan && pip install -e .
   ```

3. **This repository** - generator-identity-hf-analysis:
   ```bash
   cd /path/to/generator-identity-hf-analysis
   uv pip install -e ".[dev]"  # or: pip install -e ".[dev]"
   ```

### Directory Structure

After setup, your repository should look like:

```
generator-identity-hf-analysis/
├── data/                    # Generator data (gitignored)
│   ├── generators/
│   │   ├── top-generators/  # Large blocks from mainnet
│   │   └── random-generators/ # Random sample
│   ├── synthetic_1M.bin    # Spend-heavy synthetic
│   └── synthetic_500K.bin
└── results/                 # Analysis results (gitignored)
    └── *.csv
```

---

## Phase 1: Data Collection

This phase requires access to a synced Chia full node database. If you don't have one, you can skip to Phase 2 and use pre-extracted generator samples.

### Step 1.1: Find Large Blocks

Identify blocks with large generators (most interesting for cost analysis):

```bash
# List the 500 largest blocks by compressed size
chia-scan list-blocks \
    --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
    --top 500 --sort size --desc \
    > large_blocks.txt

# Show top 20
head -20 large_blocks.txt
```

### Step 1.2: Extract Large Generators

Extract generators from blocks >= 50KB compressed size:

```bash
# Create output directory
mkdir -p data/generators/top-generators

# Extract generators
chia-scan extract-blocks \
    --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
    -o data/generators/top-generators \
    --size 50k- \
    --generator-only

# Count extracted files
ls data/generators/top-generators/*.bin | wc -l
```

Output files are named: `generator_{height}_{hash}.bin`

### Step 1.3: Extract Random Sample

Extract a random sample for variety (ensures we're not biased toward large blocks):

```bash
# Create directory for random sample
mkdir -p data/generators/random-generators

# Extract 100 random generators from post-transaction-era blocks
# (Height 225000+ is after transactions were enabled)
chia-scan list-blocks \
    --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
    --start 225000 --end 7500000 \
    --min-size 1k \
    | shuf -n 100 \
    | awk '{print $1}' \
    > random_heights.txt

chia-scan extract-blocks \
    --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
    -o data/generators/random-generators \
    --heights-file random_heights.txt \
    --generator-only
```

### Step 1.4: Build Synthetic Generators

Real generators from mainnet are often NFT mints with large embedded images. To test spend-heavy scenarios, build synthetic generators from real spends (excluding large atoms):

```bash
# Build ~1MB synthetic generator (many spends, no NFT data)
chia-scan build-synthetic \
    -i data/generators/top-generators \
    -o data/synthetic_1M.bin \
    --target-size 1M \
    --max-atom-size 1000

# Build ~500KB version
chia-scan build-synthetic \
    -i data/generators/top-generators \
    -o data/synthetic_500K.bin \
    --target-size 500K \
    --max-atom-size 1000

# Show statistics without writing
chia-scan build-synthetic \
    -i data/generators/top-generators \
    --stats-only
```

The `--max-atom-size 1000` filters out NFT image data, keeping only normal puzzle/solution atoms (hashes, pubkeys, conditions).

### Step 1.5: Package for Transfer (Optional)

If you're collecting data on a remote machine and analyzing locally:

```bash
# Create archive
tar -czvf generator_samples.tar.gz \
    data/generators/top-generators/*.bin \
    data/generators/random-generators/*.bin \
    data/synthetic_1M.bin \
    data/synthetic_500K.bin

# Transfer to analysis machine
rsync -avP remote_machine:generator_samples.tar.gz .
# Or use scp:
scp remote_machine:generator_samples.tar.gz .

# Extract
tar -xzvf generator_samples.tar.gz -C data/
```

---

## Phase 2: Analysis

This phase runs the analysis on the extracted generator samples. All commands should be run from the `generator-identity-hf-analysis` repository root.

### Step 2.1: SHA256 Timing Benchmark

**Purpose**: Determine the I/S ratio (invocation overhead vs per-block cost) to justify `I=8` in the formula.

```bash
python scripts/benchmark_sha.py --iterations 10000 -v
```

**Expected output:**
```
SHA256 Timing Benchmark
============================================================

Linear Model Fit
----------------------------------------
Per-block cost (S):          ~19 ns
Invocation overhead (I):    ~150 ns

I/S ratio:                    ~8

Recommendation
----------------------------------------
Use I = 8 (or 9 depending on hardware)
```

**What this tells us:**
- SHA256 invocation overhead is ~8× the per-block mixing cost
- This justifies `I=8` in the formula
- The ratio is consistent across hardware (see [Expected Results](#expected-results))

### Step 2.2: Analyze Real Generators

**Purpose**: Validate the cost formula against real mainnet generators to ensure backward compatibility.

```bash
# Analyze all extracted generators
python scripts/analyze_generators.py data/generators/top-generators \
    --batch --csv results/top-generators_analysis.csv

python scripts/analyze_generators.py data/generators/random-generators \
    --batch --csv results/random-generators_analysis.csv
```

**Expected output:**
```
Processed 400 generators
  Min ratio:  0.494
  Avg ratio:  0.505
  Max ratio:  0.515
```

**Interpretation:**
- Ratio ~0.5 means new cost is about half of old cost
- This is expected for data-heavy blocks (NFT mints with images)
- These blocks have high `atom_bytes` but few unique nodes
- For typical generators, we expect ratio ~0.99 (see [Expected Results](#expected-results))

### Step 2.3: Analyze Synthetic Generators

**Purpose**: Test spend-heavy scenarios (many transactions, high sharing) to validate the formula handles high-sharing structures correctly.

```bash
python scripts/analyze_generators.py data/synthetic_1M.bin -v
python scripts/analyze_generators.py data/synthetic_500K.bin -v
```

**Expected output for synthetic_1M:**
```
Generator: synthetic_1M.bin
Input file size: 1,047,738 bytes

Cost Components (unique nodes):
  atom_bytes:       140,263
  atom_count:       6,219
  pair_count:       29,003
  sha_blocks:       64,316
  sha_invocations:  35,222

Cost Comparison:
  Estimated length: 210,707
  Old cost:         12,572,856,000
  New cost:         2,821,656,000
  Ratio (new/old):  0.224
  Size fraction:    44.8%
  SHA fraction:     55.2%
```

**Interpretation:**
- Synthetic has many spends (high `pair_count`)
- Ratio ~0.22 because of massive sharing (classic size 1MB → unique nodes ~210KB)
- Size/SHA split is ~45/55 (balanced as intended)
- High-sharing structures correctly get lower costs

### Step 2.4: Coefficient Sweep

**Purpose**: Find optimal B, A, P values that give average cost ratio closest to 1.0 for typical generators.

```bash
python scripts/sweep_coefficients.py data/generators/top-generators \
    --B-range 1 \
    --A-range 0,1,2,3 \
    --P-range 1,2,3,4,5 \
    --target 1.0
```

**Expected output:**
```
  B   A   P     Min     Avg     Max    Dist
---------------------------------------------
  1   2   3   0.610   0.990   1.130   0.010 *
  1   1   3   0.590   0.980   1.060   0.020 *
  1   0   3   0.650   1.030   1.290   0.030
  ...

Best combination: B=1, A=2, P=3
  Average ratio: 0.99
  Range: 0.61 - 1.13
```

**Interpretation:**
- B=1, A=2, P=3 gives average ratio closest to 1.0
- This means: `size_component = atom_bytes + 2×atom_count + 3×pair_count`
- **P=3 is required** to ensure size_component ≥ serde_2026 serialized size (see [SERDE2026_UPPER_BOUND.md](SERDE2026_UPPER_BOUND.md))
- The formula matches old backref-serialized costs on average
- The range (0.61-1.13) is acceptable: low end is data-heavy blocks, high end is structure-heavy blocks

### Step 2.5: DoS Analysis

**Purpose**: Verify the formula protects against adversarial structures (many small nodes, deep nesting).

```bash
python scripts/dos_test.py -v
```

**Expected output:**
```
Results (sorted by ratio)
----------------------------------------------------------------------
⚠️  MUCH LESS  shared_balanced_tree      ratio=0.00x  nodes=13
📉 less        single_huge_atom          ratio=0.51x  nodes=1
📉 less        hash_sized_atoms          ratio=0.74x  nodes=6,001
📈 more        unique_balanced_tree      ratio=1.85x  nodes=2,047
📈 more        deep_unique_nesting       ratio=1.85x  nodes=20,001
✅ MUCH MORE   nil_list                  ratio=2.38x  nodes=10,001
✅ MUCH MORE   many_small_pairs          ratio=2.55x  nodes=20,000
✅ MUCH MORE   tiny_unique_atoms         ratio=2.55x  nodes=20,001
```

**Interpretation:**
- Structures with many small nodes cost 2-2.5× MORE (DoS protection ✅)
- Data-heavy structures cost ~0.5× (correct - low hash work per byte)
- High-sharing structures cost less (correct - fewer unique nodes)
- All adversarial structures cost 2x+ more than before

### Step 2.6: Rust Analysis Tools (Optional)

For additional detailed analysis, you can use the Rust tools:

```bash
# Detailed DoS analysis with timing
cargo run --release --bin dos-test

# Serialization benchmark and comparison
cargo run --release --bin serialization-dos-bench -- data/synthetic_1M.bin --stats
```

---

## Expected Results

### SHA256 I/S Ratio

| Hardware | Per Block | Per Invocation | I/S Ratio |
|----------|-----------|----------------|-----------|
| Apple M-series | ~19 ns | ~150 ns | ~8 |
| Intel w/ SHA-NI | ~30 ns | ~200 ns | ~7 |
| Intel 2012 (no SHA-NI) | ~520 ns | ~3400 ns | ~7 |

The ratio is consistent across hardware (6.7-7.9×), justifying `I=8` in the formula.

### Real Generator Analysis (B=1, A=2, P=3)

| Metric | Expected | Notes |
|--------|----------|-------|
| Min ratio | ~0.5 | Data-heavy NFT blocks |
| Avg ratio | ~0.99 | Typical generators |
| Max ratio | ~1.1 | Structure-heavy blocks |

### Synthetic Generator Analysis

| Generator | Classic Size | Backref Size | Estimated Len | Ratio |
|-----------|--------------|--------------|---------------|-------|
| synthetic_1M | ~1 MB | ~245 KB | ~210 KB | ~0.86 |
| synthetic_500K | ~500 KB | ~185 KB | ~188 KB | ~1.02 |

High-sharing synthetic generators get lower costs because they have fewer unique nodes - this is correct behavior.

### DoS Protection Results

All adversarial structures should cost **2x+ more** than under the old formula:

| Structure | Ratio | Protection |
|-----------|-------|------------|
| `million_nil_atoms` | 2.37× | ✅ |
| `deep_nesting` | 2.37× | ✅ |
| `many_small_pairs` | 2.25× | ✅ |

### Final Parameters

From the analysis, the final parameters are:

| Coefficient | Value | Meaning | Source |
|-------------|-------|---------|--------|
| B | 1 | Per byte of atom data | Coefficient sweep |
| A | 2 | Per-atom overhead (~1 byte length prefix + ~1 byte structure) | Coefficient sweep |
| P | 2 | Per-pair overhead | Coefficient sweep |
| S | 1 | Per SHA256 64-byte block | SHA benchmark |
| I | 8 | Per SHA256 invocation (8× block cost) | SHA benchmark |
| SIZE_COST_PER_BYTE | 6000 | Size component multiplier | Fitted to match old costs |
| SHA_COST_PER_UNIT | 4500 | SHA component multiplier | Fitted to match old costs |

**The Complete Formula:**
```
size_component = B×atom_bytes + A×atom_count + P×pair_count
               = atom_bytes + 2×atom_count + 3×pair_count

sha_component  = S×sha_blocks + I×sha_invocations  
               = sha_blocks + 8×sha_invocations

total_cost = size_component × 6000 + sha_component × 4500
```

---

## Validation Checklist

Before finalizing parameters, verify all of the following:

- [ ] **SHA benchmark**: I/S ratio is consistent (~7-9 across hardware)
- [ ] **Coefficient sweep**: B=1, A=2, P=3 gives avg ratio ~1.0 and upper bounds serde_2026
- [ ] **DoS test**: Adversarial structures cost 2x+ more
- [ ] **Synthetic generators**: Have ~45/55 size/SHA split
- [ ] **Real generators**: Have ratio range 0.5-1.1 (no extreme outliers)
- [ ] **Backward compatibility**: Typical generators cost ~96-106% of old

---

## Troubleshooting

### "bad encoding" errors

Some newer generators (blocks >6M height) may fail to parse with older versions of `clvm_rs`. Solutions:
- Use generators from earlier blocks (height < 6M)
- Update `clvm_rs` to the latest version
- Use the `generator-identity-hf` branch of `clvm_rs` which includes fixes

### Recursion depth exceeded

This was fixed in the scripts by using iterative traversal. If you see this error:
- Make sure you have the latest version of this repository
- Check that you're using Python 3.10+
- Verify `clvm_rs` is up to date

### Missing blockchain database

You need a synced Chia full node. The database is typically at:
- **Linux/macOS**: `~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite`
- **Windows**: `%USERPROFILE%\.chia\mainnet\db\blockchain_v2_mainnet.sqlite`

If you don't have access to a full node, you can:
- Use pre-extracted generator samples (if available)
- Skip Phase 1 and focus on synthetic generator analysis
- Contact the repository maintainers for sample data

### Import errors

If you see import errors for `canon_analysis`:
```bash
# Make sure you've installed the package
uv pip install -e ".[dev]"
# or
pip install -e ".[dev]"
```

### Rust toolchain issues

If Rust tools fail to build:
```bash
# Make sure Rust is installed
rustc --version

# Update Rust toolchain
rustup update

# Clean and rebuild
cargo clean
cargo build --release
```

---

## Quick Commands Summary

For reference, here's a condensed version of all commands:

```bash
# Phase 1: Data Collection (requires mainnet DB)
chia-scan extract-blocks --db ~/.chia/.../blockchain.sqlite \
    -o data/generators/top-generators --size 50k- --generator-only
chia-scan build-synthetic -i data/generators/top-generators \
    -o data/synthetic_1M.bin --target-size 1M --max-atom-size 1000

# Phase 2: Analysis
python scripts/benchmark_sha.py --iterations 10000 -v
python scripts/analyze_generators.py data/generators/top-generators \
    --batch --csv results/top-generators_analysis.csv
python scripts/analyze_generators.py data/synthetic_1M.bin -v
python scripts/sweep_coefficients.py data/generators/top-generators
python scripts/dos_test.py -v
```

---

## Next Steps

After reproducing the analysis:

1. **Review the technical specification**: See [GENERATOR_IDENTITY_HARDFORK.md](GENERATOR_IDENTITY_HARDFORK.md) for the complete design rationale, DoS analysis, and implementation details.

2. **Check the implementation PRs**: The analysis in this repository supports three implementation PRs:
   - PR #1 (clvm_rs): Core interning infrastructure
   - PR #2 (chia_rs): Chia-specific cost calculation
   - PR #3 (clvm_rs): New serialization format (future work)

3. **Validate your results**: Compare your findings against the expected results in this document and the validation checklist above.
