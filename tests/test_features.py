import math

import pandas as pd

import src.features.build_features as build_features


def test_payment_aggregates(client_row):
    features = build_features.build_features(pd.DataFrame([client_row])).iloc[0]
    assert features["PAY_MAX"] == 2
    assert features["PAY_DELAY_MONTHS"] == 2
    assert features["BILL_MEAN"] == 5000
    assert features["PAY_AMT_MEAN"] == 1000
    assert features["UTILIZATION"] == 0.2
    assert features["PAY_RATIO"] == 0.2


def test_pay_ratio_is_nan_without_debt(client_row):
    row = client_row | {f"BILL_AMT{i}": 0.0 for i in range(1, 7)}
    features = build_features.build_features(pd.DataFrame([row])).iloc[0]
    assert math.isnan(features["PAY_RATIO"])


def test_age_bins(client_row):
    rows = pd.DataFrame([client_row | {"AGE": age} for age in (21, 25, 26, 45, 60)])
    assert build_features.build_features(rows)["AGE_BIN"].tolist() == ["до 25", "до 25", "26-35", "36-45", "старше 55"]


def test_input_is_not_modified(client_row):
    df = pd.DataFrame([client_row])
    build_features.build_features(df)
    assert list(df.columns) == build_features.INPUT_FEATURES
