"""
Sample measurement data generators for testing.

Provides realistic S-parameter data that mimics real VNA measurements.
"""

from typing import Any

import numpy as np

DEFAULT_SAMPLE_SEED = 12345


def _seed_component(value: Any) -> int:
    """Convert a generator input into a stable 32-bit seed component."""
    if value is None:
        return 0
    if isinstance(value, str):
        total = 0
        for char in value:
            total = ((total * 131) + ord(char)) & 0xFFFFFFFF
        return total
    if isinstance(value, (bool, int, np.integer)):
        return int(value) & 0xFFFFFFFF
    if isinstance(value, (float, np.floating)):
        return int(round(float(value) * 1000)) & 0xFFFFFFFF
    if isinstance(value, np.ndarray):
        total = 0
        for item in value:
            total = ((total * 131) + _seed_component(item)) & 0xFFFFFFFF
        return total
    if isinstance(value, (tuple, list)):
        total = 0
        for item in value:
            total = ((total * 131) + _seed_component(item)) & 0xFFFFFFFF
        return total
    if isinstance(value, dict):
        total = 0
        for key in sorted(value):
            total = ((total * 131) + _seed_component(key)) & 0xFFFFFFFF
            total = ((total * 131) + _seed_component(value[key])) & 0xFFFFFFFF
        return total
    return _seed_component(str(value))


def _create_rng(
    tag: str, frequencies: np.ndarray, seed: int | None = None, *components: Any
) -> np.random.Generator:
    """Create a deterministic local RNG for one generator call."""
    resolved_seed = DEFAULT_SAMPLE_SEED if seed is None else seed
    seed_value = _seed_component(tag)
    seed_value = ((seed_value * 131) + _seed_component(resolved_seed)) & 0xFFFFFFFF
    seed_value = ((seed_value * 131) + _seed_component(frequencies)) & 0xFFFFFFFF
    for component in components:
        seed_value = ((seed_value * 131) + _seed_component(component)) & 0xFFFFFFFF
    return np.random.default_rng(seed_value)


