import numpy as np
import pytest

from energy_co2 import metrics


def test_mae_rmse_basic():
    assert metrics.mae([1, 2, 3], [1, 2, 5]) == pytest.approx(2 / 3)
    assert metrics.rmse([1, 2, 3], [1, 2, 5]) == pytest.approx(np.sqrt(4 / 3))


def test_mape_ignores_zero_actuals():
    assert metrics.mape([0, 100], [10, 110]) == pytest.approx(10.0)


def test_smape_symmetric_and_bounded():
    assert metrics.smape([100], [50]) == metrics.smape([50], [100])
    assert 0 <= metrics.smape([1, 2], [3, 0]) <= 200


def test_mase_relative_to_naive():
    train = np.array([1.0, 2.0, 3.0, 4.0])      # naive in-sample MAE = 1
    assert metrics.mase([5, 6], [5, 6], train) == pytest.approx(0.0)
    assert metrics.mase([5, 6], [6, 7], train) == pytest.approx(1.0)
    assert np.isnan(metrics.mase([5], [5], np.array([1.0, 1.0])))   # масштаб 0 → NaN


def test_evaluate_returns_all_keys():
    out = metrics.evaluate([1, 2, 3], [1.1, 2.1, 2.9], y_train=[0, 1, 2], m=1)
    assert set(out) == {"MAE", "RMSE", "MAPE", "sMAPE", "MASE"}
