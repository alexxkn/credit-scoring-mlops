import pandas as pd

import src.features.schema as schema

# Список входных признаков вынесен в schema.py без pandas: его использует сервис, где pandas не нужен
PAY_STATUS = schema.PAY_STATUS
BILL_AMT = schema.BILL_AMT
PAY_AMT = schema.PAY_AMT
INPUT_FEATURES = schema.INPUT_FEATURES

AGE_BINS = [0, 25, 35, 45, 55, 200]
AGE_LABELS = ["до 25", "26-35", "36-45", "46-55", "старше 55"]

NUMERIC_FEATURES = [
    "LIMIT_BAL",
    "AGE",
    *PAY_STATUS,
    *BILL_AMT,
    *PAY_AMT,
    "PAY_MAX",
    "PAY_DELAY_MONTHS",
    "BILL_MEAN",
    "PAY_AMT_MEAN",
    "UTILIZATION",
    "PAY_RATIO",
]
CATEGORICAL_FEATURES = ["SEX", "EDUCATION", "MARRIAGE", "AGE_BIN"]


def build_features(df):
    df = df.copy()
    pay_status = df[PAY_STATUS]
    df["PAY_MAX"] = pay_status.max(axis=1)
    df["PAY_DELAY_MONTHS"] = (pay_status > 0).sum(axis=1)
    df["BILL_MEAN"] = df[BILL_AMT].mean(axis=1)
    df["PAY_AMT_MEAN"] = df[PAY_AMT].mean(axis=1)
    df["UTILIZATION"] = df["BILL_AMT1"] / df["LIMIT_BAL"]
    bill_total = df[BILL_AMT].sum(axis=1)
    # Без положительного долга доля погашения не определена, оставляем NaN и заполняем медианой в Pipeline
    df["PAY_RATIO"] = df[PAY_AMT].sum(axis=1) / bill_total.where(bill_total > 0)
    df["AGE_BIN"] = pd.cut(df["AGE"], bins=AGE_BINS, labels=AGE_LABELS).astype(str)
    return df
