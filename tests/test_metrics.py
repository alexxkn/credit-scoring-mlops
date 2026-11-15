import pytest

import src.models.metrics as metrics


def test_compute_metrics():
    y_true = [0, 0, 1, 1]
    y_proba = [0.1, 0.6, 0.4, 0.9]
    y_pred = [0, 1, 0, 1]
    result = metrics.compute_metrics(y_true, y_proba, y_pred)
    assert result["roc_auc"] == pytest.approx(0.75)
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(0.5)
    assert result["f1"] == pytest.approx(0.5)


def test_plot_roc_curve_creates_file(tmp_path):
    path = tmp_path / "roc.png"
    metrics.plot_roc_curve([0, 1, 0, 1], [0.2, 0.8, 0.3, 0.7], "test", path)
    assert path.stat().st_size > 0
