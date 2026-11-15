import numpy as np

import src.monitoring.drift as drift


def test_psi_same_distribution_is_small():
    rng = np.random.default_rng(42)
    assert drift.psi(rng.normal(size=5000), rng.normal(size=5000)) < 0.1


def test_psi_shifted_distribution_is_large():
    rng = np.random.default_rng(42)
    assert drift.psi(rng.normal(size=5000), rng.normal(loc=1, size=5000)) > 0.25


def test_psi_discrete_feature():
    expected = np.array([0] * 700 + [1] * 200 + [2] * 100)
    assert drift.psi(expected, expected) == 0


def test_psi_constant_feature_change_is_large():
    assert drift.psi(np.zeros(1000), np.ones(1000)) > 0.25


def test_psi_status():
    assert drift.psi_status(0.05) == "нет дрифта"
    assert drift.psi_status(0.2) == "умеренный дрифт"
    assert drift.psi_status(0.3) == "значительный дрифт"
