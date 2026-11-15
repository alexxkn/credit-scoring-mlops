import pytest

import src.data.validation as validation


def test_raw_data_passes_validation(raw_data):
    assert validation.validate(raw_data).success


@pytest.mark.parametrize(
    "column, value",
    [("LIMIT_BAL", None), ("LIMIT_BAL", -1000), ("AGE", 150), ("SEX", 3), ("EDUCATION", 9), ("PAY_0", 12), ("PAY_AMT1", -1), ("default.payment.next.month", 2)],
)
def test_anomalies_fail_validation(raw_data, column, value):
    raw_data[column] = raw_data[column].astype(float)
    raw_data.loc[0, column] = value
    assert not validation.validate(raw_data).success


def test_missing_column_fails_validation(raw_data):
    assert not validation.validate(raw_data.drop(columns=["AGE"])).success


def test_wrong_type_fails_validation(raw_data):
    raw_data["LIMIT_BAL"] = raw_data["LIMIT_BAL"].astype(str)
    assert not validation.validate(raw_data).success


def test_duplicate_id_fails_validation(raw_data):
    raw_data.loc[1, "ID"] = raw_data.loc[0, "ID"]
    assert not validation.validate(raw_data).success
