# Canonical Generator Analysis

Analysis tools for deriving and validating the cost formula constants used in the
**Canonicalized Generators** hard fork.

## Background

The Canonicalized Generators hard fork changes how generator identity and cost are computed:

| Aspect | Before | After |
|--------|--------|-------|
| **Identity** | `SHA256(serialized_bytes)` | `SHA256_tree_hash(tree)` |
| **Cost basis** | Serialized length | Interned tree structure |

This makes consensus independent of serialization format, enabling future compression
improvements without hard forks.

## The Cost Formula

```
size_component = B×atom_bytes + A×atom_count + P×pair_count
sha_component  = S×sha_blocks + I×sha_invocations

total_cost = size_component × SIZE_COST_PER_BYTE 
           + sha_component × SHA_COST_PER_UNIT
```

**Constants** (derived from analysis in this repo):
| Constant | Value | Purpose |
|----------|-------|---------|
| B | 1 | Per byte of atom data |
| A | 2 | Per-atom overhead |
| P | 2 | Per-pair overhead |
| S | 1 | Per SHA256 block (64 bytes) |
| I | 8 | Per SHA256 invocation |
| SIZE_COST_PER_BYTE | 6000 | Size component multiplier |
| SHA_COST_PER_UNIT | 4500 | SHA component multiplier |

## Installation

```bash
# Clone the repo
git clone https://github.com/Chia-Network/canonical-generator-analysis.git
cd canonical-generator-analysis

# Install with uv (recommended)
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"
```

**Note**: Some newer generators (from blocks after ~6M height) may fail to parse
with the PyPI version of clvm_rs. If you encounter "bad encoding" errors, you may
need a newer version of clvm_rs.

## Usage

### Analyze a Single Generator

```bash
python scripts/analyze_generators.py path/to/generator.bin
```

### Batch Analysis

```bash
python scripts/analyze_generators.py ./data/generators/ --batch --csv results.csv
```

### SHA256 Timing Benchmark

Determines the I/S ratio (invocation overhead vs per-block cost):

```bash
python scripts/benchmark_sha.py
```

### DoS Analysis

Tests cost formula against adversarial structures:

```bash
python scripts/dos_test.py
```

### Fetch Mainnet Generators

Download real generators for analysis (requires running Chia node):

```bash
python scripts/fetch_generators.py --count 500 --output data/generators/
```

## Project Structure

```
canonical-generator-analysis/
├── src/canon_analysis/      # Core library
│   ├── intern.py            # Tree interning (deduplication)
│   ├── tree_hash.py         # SHA256 tree hash
│   ├── cost_components.py   # Cost component extraction
│   └── formula.py           # Cost formula implementation
├── scripts/                 # Analysis scripts
│   ├── analyze_generators.py
│   ├── benchmark_sha.py
│   ├── dos_test.py
│   └── fetch_generators.py
├── data/                    # Generator data (gitignored)
└── docs/                    # Analysis documentation
```

## Key Findings

### SHA256 Invocation Overhead

Benchmarking shows invocation overhead is ~8× per-block cost:

| Hardware | Per Block | Per Invocation | Ratio |
|----------|-----------|----------------|-------|
| Apple M4 | 19 ns | 151 ns | 7.9× |
| Intel 2012 | 520 ns | 3,465 ns | 6.7× |

This justifies `I=8` in the formula.

### Real Generator Validation

Tested against 509 real mainnet generators:
- Average cost ratio (new/old): **0.99**
- Range: 0.61 - 1.13
- Large generators (>100KB): consistently 0.9-1.05

### Synthetic Spend-Heavy Validation

Built synthetic generators with 1000+ spends:
- Cost ratio: **0.86 - 1.02**
- High-sharing structures correctly get lower costs

### DoS Protection

All adversarial structures cost **2x+ more** than under the old formula:
- `million_nil_atoms`: 2.37×
- `deep_nesting`: 2.37×
- `many_small_pairs`: 2.25×

## License

Apache-2.0
