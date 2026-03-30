"""
Tests for the DistortionTool Legendre polynomial decomposition.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.tina.tools.distortion import (
    _PP_RANGES,
    COMPONENT_NAMES,
    MAX_ORDER,
    DistortionTool,
    _legendre_pp_range,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_sparams(freqs: np.ndarray, mag_db: np.ndarray) -> dict:
    """
    Create a minimal S-parameters dictionary containing S21 magnitude and a zero phase array.

    Parameters:
        freqs (np.ndarray): Frequency values (not used by this helper; present for API compatibility).
        mag_db (np.ndarray): S21 magnitude values in dB.

    Returns:
        dict: A dictionary with key "S21" mapping to a tuple (magnitude_array, phase_array),
              where `phase_array` is an array of zeros with the same shape as `mag_db`.
    """
    phase = np.zeros_like(mag_db)
    return {"S21": (mag_db, phase)}


@pytest.fixture
def flat_band():
    """
    Create a flat 0 dB S21 response over a 100 MHz band centered at 1.0 GHz.

    Returns:
        tuple: (freqs, sparams) where
            freqs (ndarray): Frequency array in Hz (201 points from 0.9e9 to 1.1e9).
            sparams (dict): Minimal S-parameter dictionary containing 'S21' with magnitudes all 0 dB and phases all zeros matching `freqs`.
    """
    freqs = np.linspace(0.9e9, 1.1e9, 201)
    mag = np.zeros(201)
    return freqs, _make_sparams(freqs, mag)


@pytest.fixture
def linear_band():
    """
    Generate a synthetic S-parameter input representing a linear magnitude tilt across the band.

    Frequencies span 0.9 GHz to 1.1 GHz (201 points); magnitude is a linear ramp from -0.5 dB to +0.5 dB (equivalently 1 dB per 100 MHz). Phase values are all zero.

    Returns:
        freqs (ndarray): Frequency array in Hz.
        sparams (dict): Minimal S-parameter dictionary containing only 'S21' with keys 'mag_db' (dB) and 'phase_deg' (degrees).
    """
    freqs = np.linspace(0.9e9, 1.1e9, 201)
    # 1 dB tilt across the 200 MHz band; c1 = 0.5 dB (half the peak-to-peak / PP_range)
    mag = np.linspace(-0.5, 0.5, 201)
    return freqs, _make_sparams(freqs, mag)


@pytest.fixture
def parabolic_band():
    """
    Create a synthetic S21 dataset representing a pure parabolic (Legendre P₂) magnitude response across 0.9–1.1 GHz.

    The magnitude follows P₂(x) = (3*x**2 - 1)/2 where x is the frequency normalized to the band center and half-bandwidth (so x in [-1, 1]).

    Returns:
        tuple: (freqs, sparams) where
            freqs (ndarray): Frequencies in Hz (linspace from 0.9e9 to 1.1e9, 201 points).
            sparams (dict): Minimal S-parameter dictionary produced by _make_sparams with 'S21' magnitude set to P₂(x) and phase set to zero.
    """
    freqs = np.linspace(0.9e9, 1.1e9, 201)
    f0 = (freqs[0] + freqs[-1]) / 2
    half_bw = (freqs[-1] - freqs[0]) / 2
    x = (freqs - f0) / half_bw
    # c2 = 1.0 → y(x) = P₂(x) = (3x²-1)/2
    mag = (3 * x**2 - 1) / 2
    return freqs, _make_sparams(freqs, mag)


# ---------------------------------------------------------------------------
# _legendre_pp_range
# ---------------------------------------------------------------------------


class TestLegendreRange:
    """Peak-to-peak range of individual Legendre polynomials."""

    @pytest.mark.unit
    def test_p0_range_is_zero(self):
        """P₀(x) = 1 everywhere — range is 0."""
        assert _legendre_pp_range(0) == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.unit
    def test_p1_range_is_two(self):
        """P₁(x) = x, range [−1, 1] → 2."""
        assert _legendre_pp_range(1) == pytest.approx(2.0, rel=1e-3)

    @pytest.mark.unit
    def test_p2_range(self):
        """P₂(x) = (3x²−1)/2; min=−½, max=1 → range = 3/2."""
        assert _legendre_pp_range(2) == pytest.approx(1.5, rel=1e-3)

    @pytest.mark.unit
    def test_p3_range_is_two(self):
        """P₃ global extrema at x=±1 with values ±1 → range = 2."""
        assert _legendre_pp_range(3) == pytest.approx(2.0, rel=1e-3)

    @pytest.mark.unit
    def test_p4_range(self):
        """P₄ min ≈ −3/7 at interior, max = 1 at edges → range ≈ 10/7."""
        assert _legendre_pp_range(4) == pytest.approx(10 / 7, rel=1e-3)

    @pytest.mark.unit
    def test_p5_range_is_two(self):
        """P₅ global extrema at x=±1 with values ±1 → range = 2."""
        assert _legendre_pp_range(5) == pytest.approx(2.0, rel=1e-3)

    @pytest.mark.unit
    def test_precomputed_ranges_match(self):
        """Module-level _PP_RANGES must equal freshly computed values."""
        for n in range(MAX_ORDER + 1):
            assert _PP_RANGES[n] == pytest.approx(_legendre_pp_range(n), rel=1e-6)


# ---------------------------------------------------------------------------
# DistortionTool.compute — invalid / missing inputs
# ---------------------------------------------------------------------------


class TestDistortionToolInvalidInputs:
    @pytest.mark.unit
    def test_missing_cursor1_returns_empty(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", None, 1.0e9
        )
        assert not result.extra

    @pytest.mark.unit
    def test_missing_cursor2_returns_empty(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, None
        )
        assert not result.extra

    @pytest.mark.unit
    def test_unknown_trace_returns_empty(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S99", "magnitude", 0.9e9, 1.1e9
        )
        assert not result.extra

    @pytest.mark.unit
    def test_too_few_band_points_returns_empty(self, flat_band):
        """Band so narrow it contains fewer than MAX_ORDER+2 points."""
        freqs, sparams = flat_band
        # Band spans only 1 MHz inside a 200-point 200 MHz array → ~1 point
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 1.0e9, 1.0005e9
        )
        assert not result.extra

    @pytest.mark.unit
    def test_cursor_order_does_not_matter(self, flat_band):
        """Swapping cursor1/cursor2 gives the same result."""
        freqs, sparams = flat_band
        r1 = DistortionTool().compute(freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9)
        r2 = DistortionTool().compute(freqs, sparams, "S21", "magnitude", 1.1e9, 0.9e9)
        assert r1.extra["coeffs"] == pytest.approx(r2.extra["coeffs"], rel=1e-6)


# ---------------------------------------------------------------------------
# DistortionTool.compute — correct extra structure
# ---------------------------------------------------------------------------


class TestDistortionToolExtraStructure:
    @pytest.mark.unit
    def test_extra_keys_present(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        for key in (
            "coeffs",
            "delta_y",
            "f0_hz",
            "bandwidth_hz",
            "f_band_hz",
            "y_band",
            "x_norm",
        ):
            assert key in result.extra, f"Missing key: {key}"

    @pytest.mark.unit
    def test_coeffs_length(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        assert len(result.extra["coeffs"]) == MAX_ORDER + 1

    @pytest.mark.unit
    def test_delta_y_length(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        assert len(result.extra["delta_y"]) == MAX_ORDER + 1

    @pytest.mark.unit
    def test_delta_y0_is_zero(self, linear_band):
        """Constant component always has Δy₀ = 0."""
        freqs, sparams = linear_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        assert result.extra["delta_y"][0] == 0.0

    @pytest.mark.unit
    def test_x_norm_bounds(self, flat_band):
        """Normalised frequencies must lie in [−1, 1]."""
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        x = result.extra["x_norm"]
        assert min(x) >= -1.0 - 1e-9
        assert max(x) <= 1.0 + 1e-9

    @pytest.mark.unit
    def test_bandwidth_and_center(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        assert result.extra["f0_hz"] == pytest.approx(1.0e9, rel=1e-6)
        assert result.extra["bandwidth_hz"] == pytest.approx(0.2e9, rel=1e-6)

    @pytest.mark.unit
    def test_unit_label_magnitude(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        assert result.unit_label == "dB"

    @pytest.mark.unit
    def test_unit_label_phase(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(freqs, sparams, "S21", "phase", 0.9e9, 1.1e9)
        assert result.unit_label == "°"


# ---------------------------------------------------------------------------
# DistortionTool.compute — coefficient accuracy
# ---------------------------------------------------------------------------


class TestDistortionToolCoefficients:
    @pytest.mark.unit
    def test_flat_response_only_c0_nonzero(self, flat_band):
        """A flat 0 dB response should have c₀ ≈ 0 and all higher coefficients ≈ 0."""
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        coeffs = result.extra["coeffs"]
        assert coeffs[0] == pytest.approx(0.0, abs=1e-6)
        for n in range(1, MAX_ORDER + 1):
            assert coeffs[n] == pytest.approx(0.0, abs=1e-4), f"c{n} should be ~0"

    @pytest.mark.unit
    def test_flat_response_all_delta_y_zero(self, flat_band):
        freqs, sparams = flat_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        for n, dy in enumerate(result.extra["delta_y"]):
            assert dy == pytest.approx(0.0, abs=1e-4), f"Δy{n} should be ~0"

    @pytest.mark.unit
    def test_linear_response_recovers_c1(self, linear_band):
        """A linear tilt should give c₁ = 0.5 and all other higher-order coefficients ≈ 0."""
        freqs, sparams = linear_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        coeffs = result.extra["coeffs"]
        # y = x → c₁ = 0.5... wait, legendre: legfit([...x...], x, deg) should give c1=1
        # Actually y = x (goes from -0.5 to 0.5), x_norm goes from ~-1 to ~1
        # legfit fitting x_norm to y_band where y_band ≈ x_norm/2? No:
        # y = np.linspace(-0.5, 0.5, 201), x_norm = np.linspace(-1, 1, 201)
        # y ≈ 0.5 * x_norm → c1 = 0.5
        assert coeffs[1] == pytest.approx(0.5, rel=1e-3)
        for n in [2, 3, 4, 5]:
            assert abs(coeffs[n]) < 1e-3, f"c{n} should be ~0 for linear input"

    @pytest.mark.unit
    def test_linear_response_delta_y1(self, linear_band):
        """Δy₁ = 2|c₁| = 2 × 0.5 = 1.0 for the linear fixture."""
        freqs, sparams = linear_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        assert result.extra["delta_y"][1] == pytest.approx(1.0, rel=1e-3)

    @pytest.mark.unit
    def test_parabolic_response_recovers_c2(self, parabolic_band):
        """A pure P₂ input should recover c₂ ≈ 1 and all other orders ≈ 0."""
        freqs, sparams = parabolic_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        coeffs = result.extra["coeffs"]
        assert coeffs[2] == pytest.approx(1.0, rel=1e-3)
        for n in [1, 3, 4, 5]:
            assert abs(coeffs[n]) < 1e-3, f"c{n} should be ~0 for parabolic input"

    @pytest.mark.unit
    def test_parabolic_response_delta_y2(self, parabolic_band):
        """Δy₂ = 3/2 × |c₂| = 1.5 for a unit parabolic response."""
        freqs, sparams = parabolic_band
        result = DistortionTool().compute(
            freqs, sparams, "S21", "magnitude", 0.9e9, 1.1e9
        )
        assert result.extra["delta_y"][2] == pytest.approx(1.5, rel=1e-3)

    @pytest.mark.unit
    def test_orthogonality_independence(self):
        """Adding a linear tilt to a parabolic response should not change c₂."""
        freqs = np.linspace(0.9e9, 1.1e9, 201)
        f0 = (freqs[0] + freqs[-1]) / 2
        half_bw = (freqs[-1] - freqs[0]) / 2
        x = (freqs - f0) / half_bw
        # Pure parabolic
        mag_para = (3 * x**2 - 1) / 2
        # Parabolic + linear tilt
        mag_mixed = mag_para + 0.3 * x
        sparams_para = _make_sparams(freqs, mag_para)
        sparams_mixed = _make_sparams(freqs, mag_mixed)
        tool = DistortionTool()
        r_para = tool.compute(freqs, sparams_para, "S21", "magnitude", 0.9e9, 1.1e9)
        r_mixed = tool.compute(freqs, sparams_mixed, "S21", "magnitude", 0.9e9, 1.1e9)
        # c₂ must be the same regardless of the added linear term (Legendre orthogonality)
        assert r_para.extra["coeffs"][2] == pytest.approx(
            r_mixed.extra["coeffs"][2], rel=1e-6
        )


# ---------------------------------------------------------------------------
# COMPONENT_NAMES
# ---------------------------------------------------------------------------


class TestComponentNames:
    @pytest.mark.unit
    def test_length(self):
        assert len(COMPONENT_NAMES) == MAX_ORDER + 1

    @pytest.mark.unit
    def test_expected_names(self):
        assert COMPONENT_NAMES[0] == "Constant"
        assert COMPONENT_NAMES[1] == "Linear"
        assert COMPONENT_NAMES[2] == "Parabolic"
        assert COMPONENT_NAMES[3] == "Cubic"
        assert COMPONENT_NAMES[4] == "Quartic"
        assert COMPONENT_NAMES[5] == "Quintic"
