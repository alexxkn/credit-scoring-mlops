import pathlib

import pandas as pd
import pytest

RAW_PATH = pathlib.Path(__file__).parent.parent / "data" / "raw" / "UCI_Credit_Card.csv"


@pytest.fixture
def raw_data():
    return pd.read_csv(RAW_PATH)


@pytest.fixture
def client_row():
    return {
        "LIMIT_BAL": 50000.0,
        "SEX": 2,
        "EDUCATION": 2,
        "MARRIAGE": 1,
        "AGE": 30,
        "PAY_0": 2,
        "PAY_2": 1,
        "PAY_3": 0,
        "PAY_4": -1,
        "PAY_5": 0,
        "PAY_6": 0,
        "BILL_AMT1": 10000.0,
        "BILL_AMT2": 8000.0,
        "BILL_AMT3": 6000.0,
        "BILL_AMT4": 4000.0,
        "BILL_AMT5": 2000.0,
        "BILL_AMT6": 0.0,
        "PAY_AMT1": 1000.0,
        "PAY_AMT2": 1000.0,
        "PAY_AMT3": 1000.0,
        "PAY_AMT4": 1000.0,
        "PAY_AMT5": 1000.0,
        "PAY_AMT6": 1000.0,
    }
