"""
Sample measurement data generators for testing.

Provides realistic S-parameter data that mimics real VNA measurements.
"""

from typing import Dict, Tuple

import numpy as np


def generate_sample_frequencies(
    start_hz: float = 10e6,
    stop_hz: float = 1000e6,
    points: int = 201,
    sweep_type: str = "linear",
) -> np.ndarray:
    """
    Generate sample frequency array.

    Args:
        start_hz: Start frequency in Hz
        stop_hz: Stop frequency in Hz
        points: Number of frequency points
        sweep_type: 'linear' or 'logarithmic'

    Returns:
        Numpy array of frequencies in Hz
    """
    if sweep_type == "linear":
        return np.linspace(start_hz, stop_hz, points)
    elif sweep_type == "logarithmic":
        return np.logspace(np.log10(start_hz), np.log10(stop_hz), points)
    else:
        raise ValueError(f"Unknown sweep type: {sweep_type}")


def generate_realistic_s11(
    frequencies: np.ndarray,
    resonance_freq: float = None,
    q_factor: float = 50.0,
    return_loss_db: float = -15.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate realistic S11 (reflection) data with resonance features.

    S11 represents the input reflection coefficient, typically showing:
    - Resonance dips at specific frequencies
    - Overall decreasing reflection at higher frequencies
    - Phase rotation

    Args:
        frequencies: Frequency array in Hz
        resonance_freq: Resonance frequency (default: middle of range)
        q_factor: Quality factor of resonance
        return_loss_db: Return loss at resonance in dB

    Returns:
        Tuple of (magnitude_db, phase_deg)
    """
    if resonance_freq is None:
        resonance_freq = (frequencies[0] + frequencies[-1]) / 2

    # Normalize frequency
    t = (frequencies - frequencies[0]) / (frequencies[-1] - frequencies[0])

    # Base reflection (decreases with frequency)
    base_reflection_db = -10 - 15 * t

    # Add resonance feature (Lorentzian)
    omega = 2 * np.pi * frequencies
    omega0 = 2 * np.pi * resonance_freq
    gamma = omega0 / q_factor

    lorentzian = gamma**2 / ((omega - omega0) ** 2 + gamma**2)
    resonance_contribution_db = return_loss_db * lorentzian

    # Combine
    magnitude_db = base_reflection_db + resonance_contribution_db

    # Phase: rotates through resonance
    phase_deg = -180 * t + 90 * np.tanh(10 * (t - 0.5))

    # Add some realistic noise
    magnitude_db += np.random.normal(0, 0.1, len(frequencies))
    phase_deg += np.random.normal(0, 0.5, len(frequencies))

    return magnitude_db, phase_deg


def generate_realistic_s21(
    frequencies: np.ndarray,
    insertion_loss_db: float = -0.5,
    rolloff_db_per_decade: float = -20.0,
    cutoff_freq: float = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate realistic S21 (forward transmission) data.

    S21 represents the forward transmission coefficient, typically showing:
    - Low insertion loss at low frequencies
    - Rolloff at higher frequencies (low-pass characteristic)
    - Smooth phase transition

    Args:
        frequencies: Frequency array in Hz
        insertion_loss_db: Insertion loss in passband
        rolloff_db_per_decade: Rolloff rate (negative for low-pass)
        cutoff_freq: 3dB cutoff frequency (default: 70% of stop freq)

    Returns:
        Tuple of (magnitude_db, phase_deg)
    """
    if cutoff_freq is None:
        cutoff_freq = frequencies[-1] * 0.7

    # Normalize frequency
    t = frequencies / frequencies[-1]

    # Low-pass filter response
    s = 1j * 2 * np.pi * frequencies
    s0 = 1j * 2 * np.pi * cutoff_freq
    H = 1 / (1 + s / s0)

    # Convert to dB and phase
    magnitude_db = 20 * np.log10(np.abs(H)) + insertion_loss_db
    phase_deg = np.angle(H, deg=True)

    # Add realistic noise
    magnitude_db += np.random.normal(0, 0.05, len(frequencies))
    phase_deg += np.random.normal(0, 0.3, len(frequencies))

    return magnitude_db, phase_deg


def generate_realistic_s12(
    frequencies: np.ndarray,
    **kwargs,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate realistic S12 (reverse transmission) data.

    For reciprocal networks, S12 ≈ S21. This generates data similar to S21
    but with slight asymmetry.

    Args:
        frequencies: Frequency array in Hz
        **kwargs: Passed to generate_realistic_s21

    Returns:
        Tuple of (magnitude_db, phase_deg)
    """
    # Generate base S21-like response
    mag, phase = generate_realistic_s21(frequencies, **kwargs)

    # Add slight asymmetry
    mag += np.random.normal(0, 0.1, len(frequencies))
    phase += np.random.normal(0, 2.0, len(frequencies))

    return mag, phase


def generate_realistic_s22(
    frequencies: np.ndarray,
    **kwargs,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate realistic S22 (output reflection) data.

    S22 represents the output reflection coefficient, typically similar to S11
    but with different resonance characteristics.

    Args:
        frequencies: Frequency array in Hz
        **kwargs: Passed to generate_realistic_s11

    Returns:
        Tuple of (magnitude_db, phase_deg)
    """
    # Generate base S11-like response with different parameters
    if "resonance_freq" not in kwargs:
        kwargs["resonance_freq"] = frequencies[-1] * 0.6
    if "return_loss_db" not in kwargs:
        kwargs["return_loss_db"] = -18.0

    mag, phase = generate_realistic_s11(frequencies, **kwargs)

    # Offset phase slightly
    phase -= 10

    return mag, phase


def generate_sample_sparameters(
    frequencies: np.ndarray,
    **kwargs,
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """
    Generate complete 2-port S-parameter dataset.

    Args:
        frequencies: Frequency array in Hz
        **kwargs: Additional parameters passed to individual generators

    Returns:
        Dictionary with S11, S21, S12, S22 as keys
        and (magnitude_db, phase_deg) tuples as values
    """
    return {
        "S11": generate_realistic_s11(frequencies, **kwargs),
        "S21": generate_realistic_s21(frequencies, **kwargs),
        "S12": generate_realistic_s12(frequencies, **kwargs),
        "S22": generate_realistic_s22(frequencies, **kwargs),
    }


def generate_matched_load() -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """
    Generate S-parameters for a perfectly matched 50Ω load.

    Ideal characteristics:
    - S11 = S22 = -∞ dB (perfect match, no reflection)
    - S21 = S12 = 0 dB (perfect transmission)
    - All phases = 0°

    Returns:
        Dictionary of ideal matched load S-parameters
    """
    freqs = generate_sample_frequencies()
    n = len(freqs)

    return {
        "S11": (np.full(n, -60.0), np.zeros(n)),  # Very low reflection
        "S21": (np.zeros(n), np.zeros(n)),  # Perfect transmission
        "S12": (np.zeros(n), np.zeros(n)),  # Perfect transmission
        "S22": (np.full(n, -60.0), np.zeros(n)),  # Very low reflection
    }


def generate_open_circuit() -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """
    Generate S-parameters for an open circuit termination.

    Ideal characteristics:
    - S11 = S22 = 0 dB, 0° (total reflection, same phase)
    - S21 = S12 = -∞ dB (no transmission)

    Returns:
        Dictionary of ideal open circuit S-parameters
    """
    freqs = generate_sample_frequencies()
    n = len(freqs)

    return {
        "S11": (np.zeros(n), np.zeros(n)),  # Total reflection
        "S21": (np.full(n, -80.0), np.zeros(n)),  # No transmission
        "S12": (np.full(n, -80.0), np.zeros(n)),  # No transmission
        "S22": (np.zeros(n), np.zeros(n)),  # Total reflection
    }


def generate_short_circuit() -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """
    Generate S-parameters for a short circuit termination.

    Ideal characteristics:
    - S11 = S22 = 0 dB, 180° (total reflection, inverted phase)
    - S21 = S12 = -∞ dB (no transmission)

    Returns:
        Dictionary of ideal short circuit S-parameters
    """
    freqs = generate_sample_frequencies()
    n = len(freqs)

    return {
        "S11": (np.zeros(n), np.full(n, 180.0)),  # Total reflection, inverted
        "S21": (np.full(n, -80.0), np.zeros(n)),  # No transmission
        "S12": (np.full(n, -80.0), np.zeros(n)),  # No transmission
        "S22": (np.zeros(n), np.full(n, 180.0)),  # Total reflection, inverted
    }
