"""
Pytest configuration and shared fixtures.

Provides mocks, fixtures, and helpers for testing without hardware.
"""

import queue
from typing import Dict, Tuple
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest
import pyvisa

from src.tina.drivers.base import VNAConfig
from src.tina.worker import MessageType

# Import fixtures from our fixtures module
from tests.fixtures.mock_visa import MockResourceManager, MockVisaResource
from tests.fixtures.mock_vna import MockE5071B, MockVNA
from tests.fixtures.sample_data import (
    generate_sample_frequencies,
    generate_sample_sparameters,
)

# ===== Configuration Fixtures =====


@pytest.fixture
def vna_config():
    """Create a basic VNA configuration for testing."""
    return VNAConfig(
        host="192.168.1.100",
        port="inst0",
        start_freq_hz=10e6,
        stop_freq_hz=1000e6,
        sweep_points=201,
        set_freq_range=True,
        set_sweep_points=True,
        enable_averaging=False,
    )


# ===== VISA Mock Fixtures =====


@pytest.fixture
def mock_visa_resource():
    """Create a mock VISA resource."""
    return MockVisaResource()


@pytest.fixture
def mock_pyvisa_resource_manager(monkeypatch):
    """
    Mock pyvisa ResourceManager globally.

    This ensures no real VISA drivers are used and all resources
    are MockVisaResource instances.
    """
    mock_rm = MockResourceManager()

    def mock_resource_manager_factory(backend=None):
        return mock_rm

    monkeypatch.setattr(pyvisa, "ResourceManager", mock_resource_manager_factory)
    return mock_rm


@pytest.fixture
def patch_socket_reachable(monkeypatch):
    """
    Patch socket operations to always report host as reachable.

    This allows HP E5071B driver tests to bypass network checks.
    """

    def mock_socket_connect_ex(address):
        return 0  # Success

    mock_socket = MagicMock()
    mock_socket_instance = MagicMock()
    mock_socket_instance.connect_ex.return_value = 0
    mock_socket_instance.__enter__.return_value = mock_socket_instance
    mock_socket_instance.__exit__.return_value = None
    mock_socket.return_value = mock_socket_instance

    monkeypatch.setattr("socket.socket", mock_socket)
    return mock_socket


# ===== VNA Mock Fixtures =====


@pytest.fixture
def mock_vna(vna_config):
    """Create a mock VNA instance."""
    return MockVNA(vna_config)


@pytest.fixture
def connected_mock_vna(mock_vna):
    """Create and connect a mock VNA."""
    mock_vna.connect()
    yield mock_vna
    if mock_vna.is_connected():
        mock_vna.disconnect()


@pytest.fixture
def mock_e5071b(vna_config):
    """Create a mock HP E5071B VNA instance."""
    return MockE5071B(vna_config)


@pytest.fixture
def connected_mock_e5071b(mock_e5071b):
    """Create and connect a mock HP E5071B VNA."""
    mock_e5071b.connect()
    yield mock_e5071b
    if mock_e5071b.is_connected():
        mock_e5071b.disconnect()


# Backward compatibility aliases
@pytest.fixture
def dummy_vna(mock_vna):
    """Alias for mock_vna (backward compatibility)."""
    return mock_vna


@pytest.fixture
def connected_dummy_vna(connected_mock_vna):
    """Alias for connected_mock_vna (backward compatibility)."""
    return connected_mock_vna


@pytest.fixture
def dummy_visa_resource(mock_visa_resource):
    """Alias for mock_visa_resource (backward compatibility)."""
    return mock_visa_resource


# ===== Sample Data Fixtures =====


@pytest.fixture
def sample_frequencies():
    """Generate sample frequency data."""
    return generate_sample_frequencies(start_hz=10e6, stop_hz=1000e6, points=201)


@pytest.fixture
def sample_sparameters(sample_frequencies):
    """Generate sample S-parameter data."""
    return generate_sample_sparameters(sample_frequencies)


# ===== Worker Test Helpers =====


def consume_worker_messages_until(
    worker, target_type: MessageType, timeout: float = 2.0, max_messages: int = 20
):
    """
    Consume worker messages until target type is found.

    Helper for worker tests that need to handle progress updates
    and other intermediate messages before getting the final response.

    Args:
        worker: MeasurementWorker instance
        target_type: MessageType to wait for
        timeout: Timeout per message in seconds
        max_messages: Maximum messages to consume

    Returns:
        Message of target_type, or None if not found

    Example:
        msg = consume_worker_messages_until(worker, MessageType.CONNECTED)
        assert msg is not None
        assert msg.type == MessageType.CONNECTED
    """
    for _ in range(max_messages):
        try:
            msg = worker.get_response(timeout=timeout)
            if msg.type == target_type:
                return msg
            elif msg.type == MessageType.ERROR:
                # Return error immediately
                return msg
        except queue.Empty:
            return None
    return None


# Make helper available to tests
pytest.consume_worker_messages_until = consume_worker_messages_until
