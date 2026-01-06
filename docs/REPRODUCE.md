# Reproducing the Analysis

This document explains how to reproduce the cost formula analysis from scratch.

## Prerequisites

1. **Chia blockchain database** - A synced Chia full node with the blockchain database
   (typically at `~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite`)

2. **vibed-chia-tools** - Tools for extracting and analyzing blocks:
   ```bash
   cd /path/to/vibed-chia-tools
   uv sync  # or: pip install -e .
   ```

3. **This repo** - canonical-generator-analysis:
   ```bash
   cd /path/to/canonical-generator-analysis
   uv pip install -e ".[dev]"
   ```

## Step 1: Extract Real Generators

### Find Large Blocks

First, identify blocks with large generators (these are the most interesting for cost analysis):

```bash
# List the 500 largest blocks
chia-scan list-blocks \
    --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
    --top 500 --sort size --desc
```

### Extract Generators

Extract generators from large blocks:

```bash
# Extract generators from blocks >= 50KB compressed size
chia-scan extract-blocks \
    --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
    -o ./data/generators/top-generators \
    --size 50k- \
    --generator-only

# Also extract ~100 random blocks for variety
chia-scan extract-blocks \
    --db ~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite \
    -o ./data/generators/random-generators \
    --height 225000-7500000 \
    --generator-only \
    --random 100
```

Output files are named: `generator_{height}_{hash}.bin`

## Step 2: Build Synthetic Generators

Real generators from mainnet are often NFT mints with large embedded images.
To test spend-heavy scenarios, build synthetic generators from real spends:

```bash
# Build a ~1MB synthetic generator (many spends, no large atoms)
chia-scan build-synthetic \
    -i ./data/generators/top-generators \
    -o ./data/synthetic_1M.bin \
    --target-size 1M \
    --max-atom-size 1000

# Build a ~500KB version
chia-scan build-synthetic \
    -i ./data/generators/top-generators \
    -o ./data/synthetic_500K.bin \
    --target-size 500K \
    --max-atom-size 1000

# See statistics without writing
chia-scan build-synthetic \
    -i ./data/generators/top-generators \
    --stats-only
```

The `--max-atom-size 1000` filters out NFT image data, keeping only normal
puzzle/solution atoms (hashes, pubkeys, conditions).

## Step 3: Run the Analysis

### SHA256 Timing Benchmark

Determine the I/S ratio (invocation overhead vs per-block cost):

```bash
python scripts/benchmark_sha.py --iterations 10000
```

Expected output:
```
Per-block cost (S):      ~19 ns   (varies by hardware)
Invocation overhead (I): ~150 ns
I/S ratio:               ~8
```

### Cost Component Analysis

Analyze generators to validate the cost formula:

```bash
# Analyze a single generator
python scripts/analyze_generators.py ./data/generators/top-generators/generator_*.bin

# Batch analysis with CSV output
python scripts/analyze_generators.py ./data/generators/top-generators \
    --batch --csv results/real_generators.csv

# Analyze synthetic generators
python scripts/analyze_generators.py ./data/synthetic_1M.bin
python scripts/analyze_generators.py ./data/synthetic_500K.bin
```

### Coefficient Sweep

Find optimal B, A, P values:

```bash
python scripts/sweep_coefficients.py ./data/generators/top-generators \
    --B-range 1 \
    --A-range 0,1,2,3 \
    --P-range 1,2,3,4,5
```

Expected result: B=1, A=2, P=2 gives average ratio ≈ 1.0

### DoS Analysis

Test adversarial structures:

```bash
python scripts/dos_test.py -v
```

Verify that:
- Structures with many small nodes cost 2x+ more (DoS protection)
- Data-heavy structures cost ~0.5x (correct, low work per byte)
- High-sharing structures cost less (correct, fewer unique nodes)

## Expected Results

### Real Generator Analysis (B=1, A=2, P=2)

| Metric | Expected |
|--------|----------|
| Min ratio | ~0.5 (data-heavy NFT blocks) |
| Avg ratio | ~1.0 |
| Max ratio | ~1.1 |

### Synthetic Generator Analysis

| Generator | Classic Size | Backref Size | Estimated Len | Ratio |
|-----------|--------------|--------------|---------------|-------|
| synthetic_1M | ~1 MB | ~245 KB | ~210 KB | ~0.86 |
| synthetic_500K | ~500 KB | ~185 KB | ~188 KB | ~1.02 |

High-sharing synthetic generators get lower costs because they have fewer unique
nodes - this is correct behavior.

### SHA256 I/S Ratio

| Hardware | Per Block | Per Invocation | I/S Ratio |
|----------|-----------|----------------|-----------|
| Apple M-series | ~19 ns | ~150 ns | ~8 |
| Intel w/ SHA-NI | ~30 ns | ~200 ns | ~7 |
| Intel 2012 (no SHA-NI) | ~520 ns | ~3400 ns | ~7 |

The ratio is consistent across hardware, justifying I=8.

## Directory Structure

After running the analysis, you should have:

```
canonical-generator-analysis/
├── data/
│   ├── generators/
│   │   ├── top-generators/      # Large blocks from mainnet
│   │   │   └── generator_*.bin
│   │   └── random-generators/   # Random sample
│   │       └── generator_*.bin
│   ├── synthetic_1M.bin         # Spend-heavy synthetic
│   └── synthetic_500K.bin
└── results/
    ├── real_generators.csv
    └── synthetic_analysis.csv
```

## Troubleshooting

### "bad encoding" errors

Some newer generators (blocks >6M height) may fail to parse with older versions
of clvm_rs. Use generators from earlier blocks, or update clvm_rs.

### Recursion depth exceeded

This was fixed in the scripts by using iterative traversal. If you see this
error, make sure you have the latest version of this repo.

### Missing blockchain database

You need a synced Chia full node. The database is typically at:
- Linux: `~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite`
- macOS: `~/.chia/mainnet/db/blockchain_v2_mainnet.sqlite`
- Windows: `%USERPROFILE%\.chia\mainnet\db\blockchain_v2_mainnet.sqlite`
