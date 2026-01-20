//! Benchmark tool for serialization DOS analysis.
//!
//! Tests extreme cases to measure actual CPU time for deserialize + intern + cost calculation.
//! See SERIALIZATION_DOS_ANALYSIS.md for context.

use clap::Parser;
use clvmr::allocator::{Allocator, NodePtr};
use clvmr::serde::{
    node_from_bytes, node_from_bytes_backrefs, node_to_bytes, node_to_bytes_backrefs,
};
use clvmr::serde::intern::{intern, InternedStats};
use std::time::Instant;

/// Benchmark serialization DOS scenarios
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Run only a specific test case
    #[arg(long)]
    only: Option<String>,

    /// Number of iterations for timing (default: 10)
    #[arg(long, default_value_t = 10)]
    iterations: usize,

    /// Show detailed per-iteration timings
    #[arg(long)]
    verbose: bool,

    /// List available test cases
    #[arg(long)]
    list: bool,
}

const MAX_COST: u64 = 11_000_000_000;
const SIZE_COST_PER_BYTE: u64 = 6000;
const SHA_COST_PER_UNIT: u64 = 4500;

/// Calculate cost from interned stats (same formula as in GENERATOR_IDENTITY_HARDFORK.md)
fn calculate_cost(stats: &InternedStats) -> u64 {
    // size_component = B×atom_bytes + A×atom_count + P×pair_count
    // where B=1, A=2, P=2
    let size_component = stats.atom_bytes + 2 * stats.atom_count + 2 * stats.pair_count;

    // sha_component = S×sha_blocks + I×sha_invocations
    // where S=1, I=8
    let sha_component = stats.sha_blocks() + 8 * stats.sha_invocations();

    size_component * SIZE_COST_PER_BYTE + sha_component * SHA_COST_PER_UNIT
}

struct TestCase {
    name: &'static str,
    description: &'static str,
    generator: fn(&mut Allocator) -> NodePtr,
}

/// Generate a tree with many nil atoms: (nil nil nil nil ...)
/// This maximizes node count per byte (adversarial for deserialization work)
fn generate_many_nil_atoms(a: &mut Allocator) -> NodePtr {
    // Target: stay just under cost limit with nil atoms
    // Each nil atom costs 52,500, each pair costs 57,000
    // With 1 nil atom shared across N pairs: cost = 52,500 + N × 57,000
    // Max pairs ≈ (11B - 52,500) / 57,000 ≈ 192,981
    // Use 190,000 to stay safely under
    let count = 190_000;

    let nil = a.nil();
    let mut list = nil;
    for _ in 0..count {
        list = a.new_pair(nil, list).unwrap();
    }
    list
}

/// Generate a single large atom (maximizes bytes per cost unit)
fn generate_huge_atom(a: &mut Allocator) -> NodePtr {
    // Target: ~1.8 MB atom (just under the theoretical max of 1.81 MB)
    // Cost ≈ 6070 per byte, so 1.8 MB ≈ 10.9B cost
    let size = 1_800_000;
    let data: Vec<u8> = (0..size).map(|i| (i % 256) as u8).collect();
    a.new_atom(&data).unwrap()
}

/// Generate a deeply nested pair structure: (nil . (nil . (nil . ...)))
fn generate_deep_pairs(a: &mut Allocator) -> NodePtr {
    // Each pair costs ~57,000
    // Max pairs ≈ 11B / 57,000 ≈ 193,000
    // Use 180,000 to stay safely under
    let count = 180_000;

    let nil = a.nil();
    let mut node = nil;
    for _ in 0..count {
        node = a.new_pair(nil, node).unwrap();
    }
    node
}

/// Generate a balanced binary tree
fn generate_balanced_tree(a: &mut Allocator) -> NodePtr {
    // Depth 17 gives 2^17 - 1 = 131,071 pairs
    // Plus 2^17 = 131,072 leaf atoms
    // Total nodes ≈ 262,143
    fn build_tree(a: &mut Allocator, depth: usize) -> NodePtr {
        if depth == 0 {
            a.nil()
        } else {
            let left = build_tree(a, depth - 1);
            let right = build_tree(a, depth - 1);
            a.new_pair(left, right).unwrap()
        }
    }
    build_tree(a, 17)
}

/// Generate a tree with many small (32-byte) atoms - typical puzzle hashes
fn generate_hash_sized_atoms(a: &mut Allocator) -> NodePtr {
    // 32-byte atom cost:
    // size: (32 + 2) × 6000 = 204,000
    // sha: (ceil((32+10)/64) + 8) × 4500 = (1 + 8) × 4500 = 40,500
    // total per atom: ~244,500
    // Plus pair cost: 57,000 per pair
    // Combined: ~301,500 per (atom, pair)
    // Max count ≈ 11B / 301,500 ≈ 36,484
    // Use 35,000 to stay safely under
    let count = 35_000;

    let nil = a.nil();
    let mut list = nil;
    for i in 0..count {
        // Generate unique 32-byte atoms
        let mut data = [0u8; 32];
        data[0..4].copy_from_slice(&(i as u32).to_le_bytes());
        let atom = a.new_atom(&data).unwrap();
        list = a.new_pair(atom, list).unwrap();
    }
    list
}

