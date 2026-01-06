"""
Tests for intern counting, verified against Rust clvm_rs implementation.

These test cases are derived from the Rust tests in:
  clvm_rs/src/chia/generator.rs
"""

import pytest
from clvm_rs import Program

from canon_analysis.intern import count_unique_nodes


class TestInternCountsMatchRust:
    """Verify Python counts match Rust implementation."""

    def test_empty_atom(self):
        """Rust: test_empty_atom"""
        p = Program.to(b'')
        atoms, pairs, atom_bytes = count_unique_nodes(p)
        
        assert atoms == 1
        assert pairs == 0
        assert atom_bytes == 0

    def test_simple_pair(self):
        """Rust: test_simple_pair - ([1,2,3] . [4,5,6])"""
        p = Program.to((bytes([1, 2, 3]), bytes([4, 5, 6])))
        atoms, pairs, atom_bytes = count_unique_nodes(p)
        
        assert atoms == 2
        assert pairs == 1
        assert atom_bytes == 6

    def test_shared_subtree(self):
        """Rust: test_shared_subtree - (42 . 42) with same atom"""
        p = Program.to((bytes([42]), bytes([42])))
        atoms, pairs, atom_bytes = count_unique_nodes(p)
        
        # Only 1 unique atom, even though it appears twice
        assert atoms == 1
        assert pairs == 1
        assert atom_bytes == 1

    def test_cost_components_only(self):
        """Rust: test_cost_components_only - ([1,2,3,4,5] . nil)"""
        p = Program.to((bytes([1, 2, 3, 4, 5]), b''))
        atoms, pairs, atom_bytes = count_unique_nodes(p)
        
        assert atoms == 2  # The 5-byte atom + nil
        assert pairs == 1
        assert atom_bytes == 5  # Only the non-nil atom has bytes

    def test_from_serialized_bytes(self):
        """Rust: test_from_serialized_bytes - ("hello" . "world")"""
        p = Program.to((b'hello', b'world'))
        atoms, pairs, atom_bytes = count_unique_nodes(p)
        
        assert atoms == 2
        assert pairs == 1
        assert atom_bytes == 10  # "hello" (5) + "world" (5)

    def test_estimated_len(self):
        """Rust: test_estimated_len - complex tree with sharing"""
        # Create a tree with 2 atoms (10 bytes total) and 3 pairs
        a = Program.to(bytes([1, 2, 3, 4, 5]))   # 5 bytes
        b = Program.to(bytes([6, 7, 8, 9, 10]))  # 5 bytes
        p1 = Program.to((a, b))
        p2 = Program.to((p1, a))  # shares 'a'
        p3 = Program.to((p2, b))  # shares 'b'
        
        atoms, pairs, atom_bytes = count_unique_nodes(p3)
        
        assert atoms == 2
        assert pairs == 3
        assert atom_bytes == 10

    def test_nested_sharing(self):
        """Test deeply nested sharing: ((x.x).(x.x))"""
        x = Program.to(b'x')
        inner = Program.to((x, x))
        outer = Program.to((inner, inner))
        
        atoms, pairs, atom_bytes = count_unique_nodes(outer)
        
        # 1 unique atom, 2 unique pairs (inner and outer)
        assert atoms == 1
        assert pairs == 2
        assert atom_bytes == 1


class TestInternCountsMatchRustCLI:
    """
    Verify Python counts match Rust clvm-serde CLI output.
    
    These tests require generator files to exist. They are skipped
    if the files are not found.
    """

    @pytest.fixture
    def generator_path(self):
        """Path to a real generator file."""
        import os
        path = "/Users/kiss/projects/chia/clvm_rs/intern/GENERATORS/top-400-generators/generator_0002289496_21373fabad47316a.bin"
        if not os.path.exists(path):
            pytest.skip(f"Generator file not found: {path}")
        return path

    @pytest.fixture
    def synthetic_path(self):
        """Path to synthetic generator file."""
        import os
        path = "/Users/kiss/projects/chia/clvm_rs/intern/synthetic_1M.bin"
        if not os.path.exists(path):
            pytest.skip(f"Synthetic generator not found: {path}")
        return path

    def test_real_generator_matches_rust(self, generator_path):
        """
        Compare against Rust clvm-serde output for generator_0002289496.
        
        Rust output:
          atom_count:      297
          pair_count:      3209
          atom_bytes:      414564
        """
        data = open(generator_path, 'rb').read()
        program = Program.from_bytes(data)
        atoms, pairs, atom_bytes = count_unique_nodes(program)
        
        assert atoms == 297
        assert pairs == 3209
        assert atom_bytes == 414564

    def test_synthetic_generator_matches_rust(self, synthetic_path):
        """
        Compare against Rust clvm-serde output for synthetic_1M.bin.
        
        Rust output:
          atom_count:      6219
          pair_count:      29003
          atom_bytes:      140263
        """
        data = open(synthetic_path, 'rb').read()
        program = Program.from_bytes(data)
        atoms, pairs, atom_bytes = count_unique_nodes(program)
        
        assert atoms == 6219
        assert pairs == 29003
        assert atom_bytes == 140263
