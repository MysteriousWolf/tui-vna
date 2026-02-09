"""
Test fixtures and mocks for tina tests.

This module provides:
- Mock VISA resources and instruments
- Dummy VNA drivers for testing without hardware
- Sample measurement data generators
- Mock networking components
"""

from .mock_visa import MockResourceManager, MockVisaResource
from .mock_vna import MockE5071B, MockVNA
from .sample_data import (
    generate_realistic_s11,
    generate_realistic_s21,
    generate_sample_frequencies,
    generate_sample_sparameters,
)

__all__ = [
    "MockVisaResource",
    "MockResourceManager",
    "MockVNA",
    "MockE5071B",
    "generate_sample_frequencies",
    "generate_sample_sparameters",
    "generate_realistic_s11",
    "generate_realistic_s21",
]
