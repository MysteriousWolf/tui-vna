"""Tests for deterministic sample-data fixtures."""

import numpy as np
import pytest

from tests.fixtures import sample_data


class TestSampleData:
    """Validate deterministic sample-data helpers."""

    @pytest.mark.unit
    def test_realistic_generators_are_deterministic_with_same_seed(self):
        """Identical seeds should reproduce identical S-parameter traces."""
        freqs = sample_data.generate_sample_frequencies(points=51)

        first_mag, first_phase = sample_data.generate_realistic_s21(freqs, seed=7)
        second_mag, second_phase = sample_data.generate_realistic_s21(freqs, seed=7)

        np.testing.assert_allclose(first_mag, second_mag)
        np.testing.assert_allclose(first_phase, second_phase)

    @pytest.mark.unit
    def test_sample_sparameters_are_deterministic_by_default(self):
        """Default fixture generation should stay stable across repeated calls."""
        freqs = sample_data.generate_sample_frequencies(points=41)

        first = sample_data.generate_sample_sparameters(freqs)
        second = sample_data.generate_sample_sparameters(freqs)

        for key in first:
            np.testing.assert_allclose(first[key][0], second[key][0])
            np.testing.assert_allclose(first[key][1], second[key][1])

    @pytest.mark.unit
    def test_generate_sample_sparameters_routes_kwargs_per_generator(self, monkeypatch):
        """Generator-specific kwargs should be isolated to matching helpers."""
        freqs = sample_data.generate_sample_frequencies(points=11)
        received: dict[str, dict[str, object]] = {}

        def make_stub(name: str):
            def _stub(
                frequencies: np.ndarray, **kwargs: object
            ) -> tuple[np.ndarray, np.ndarray]:
                received[name] = dict(kwargs)
                values = np.zeros(len(frequencies))
                return values, values

            return _stub

        monkeypatch.setattr(sample_data, "generate_realistic_s11", make_stub("S11"))
        monkeypatch.setattr(sample_data, "generate_realistic_s21", make_stub("S21"))
        monkeypatch.setattr(sample_data, "generate_realistic_s12", make_stub("S12"))
        monkeypatch.setattr(sample_data, "generate_realistic_s22", make_stub("S22"))

        sample_data.generate_sample_sparameters(
            freqs,
            seed=5,
            resonance_freq=123.0,
            q_factor=9.0,
            insertion_loss_db=-3.0,
            rolloff_db_per_decade=-35.0,
        )

        assert received["S11"] == {"seed": 5, "resonance_freq": 123.0, "q_factor": 9.0}
        assert received["S21"] == {
            "seed": 5,
            "insertion_loss_db": -3.0,
            "rolloff_db_per_decade": -35.0,
        }
        assert received["S12"] == {
            "seed": 5,
            "insertion_loss_db": -3.0,
            "rolloff_db_per_decade": -35.0,
        }
        assert received["S22"] == {"seed": 5, "resonance_freq": 123.0, "q_factor": 9.0}

    @pytest.mark.unit
    def test_rolloff_db_per_decade_changes_s21_shape(self):
        """Steeper rolloff should reduce high-frequency transmission more strongly."""
        freqs = sample_data.generate_sample_frequencies(
            start_hz=1e6, stop_hz=1e9, points=201
        )

        mild_mag, _ = sample_data.generate_realistic_s21(
            freqs,
            seed=11,
            cutoff_freq=1e7,
            rolloff_db_per_decade=-10.0,
        )
        steep_mag, _ = sample_data.generate_realistic_s21(
            freqs,
            seed=11,
            cutoff_freq=1e7,
            rolloff_db_per_decade=-40.0,
        )

        assert steep_mag[-1] < mild_mag[-1]

    @pytest.mark.unit
    def test_logarithmic_sweep_generates_geometrically_spaced_frequencies(self):
        freqs = sample_data.generate_sample_frequencies(
            points=11,
            start_hz=100e6,
            stop_hz=1000e6,
            sweep_type="logarithmic",
        )

        # Verify frequency points are monotonically increasing
        assert np.all(np.diff(freqs) > 0)

        # Verify geometric progression (log spacing)
        ratios = freqs[1:] / freqs[:-1]
        np.testing.assert_allclose(ratios, ratios[0], rtol=1e-10)

    @pytest.mark.unit
    def test_termination_helpers_accept_shared_frequency_axis(self):
        """Termination fixtures should size outputs from a provided frequency axis."""
        freqs = sample_data.generate_sample_frequencies(points=17)

        for generator in (
            sample_data.generate_matched_load,
            sample_data.generate_open_circuit,
            sample_data.generate_short_circuit,
        ):
            sparams = generator(freqs)
            for magnitude, phase in sparams.values():
                assert len(magnitude) == len(freqs)
                assert len(phase) == len(freqs)