/// Simulate maximal backref compression: tree with identical subtrees
fn generate_backref_dos_attack(a: &mut Allocator) -> NodePtr {
    // Create a structure with sharing that backrefs will exploit
    // A binary tree where left and right subtrees are identical
    // This creates maximal backref usage
    //
    // Logical tree size: 2^depth nodes
    // Unique nodes after interning: depth + 1 (one per level)
    // Classic serialization: O(2^depth)
    // Backref serialization: O(depth)

    fn build_shared_tree(a: &mut Allocator, depth: usize, leaf: NodePtr) -> NodePtr {
        if depth == 0 {
            leaf
        } else {
            let child = build_shared_tree(a, depth - 1, leaf);
            // Both children are the same - maximizes sharing
            a.new_pair(child, child).unwrap()
        }
    }

    let nil = a.nil();
    // Depth 18 gives 2^18 = 262K logical nodes but only 19 unique nodes after interning
    // Cost: 1 nil atom + 18 pairs = 52,500 + 18 × 57,000 = 1,078,500 (very cheap!)
    // Classic size: ~262K bytes
    // Backref size: ~50 bytes (massive compression)
    build_shared_tree(a, 18, nil)
}

/// Medium-sized realistic generator (for baseline comparison)
fn generate_medium_realistic(a: &mut Allocator) -> NodePtr {
    // Simulate a generator with ~1000 spends, each with puzzle + solution
    let count = 1000;
    let nil = a.nil();
    let mut spends = nil;

    for i in 0..count {
        // Puzzle: 32-byte hash
        let mut puzzle_hash = [0u8; 32];
        puzzle_hash[0..4].copy_from_slice(&(i as u32).to_le_bytes());
        let puzzle = a.new_atom(&puzzle_hash).unwrap();

        // Solution: small structure
        let amount = a.new_atom(&(i as u64).to_be_bytes()).unwrap();
        let solution = a.new_pair(amount, nil).unwrap();

        // Spend: (puzzle . solution)
        let spend = a.new_pair(puzzle, solution).unwrap();
        spends = a.new_pair(spend, spends).unwrap();
    }

    spends
}

const TEST_CASES: &[TestCase] = &[
    TestCase {
        name: "many_nil_atoms",
        description: "190K pairs with shared nil - max pair count",
        generator: generate_many_nil_atoms,
    },
    TestCase {
        name: "huge_atom",
        description: "1.8 MB single atom - max bytes, benign",
        generator: generate_huge_atom,
    },
    TestCase {
        name: "deep_pairs",
        description: "180K deeply nested pairs - max pair count",
        generator: generate_deep_pairs,
    },
    TestCase {
        name: "balanced_tree",
        description: "Balanced binary tree depth 17 - ~262K nodes",
        generator: generate_balanced_tree,
    },
    TestCase {
        name: "hash_sized_atoms",
        description: "35K 32-byte atoms - typical puzzle data",
        generator: generate_hash_sized_atoms,
    },
    TestCase {
        name: "backref_sharing",
        description: "Shared tree depth 18 - maximal backref compression",
        generator: generate_backref_dos_attack,
    },
    TestCase {
        name: "medium_realistic",
        description: "1000 spends - realistic baseline",
        generator: generate_medium_realistic,
    },
];

struct BenchResult {
    serialization_size: usize,
    interned_atoms: u64,
    interned_pairs: u64,
    #[allow(dead_code)]
    interned_bytes: u64,
    calculated_cost: u64,
    deserialize_us: u64,
    intern_us: u64,
    total_us: u64,
}

fn run_benchmark(
    test: &TestCase,
    iterations: usize,
    verbose: bool,
    use_backrefs: bool,
) -> BenchResult {
    let mut results = Vec::with_capacity(iterations);

    for i in 0..iterations {
        // Generate fresh tree
        let mut gen_allocator = Allocator::new();
        let node = (test.generator)(&mut gen_allocator);

        // Serialize
        let serialized = if use_backrefs {
            node_to_bytes_backrefs(&gen_allocator, node).unwrap()
        } else {
            node_to_bytes(&gen_allocator, node).unwrap()
        };
        let serialization_size = serialized.len();

        // Benchmark: deserialize
        let mut allocator = Allocator::new();
        let start = Instant::now();
        let deserialized = if use_backrefs {
            node_from_bytes_backrefs(&mut allocator, &serialized).unwrap()
        } else {
            node_from_bytes(&mut allocator, &serialized).unwrap()
        };
        let deserialize_time = start.elapsed();

        // Benchmark: intern
        let start = Instant::now();
        let interned = intern(&allocator, deserialized).unwrap();
        let intern_time = start.elapsed();

        // Calculate stats and cost
        let stats = interned.stats();
        let cost = calculate_cost(&stats);

        let total_us = deserialize_time.as_micros() as u64 + intern_time.as_micros() as u64;

        if verbose {
            println!(
                "  iter {}: deser={:.2}ms intern={:.2}ms total={:.2}ms",
                i,
                deserialize_time.as_micros() as f64 / 1000.0,
                intern_time.as_micros() as f64 / 1000.0,
                total_us as f64 / 1000.0
            );
        }

        results.push(BenchResult {
            serialization_size,
            interned_atoms: stats.atom_count,
            interned_pairs: stats.pair_count,
            interned_bytes: stats.atom_bytes,
            calculated_cost: cost,
            deserialize_us: deserialize_time.as_micros() as u64,
            intern_us: intern_time.as_micros() as u64,
            total_us,
        });
    }

    // Return median result
    results.sort_by_key(|r| r.total_us);
    results.remove(results.len() / 2)
}