def _split_sample_generator_kwargs(kwargs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Route generator-specific kwargs without leaking them across helpers."""
    shared_keys = {"seed"}
    shared = {key: kwargs[key] for key in shared_keys if key in kwargs}

    generator_keys = {
        "S11": {"resonance_freq", "q_factor", "return_loss_db"},
        "S21": {"insertion_loss_db", "rolloff_db_per_decade", "cutoff_freq"},
        "S12": {"insertion_loss_db", "rolloff_db_per_decade", "cutoff_freq"},
        "S22": {"resonance_freq", "q_factor", "return_loss_db"},
    }

    split_kwargs: dict[str, dict[str, Any]] = {}
    for name, allowed_keys in generator_keys.items():
        split_kwargs[name] = {
            key: value
            for key, value in kwargs.items()
            if key in allowed_keys or key in shared
        }
    return split_kwargs


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
    if sweep_type == "logarithmic":
        return np.logspace(np.log10(start_hz), np.log10(stop_hz), points)
    raise ValueError(f"Unknown sweep type: {sweep_type}")


def generate_realistic_s11(
    frequencies: np.ndarray,
    resonance_freq: float | None = None,
    q_factor: float = 50.0,
    return_loss_db: float = -15.0,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
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
        seed: Optional deterministic noise seed

    Returns:
        Tuple of (magnitude_db, phase_deg)
    """
    resolved_resonance_freq = (
        (frequencies[0] + frequencies[-1]) / 2
        if resonance_freq is None
        else resonance_freq
    )

    t = (frequencies - frequencies[0]) / (frequencies[-1] - frequencies[0])
    base_reflection_db = -10 - 15 * t

    omega = 2 * np.pi * frequencies
    omega0 = 2 * np.pi * resolved_resonance_freq
    gamma = omega0 / q_factor

    lorentzian = gamma**2 / ((omega - omega0) ** 2 + gamma**2)
    resonance_contribution_db = return_loss_db * lorentzian
    magnitude_db = base_reflection_db + resonance_contribution_db
    phase_deg = -180 * t + 90 * np.tanh(10 * (t - 0.5))

    rng = _create_rng(
        "S11", frequencies, seed, resolved_resonance_freq, q_factor, return_loss_db
    )
    magnitude_db += rng.normal(0, 0.1, len(frequencies))
    phase_deg += rng.normal(0, 0.5, len(frequencies))

    return magnitude_db, phase_deg


def generate_realistic_s21(
    frequencies: np.ndarray,
    insertion_loss_db: float = -0.5,
    rolloff_db_per_decade: float = -20.0,
    cutoff_freq: float | None = None,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
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
        seed: Optional deterministic noise seed

    Returns:
        Tuple of (magnitude_db, phase_deg)
    """
    resolved_cutoff_freq = frequencies[-1] * 0.7 if cutoff_freq is None else cutoff_freq

    normalized_ratio = np.maximum(frequencies / resolved_cutoff_freq, 1e-12)
    decades_above_cutoff = np.maximum(np.log10(normalized_ratio), 0.0)
    rolloff_shape = 10 ** (rolloff_db_per_decade * decades_above_cutoff / 20.0)

    s = 1j * 2 * np.pi * frequencies
    s0 = 1j * 2 * np.pi * resolved_cutoff_freq
    h = (1 / (1 + s / s0)) * rolloff_shape

    magnitude_db = 20 * np.log10(np.abs(h)) + insertion_loss_db
    phase_deg = np.angle(h, deg=True)

    rng = _create_rng(
        "S21",
        frequencies,
        seed,
        insertion_loss_db,
        rolloff_db_per_decade,
        cutoff_freq,
    )
    magnitude_db += rng.normal(0, 0.05, len(frequencies))
    phase_deg += rng.normal(0, 0.3, len(frequencies))

    return magnitude_db, phase_deg


def generate_realistic_s12(
    frequencies: np.ndarray,
    insertion_loss_db: float = -0.5,
    rolloff_db_per_decade: float = -20.0,
    cutoff_freq: float | None = None,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate realistic S12 (reverse transmission) data.

    For reciprocal networks, S12 ≈ S21. This generates data similar to S21
    but with slight asymmetry.

    Args:
        frequencies: Frequency array in Hz
        insertion_loss_db: Insertion loss in passband
        rolloff_db_per_decade: Rolloff rate (negative for low-pass)
        cutoff_freq: 3dB cutoff frequency
        seed: Optional deterministic noise seed

    Returns:
        Tuple of (magnitude_db, phase_deg)
    """
    mag, phase = generate_realistic_s21(
        frequencies,
        insertion_loss_db=insertion_loss_db,
        rolloff_db_per_decade=rolloff_db_per_decade,
        cutoff_freq=cutoff_freq,
        seed=seed,
    )

    rng = _create_rng(
        "S12",
        frequencies,
        seed,
        insertion_loss_db,
        rolloff_db_per_decade,
        cutoff_freq,
    )
    mag += rng.normal(0, 0.1, len(frequencies))
    phase += rng.normal(0, 2.0, len(frequencies))

    return mag, phase


def generate_realistic_s22(
    frequencies: np.ndarray,
    resonance_freq: float | None = None,
    q_factor: float = 50.0,
    return_loss_db: float = -18.0,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate realistic S22 (output reflection) data.

    S22 represents the output reflection coefficient, typically similar to S11
    but with different resonance characteristics.

    Args:
        frequencies: Frequency array in Hz
        resonance_freq: Resonance frequency (default: 60% of stop frequency)
        q_factor: Quality factor of resonance
        return_loss_db: Return loss at resonance in dB
        seed: Optional deterministic noise seed

    Returns:
        Tuple of (magnitude_db, phase_deg)
    """
    resolved_resonance_freq = (
        frequencies[-1] * 0.6 if resonance_freq is None else resonance_freq
    )

    mag, phase = generate_realistic_s11(
        frequencies,
        resonance_freq=resolved_resonance_freq,
        q_factor=q_factor,
        return_loss_db=return_loss_db,
        seed=seed,
    )
    phase -= 10
    return mag, phase


def generate_sample_sparameters(
    frequencies: np.ndarray,
    **kwargs: Any,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """
    Generate complete 2-port S-parameter dataset.

    Args:
        frequencies: Frequency array in Hz
        **kwargs: Additional parameters passed to individual generators

    Returns:
        Dictionary with S11, S21, S12, S22 as keys
        and (magnitude_db, phase_deg) tuples as values
    """
    split_kwargs = _split_sample_generator_kwargs(kwargs)
    return {
        "S11": generate_realistic_s11(frequencies, **split_kwargs["S11"]),
        "S21": generate_realistic_s21(frequencies, **split_kwargs["S21"]),
        "S12": generate_realistic_s12(frequencies, **split_kwargs["S12"]),
        "S22": generate_realistic_s22(frequencies, **split_kwargs["S22"]),
    }


def generate_matched_load(
    frequencies: np.ndarray | None = None,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """
    Generate S-parameters for a perfectly matched 50Ω load.

    Ideal characteristics:
    - S11 = S22 = -∞ dB (perfect match, no reflection)
    - S21 = S12 = 0 dB (perfect transmission)
    - All phases = 0°

    Args:
        frequencies: Optional shared frequency axis used to size the arrays

    Returns:
        Dictionary of ideal matched load S-parameters
    """
    freqs = generate_sample_frequencies() if frequencies is None else frequencies
    n = len(freqs)

    return {
        "S11": (np.full(n, -60.0), np.zeros(n)),
        "S21": (np.zeros(n), np.zeros(n)),
        "S12": (np.zeros(n), np.zeros(n)),
        "S22": (np.full(n, -60.0), np.zeros(n)),
    }


def generate_open_circuit(
    frequencies: np.ndarray | None = None,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """
    Generate S-parameters for an open circuit termination.

    Ideal characteristics:
    - S11 = S22 = 0 dB, 0° (total reflection, same phase)
    - S21 = S12 = -∞ dB (no transmission)

    Args:
        frequencies: Optional shared frequency axis used to size the arrays

    Returns:
        Dictionary of ideal open circuit S-parameters
    """
    freqs = generate_sample_frequencies() if frequencies is None else frequencies
    n = len(freqs)

    return {
        "S11": (np.zeros(n), np.zeros(n)),
        "S21": (np.full(n, -80.0), np.zeros(n)),
        "S12": (np.full(n, -80.0), np.zeros(n)),
        "S22": (np.zeros(n), np.zeros(n)),
    }


def generate_short_circuit(
    frequencies: np.ndarray | None = None,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """
    Generate S-parameters for a short circuit termination.

    Ideal characteristics:
    - S11 = S22 = 0 dB, 180° (total reflection, inverted phase)
    - S21 = S12 = -∞ dB (no transmission)

    Args:
        frequencies: Optional shared frequency axis used to size the arrays

    Returns:
        Dictionary of ideal short circuit S-parameters
    """
    freqs = generate_sample_frequencies() if frequencies is None else frequencies
    n = len(freqs)

    return {
        "S11": (np.zeros(n), np.full(n, 180.0)),
        "S21": (np.full(n, -80.0), np.zeros(n)),
        "S12": (np.full(n, -80.0), np.zeros(n)),
        "S22": (np.zeros(n), np.full(n, 180.0)),
    }
