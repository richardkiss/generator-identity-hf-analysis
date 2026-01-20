# Generator Identity Hard Fork: Analysis and Implementation

This repository contains the **analysis, tools, and documentation** for the Generator Identity Hard Fork, which transitions generator identity and cost calculation from serialization-based to content-addressable methods.

## Quick Start

1. **Read the overview** below to understand what's changing
2. **Review the technical specification**: [docs/GENERATOR_IDENTITY_HARDFORK.md](docs/GENERATOR_IDENTITY_HARDFORK.md)
3. **Reproduce the analysis**: [docs/REPRODUCE.md](docs/REPRODUCE.md)

## Overview

The Generator Identity Hard Fork makes two fundamental changes:

| Aspect | Before | After |
|--------|--------|-------|
| **Identity** | `SHA256(serialized_bytes)` | `SHA256_tree_hash(tree)` |
| **Cost basis** | Serialized length | Interned tree structure |

This decouples consensus from serialization format, enabling future compression improvements without hard forks.

## Documentation Structure

This repository provides documentation at multiple levels of detail:

### 📘 [Complete Technical Specification](docs/GENERATOR_IDENTITY_HARDFORK.md)

The main technical document covering:
- Problem statement and motivation
- Detailed cost formula derivation and justification
- DoS analysis and validation results
- Performance considerations
- Implementation details and PR structure
- Farmer changes required
- Open questions for review

**Start here** if you want to understand the complete design and rationale.

### 🔬 [Reproduction Guide](docs/REPRODUCE.md)

Step-by-step instructions to reproduce the analysis from scratch:
- Data collection (extracting generators from blockchain)
- Running all analysis scripts
- Interpreting results
- Validation checklist
- Troubleshooting

**Start here** if you want to verify the cost formula parameters yourself.

## Implementation PRs

The implementation is split across three repositories:

| PR | Repository | Branch | Description |
|----|------------|--------|-------------|
| **#1** | [clvm_rs](https://github.com/Chia-Network/clvm_rs) | `generator-identity-hf` | Core interning infrastructure (`intern()`, `InternedTree`, `InternedStats`) |
| **#2** | [chia_rs](https://github.com/Chia-Network/chia_rs) | `generator-identity-hf` | Chia-specific cost calculation and block validation |
| **#3** | [clvm_rs](https://github.com/Chia-Network/clvm_rs) | `serde_2026` | New serialization format (future work, independent) |

**Dependency order**: PR #2 requires PR #1 to be merged and released first. PR #3 is independent.

See [docs/GENERATOR_IDENTITY_HARDFORK.md](docs/GENERATOR_IDENTITY_HARDFORK.md#implementation-overview) for detailed implementation information.

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

See [docs/GENERATOR_IDENTITY_HARDFORK.md](docs/GENERATOR_IDENTITY_HARDFORK.md#the-new-cost-formula) for the complete derivation and justification.

## Installation

```bash
# Clone the repo
git clone https://github.com/richardkiss/generator-identity-hf-analysis.git
cd generator-identity-hf-analysis

# Install with uv (recommended)
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"
```

**Notes**: 
- Some newer generators (from blocks after ~6M height) may fail to parse with the PyPI version of `clvm_rs`. If you encounter "bad encoding" errors, you may need a newer version of `clvm_rs` or use the `generator-identity-hf` branch.
- To extract generators from the blockchain, install [chia-scan](https://github.com/richardkiss/chia-scan):
  ```bash
  pip install git+https://github.com/richardkiss/chia-scan.git
  # Or if you have it locally:
  cd /path/to/chia-scan && pip install -e .
  ```

## Usage

### Quick Analysis

```bash
# Analyze a single generator
python scripts/analyze_generators.py path/to/generator.bin

# SHA256 timing benchmark (determines I/S ratio)
python scripts/benchmark_sha.py

# DoS analysis (test adversarial structures)
python scripts/dos_test.py -v
```

### Batch Analysis

```bash
# Analyze multiple generators with CSV output
python scripts/analyze_generators.py ./data/generators/ \
    --batch --csv results.csv

# Coefficient sweep (find optimal B, A, P values)
python scripts/sweep_coefficients.py ./data/generators/
```

### Complete Workflow

For the complete analysis workflow, see [docs/REPRODUCE.md](docs/REPRODUCE.md).

## Project Structure

```
generator-identity-hf-analysis/
├── src/canon_analysis/      # Core library
│   ├── intern.py            # Tree interning (deduplication)
│   ├── tree_hash.py         # SHA256 tree hash
│   ├── cost_components.py   # Cost component extraction
│   └── formula.py           # Cost formula implementation
├── scripts/                  # Analysis scripts
│   ├── analyze_generators.py
│   ├── benchmark_sha.py
│   ├── dos_test.py
│   ├── sweep_coefficients.py
│   └── fetch_generators.py
├── tools/                    # Rust analysis tools
│   ├── dos-test             # Detailed DoS analysis
│   └── serialization-dos-bench
├── docs/                     # Documentation
│   ├── GENERATOR_IDENTITY_HARDFORK.md  # Complete technical spec
│   └── REPRODUCE.md                    # Step-by-step reproduction guide
└── data/                     # Generator data (gitignored)
```

## Key Findings

### SHA256 Invocation Overhead

Benchmarking shows invocation overhead is ~8× per-block cost:

| Hardware | Per Block | Per Invocation | Ratio |
|----------|-----------|----------------|-------|
| Apple M4 | 19 ns | 151 ns | 7.9× |
| Intel 2012 | 520 ns | 3,465 ns | 6.7× |

This justifies `I=8` in the formula. See [docs/GENERATOR_IDENTITY_HARDFORK.md](docs/GENERATOR_IDENTITY_HARDFORK.md#why-sha-invocation-cost-matters) for details.

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

See [docs/GENERATOR_IDENTITY_HARDFORK.md](docs/GENERATOR_IDENTITY_HARDFORK.md#dos-analysis-and-validation) for complete DoS analysis results.

## License

Apache-2.0