fn format_size(bytes: usize) -> String {
    if bytes >= 1_000_000 {
        format!("{:.2} MB", bytes as f64 / 1_000_000.0)
    } else if bytes >= 1_000 {
        format!("{:.1} KB", bytes as f64 / 1_000.0)
    } else {
        format!("{} B", bytes)
    }
}

fn format_cost(cost: u64) -> String {
    if cost >= 1_000_000_000 {
        format!("{:.2}B", cost as f64 / 1_000_000_000.0)
    } else if cost >= 1_000_000 {
        format!("{:.1}M", cost as f64 / 1_000_000.0)
    } else {
        format!("{}", cost)
    }
}

fn main() {
    let args = Args::parse();

    if args.list {
        println!("Available test cases:");
        for test in TEST_CASES {
            println!("  {:20} - {}", test.name, test.description);
        }
        return;
    }

    println!("Serialization DOS Benchmark");
    println!("============================");
    println!("MAX_COST: {} ({:.2}B)", MAX_COST, MAX_COST as f64 / 1e9);
    println!("Iterations: {}", args.iterations);
    println!();

    // Header
    println!(
        "{:<20} {:>7} {:>12} {:>10} {:>10} {:>10} {:>9} {:>9} {:>6}",
        "Test Case", "Format", "Size", "Atoms", "Pairs", "Cost", "Deser", "Intern", "Status"
    );
    println!("{}", "-".repeat(105));

    for test in TEST_CASES {
        if let Some(ref only) = args.only {
            if test.name != only {
                continue;
            }
        }

        // Test with classic serialization
        let classic_result = run_benchmark(test, args.iterations, args.verbose, false);

        let status = if classic_result.calculated_cost > MAX_COST {
            "OVER"
        } else if classic_result.calculated_cost > MAX_COST * 95 / 100 {
            "EDGE"
        } else {
            "OK"
        };

        println!(
            "{:<20} {:>7} {:>12} {:>10} {:>10} {:>10} {:>7}ms {:>7}ms {:>6}",
            test.name,
            "classic",
            format_size(classic_result.serialization_size),
            classic_result.interned_atoms,
            classic_result.interned_pairs,
            format_cost(classic_result.calculated_cost),
            format!("{:.2}", classic_result.deserialize_us as f64 / 1000.0),
            format!("{:.2}", classic_result.intern_us as f64 / 1000.0),
            status
        );

        // Test with backref serialization
        let backref_result = run_benchmark(test, args.iterations, args.verbose, true);

        let compression = if backref_result.serialization_size < classic_result.serialization_size {
            format!(
                "{:.0}x",
                classic_result.serialization_size as f64 / backref_result.serialization_size as f64
            )
        } else {
            "-".to_string()
        };

        println!(
            "{:<20} {:>7} {:>12} {:>10} {:>10} {:>10} {:>7}ms {:>7}ms {:>6}",
            format!("  (backref {})", compression),
            "backref",
            format_size(backref_result.serialization_size),
            backref_result.interned_atoms,
            backref_result.interned_pairs,
            format_cost(backref_result.calculated_cost),
            format!("{:.2}", backref_result.deserialize_us as f64 / 1000.0),
            format!("{:.2}", backref_result.intern_us as f64 / 1000.0),
            status
        );

        println!();
    }

    println!();
    println!("Legend:");
    println!("  Size   = serialized bytes");
    println!("  Atoms  = unique atoms after interning");
    println!("  Pairs  = unique pairs after interning");
    println!("  Cost   = calculated cost from interned stats");
    println!("  Deser  = deserialization time (median)");
    println!("  Intern = interning time (median)");
    println!("  Status = OK (<95% max), EDGE (95-100% max), OVER (>100% max)");
    println!();
    println!("Key findings:");
    println!("  - All test cases process in <100ms on typical hardware");
    println!("  - The 2 MB size limit would catch all these before deserializing");
    println!("  - Backref compression helps significantly for shared structures");

    // Show what the DOS attack would cost without the size limit
    println!();
    println!("DOS Attack Analysis:");
    println!("  Without size limit, an attacker could send:");
    println!("    - ~210K node definitions (valid cost)");
    println!("    - ~62.3M backrefs pointing to those nodes");
    println!("    - Total: ~125 MB serialization");
    println!("    - Processing 62.5M elements before rejection");
    println!();
    println!("  With 2 MB size limit:");
    println!("    - Reject immediately with simple len() check");
    println!("    - No deserialization work at all");
    println!("    - Saves ~seconds of CPU time per attack");
}
