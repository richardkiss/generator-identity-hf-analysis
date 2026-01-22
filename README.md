# Generator Identity Hard Fork: Analysis and Implementation

This repository contains the **analysis, tools, and documentation** for the Generator Identity Hard Fork, which transitions generator identity and cost calculation from serialization-based to content-addressable methods.

## Overview

The Generator Identity Hard Fork makes two fundamental changes:

| Aspect | Before | After |
|--------|--------|-------|
| **Identity** | `SHA256(serialized_bytes)` | `SHA256_tree_hash(tree)` |
| **Cost basis** | Serialized length | Interned tree structure |

This decouples consensus from serialization format, enabling future compression improvements without hard forks.

## Documentation

| Document | Description |
|----------|-------------|
| **[Technical Specification](docs/GENERATOR_IDENTITY_HARDFORK.md)** | Complete design: problem statement, cost formula derivation, DoS analysis, implementation details |
| **[Analysis Workflow](docs/ANALYSIS_WORKFLOW.md)** | Step-by-step instructions to run the analysis from scratch |
| **[Serialization DOS Analysis](docs/SERIALIZATION_DOS_ANALYSIS.md)** | Analysis of peer protocol DOS vulnerability in generator deserialization and mitigation strategy |
| **[Generator as Witness Proposal](docs/GENERATOR_AS_WITNESS_PROPOSAL.md)** | Alternative approach: treat generator as pure witness, don't commit to it at all (future consideration) |

## Implementation PRs

| PR | Repository | Branch | Description |
|----|------------|--------|-------------|
| **#1** | [clvm_rs](https://github.com/Chia-Network/clvm_rs) | `generator-identity-hf` | Core interning infrastructure |
| **#2** | [chia_rs](https://github.com/Chia-Network/chia_rs) | `generator-identity-hf` | Chia-specific cost calculation |
| **#3** | [clvm_rs](https://github.com/Chia-Network/clvm_rs) | `serde_2026` | New serialization format (future work) |

PR #2 depends on PR #1. PR #3 is independent.

## Installation

```bash
git clone https://github.com/richardkiss/generator-identity-hf-analysis.git
cd generator-identity-hf-analysis
pip install -e ".[dev]"
```

To extract generators from the blockchain, also install [chia-scan](https://github.com/richardkiss/chia-scan).

## Quick Usage

```bash
# Analyze generators
analyze-generators path/to/generator.bin
analyze-generators ./data/generators/ --batch --csv results.csv

# Run benchmarks
benchmark-sha              # SHA256 timing (determines I/S ratio)
dos-test -v                # Test adversarial structures
sweep-coefficients ./data/generators/
```

See [docs/ANALYSIS_WORKFLOW.md](docs/ANALYSIS_WORKFLOW.md) for the complete workflow.

## License

Apache-2.0
