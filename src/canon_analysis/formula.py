"""
Cost formula implementation for Canonicalized Generators.

The blended formula:
    size_component = B×atom_bytes + A×atom_count + P×pair_count
    sha_component  = S×sha_blocks + I×sha_invocations
    
    total_cost = size_component × SIZE_COST_PER_BYTE 
               + sha_component × SHA_COST_PER_UNIT

This protects against two DoS vectors:
1. Memory/Storage DoS (size component)
2. CPU/Hashing DoS (SHA component)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from canon_analysis.cost_components import CostComponents


@dataclass
class CostCoefficients:
    """Coefficients for the cost formula."""

    # Size component coefficients
    B: int = 1  # Per atom byte
    A: int = 2  # Per atom overhead
    P: int = 2  # Per pair overhead

    # SHA component coefficients
    S: int = 1  # Per SHA256 block
    I: int = 8  # Per SHA256 invocation

    # Multipliers
    size_cost_per_byte: int = 6000  # Half of old COST_PER_BYTE
    sha_cost_per_unit: int = 4500  # Fitted to match old costs

    # Old formula for comparison
    old_cost_per_byte: int = 12000


# Default coefficients derived from analysis
DEFAULT_COEFFICIENTS = CostCoefficients()


@dataclass
class CostBreakdown:
    """Detailed breakdown of cost calculation."""

    # Raw components
    components: CostComponents

    # Intermediate values
    size_component: int  # B×atom_bytes + A×atom_count + P×pair_count
    sha_component: int  # S×sha_blocks + I×sha_invocations

    # Final costs
    size_cost: int  # size_component × SIZE_COST_PER_BYTE
    sha_cost: int  # sha_component × SHA_COST_PER_UNIT
    total_cost: int  # size_cost + sha_cost

    # For comparison
    estimated_length: int  # Legacy: atom_bytes + A×atom_count + P×pair_count
    old_cost: Optional[int] = None  # serialized_len × old_cost_per_byte

    @property
    def size_fraction(self) -> float:
        """Fraction of total cost from size component."""
        if self.total_cost == 0:
            return 0.0
        return self.size_cost / self.total_cost

    @property
    def sha_fraction(self) -> float:
        """Fraction of total cost from SHA component."""
        if self.total_cost == 0:
            return 0.0
        return self.sha_cost / self.total_cost

    @property
    def cost_ratio(self) -> Optional[float]:
        """Ratio of new cost to old cost (if old_cost is set)."""
        if self.old_cost is None or self.old_cost == 0:
            return None
        return self.total_cost / self.old_cost


def calculate_estimated_length(
    components: CostComponents,
    coeffs: CostCoefficients = DEFAULT_COEFFICIENTS,
) -> int:
    """
    Calculate estimated length (legacy formula without SHA component).

    This is: B×atom_bytes + A×atom_count + P×pair_count

    Useful for comparing against serialized length.
    """
    return (
        coeffs.B * components.atom_bytes
        + coeffs.A * components.atom_count
        + coeffs.P * components.pair_count
    )


def calculate_cost(
    components: CostComponents,
    coeffs: CostCoefficients = DEFAULT_COEFFICIENTS,
    serialized_len: Optional[int] = None,
) -> CostBreakdown:
    """
    Calculate the full cost using the blended formula.

    Args:
        components: Cost components from an interned generator
        coeffs: Coefficients to use (default: derived from analysis)
        serialized_len: If provided, also calculates old cost for comparison

    Returns:
        CostBreakdown with all intermediate and final values
    """
    # Size component
    size_component = (
        coeffs.B * components.atom_bytes
        + coeffs.A * components.atom_count
        + coeffs.P * components.pair_count
    )

    # SHA component
    sha_component = coeffs.S * components.sha_blocks + coeffs.I * components.sha_invocations

    # Final costs
    size_cost = size_component * coeffs.size_cost_per_byte
    sha_cost = sha_component * coeffs.sha_cost_per_unit
    total_cost = size_cost + sha_cost

    # Legacy estimated length (for comparison)
    estimated_length = calculate_estimated_length(components, coeffs)

    # Old cost if serialized length provided
    old_cost = None
    if serialized_len is not None:
        old_cost = serialized_len * coeffs.old_cost_per_byte

    return CostBreakdown(
        components=components,
        size_component=size_component,
        sha_component=sha_component,
        size_cost=size_cost,
        sha_cost=sha_cost,
        total_cost=total_cost,
        estimated_length=estimated_length,
        old_cost=old_cost,
    )


def compare_formulas(
    components: CostComponents,
    serialized_len: int,
    coeffs: CostCoefficients = DEFAULT_COEFFICIENTS,
) -> dict:
    """
    Compare old vs new cost formulas.

    Returns a dict with comparison metrics.
    """
    breakdown = calculate_cost(components, coeffs, serialized_len)

    return {
        "serialized_len": serialized_len,
        "estimated_len": breakdown.estimated_length,
        "old_cost": breakdown.old_cost,
        "new_cost": breakdown.total_cost,
        "cost_ratio": breakdown.cost_ratio,
        "size_fraction": breakdown.size_fraction,
        "sha_fraction": breakdown.sha_fraction,
        "atom_bytes": components.atom_bytes,
        "atom_count": components.atom_count,
        "pair_count": components.pair_count,
        "sha_blocks": components.sha_blocks,
        "sha_invocations": components.sha_invocations,
    }
