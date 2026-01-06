# Benchmark Workflow for Cost Formula Parameters

This document describes the complete workflow for deriving and validating the
cost formula parameters (B, A, P, S, I, SIZE_COST_PER_BYTE, SHA_COST_PER_UNIT).

## Overview

The workflow has two phases:

1. **Data Collection** (requires mainnet DB) - Extract generators from blockchain
2. **Analysis** (local) - Run benchmarks and derive parameters

## Phase 1: Data Collection (Remote Machine with Mainnet DB)

These commands require access to a synced Chia full node database.

### Prerequisites

```bash
# Install vibed-chia-tools (chia-scan)
pip install git+https://github.com/Chia-Network/vibed-chia-tools.git

# Or if you have it locally:
cd /path/to/vibed-chia-tools && pip install -e .
```

### Step 1.1: Find Large Blocks

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

```bash
# Create output directory
mkdir -p generators/top-400

# Extract generators from blocks >= 50KB compressed
chia-scan extract-blocks \
    --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
    -o generators/top-400 \
    --size 50k- \
    --generator-only

# Count extracted files
ls generators/top-400/*.bin | wc -l
```

### Step 1.3: Extract Random Sample

```bash
# Create directory for random sample
mkdir -p generators/random-100

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
    -o generators/random-100 \
    --heights-file random_heights.txt \
    --generator-only
```

### Step 1.4: Build Synthetic Generators

Synthetic generators combine real spends without large atoms (NFT images):

```bash
# Build ~1MB synthetic (spend-heavy, no NFT data)
chia-scan build-synthetic \
    -i generators/top-400 \
    -o synthetic_1M.bin \
    --target-size 1M \
    --max-atom-size 1000

# Build ~500KB synthetic
chia-scan build-synthetic \
    -i generators/top-400 \
    -o synthetic_500K.bin \
    --target-size 500K \
    --max-atom-size 1000

# Show statistics
chia-scan build-synthetic \
    -i generators/top-400 \
    --stats-only
```

### Step 1.5: Package for Transfer

```bash
# Create archive
tar -czvf generator_samples.tar.gz \
    generators/top-400/*.bin \
    generators/random-100/*.bin \
    synthetic_1M.bin \
    synthetic_500K.bin

# Show size
ls -lh generator_samples.tar.gz
```

### Step 1.6: Transfer to Analysis Machine

```bash
# From analysis machine:
rsync -avP remote_machine:generator_samples.tar.gz .

# Or use scp:
scp remote_machine:generator_samples.tar.gz .

# Extract
tar -xzvf generator_samples.tar.gz -C data/
```

---

## Phase 2: Analysis (Local Machine)

These commands run the analysis on the extracted generator samples.

### Prerequisites

```bash
cd /path/to/canonical-generator-analysis
pip install -e ".[dev]"
```

### Step 2.1: SHA256 Timing Benchmark

Determine the I/S ratio (invocation overhead vs per-block cost):

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
- This justifies I=8 in the formula

### Step 2.2: Analyze Real Generators

```bash
# Analyze all extracted generators
python scripts/analyze_generators.py data/generators/top-400 \
    --batch --csv results/top400_analysis.csv

python scripts/analyze_generators.py data/generators/random-100 \
    --batch --csv results/random100_analysis.csv
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

### Step 2.3: Analyze Synthetic Generators

```bash
python scripts/analyze_generators.py data/synthetic_1M.bin
python scripts/analyze_generators.py data/synthetic_500K.bin
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
- Synthetic has many spends (high pair_count)
- Ratio ~0.22 because of massive sharing (classic size 1MB → unique nodes ~210KB)
- Size/SHA split is ~45/55 (balanced as intended)

### Step 2.4: Coefficient Sweep

Find optimal B, A, P values:

```bash
python scripts/sweep_coefficients.py data/generators/top-400 \
    --B-range 1 \
    --A-range 0,1,2,3 \
    --P-range 1,2,3,4,5 \
    --target 1.0
```

**Expected output:**
```
  B   A   P     Min     Avg     Max    Dist
---------------------------------------------
  1   2   2   0.610   0.990   1.130   0.010 *
  1   1   2   0.590   0.980   1.060   0.020 *
  1   0   3   0.650   1.030   1.290   0.030
  ...

Best combination: B=1, A=2, P=2
  Average ratio: 0.99
  Range: 0.61 - 1.13
```

**Interpretation:**
- B=1, A=2, P=2 gives average ratio closest to 1.0
- This means: `estimated_len = atom_bytes + 2*atom_count + 2*pair_count`
- The formula matches old backref-serialized costs on average

### Step 2.5: DoS Analysis

Verify formula protects against adversarial structures:

```bash
python scripts/dos_test.py -v -t
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
- Data-heavy structures cost ~0.5× (correct - low hash work)
- High-sharing structures cost less (correct - fewer unique nodes)

---

## Deriving the Final Parameters

### Size Component Coefficients

From coefficient sweep on real generators:

| Coefficient | Value | Meaning |
|-------------|-------|---------|
| B | 1 | Per byte of atom data |
| A | 2 | Per-atom overhead (~1 byte length prefix + ~1 byte structure) |
| P | 2 | Per-pair overhead |

### SHA Component Coefficients  

From SHA256 timing benchmark:

| Coefficient | Value | Meaning |
|-------------|-------|---------|
| S | 1 | Per SHA256 64-byte block |
| I | 8 | Per SHA256 invocation (8× block cost) |

### Multipliers

To achieve ~50/50 split between size and SHA components:

| Multiplier | Value | Derivation |
|------------|-------|------------|
| SIZE_COST_PER_BYTE | 6000 | Half of old COST_PER_BYTE (12000) |
| SHA_COST_PER_UNIT | 4500 | Fitted to match old costs for typical generators |

### The Complete Formula

```
size_component = B×atom_bytes + A×atom_count + P×pair_count
               = atom_bytes + 2×atom_count + 2×pair_count

sha_component  = S×sha_blocks + I×sha_invocations  
               = sha_blocks + 8×sha_invocations

total_cost = size_component × 6000 + sha_component × 4500
```

---

## Validation Checklist

Before finalizing parameters, verify:

- [ ] SHA benchmark I/S ratio is consistent (~7-9 across hardware)
- [ ] Coefficient sweep shows B=1, A=2, P=2 gives avg ratio ~1.0
- [ ] DoS test shows adversarial structures cost 2x+ more
- [ ] Synthetic generators have ~45/55 size/SHA split
- [ ] Real generators have ratio range 0.5-1.1 (no extreme outliers)

---

## Quick Commands Summary

```bash
# On remote machine (with mainnet DB):
chia-scan extract-blocks --db ~/.chia/.../blockchain.sqlite \
    -o generators --size 50k- --generator-only
chia-scan build-synthetic -i generators -o synthetic_1M.bin --target-size 1M

# Transfer:
rsync -avP remote:generators/ data/generators/
rsync -avP remote:synthetic_*.bin data/

# On analysis machine:
python scripts/benchmark_sha.py
python scripts/analyze_generators.py data/generators --batch --csv results.csv
python scripts/sweep_coefficients.py data/generators
python scripts/dos_test.py -v
```
