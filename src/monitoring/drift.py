import argparse
import json
import pathlib

import numpy as np
import pandas as pd
import requests

import src.data.make_dataset as make_dataset
import src.features.build_features as build_features
import src.models.predict as predict

KEY_FEATURES = ["LIMIT_BAL", "AGE", "PAY_0", "BILL_AMT1", "PAY_AMT1"]
REPORT_PATH = pathlib.Path("reports/drift_report.json")


def psi(expected, actual, bins=10):
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    # Границы корзин по квантилям эталона; у дискретных признаков квантили совпадают, поэтому оставляем уникальные.
    # right=True кладёт значение, равное границе, в левую корзину: иначе у константного признака любое большее значение попадает в ту же корзину
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1))[1:-1])
    expected_share = np.bincount(np.digitize(expected, edges, right=True), minlength=len(edges) + 1) / len(expected)
    actual_share = np.bincount(np.digitize(actual, edges, right=True), minlength=len(edges) + 1) / len(actual)
    # Пустая корзина дала бы log(0), поэтому ограничиваем доли снизу
    expected_share = np.clip(expected_share, 1e-4, None)
    actual_share = np.clip(actual_share, 1e-4, None)
    return float(np.sum((actual_share - expected_share) * np.log(actual_share / expected_share)))


def psi_status(value):
    if value < 0.1:
        return "нет дрифта"
    if value < 0.25:
        return "умеренный дрифт"
    return "значительный дрифт"


def simulate_shift(df):
    df = df.copy()
    df["LIMIT_BAL"] = df["LIMIT_BAL"] * 0.6
    df["PAY_0"] = (df["PAY_0"] + 1).clip(upper=8)
    df["BILL_AMT1"] = df["BILL_AMT1"] * 1.3
    return df


def request_predictions(api_url, df):
    probabilities = []
    with requests.Session() as session:
        for record in df[build_features.INPUT_FEATURES].to_dict(orient="records"):
            response = session.post(f"{api_url}/predict", json=record, timeout=10)
            response.raise_for_status()
            probabilities.append(response.json()["default_probability"])
    return np.array(probabilities)


def main():
    parser = argparse.ArgumentParser(description="Отправка новых данных в API и расчёт PSI относительно обучающей выборки")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--n-samples", type=int, default=1000)
    parser.add_argument("--shift", action="store_true", help="сдвинуть часть признаков, чтобы показать срабатывание дрифта")
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    train = pd.read_csv("data/processed/train.csv")
    new_data = pd.read_csv("data/processed/test.csv").sample(n=args.n_samples, random_state=args.random_state)
    if args.shift:
        new_data = simulate_shift(new_data)

    new_probabilities = request_predictions(args.api_url, new_data)
    model = predict.load_model("models/credit_default_model.pkl")
    _, train_probabilities = predict.predict(model, train[build_features.INPUT_FEATURES])

    report = {"default_probability": psi(train_probabilities, new_probabilities)}
    report.update({feature: psi(train[feature], new_data[feature]) for feature in KEY_FEATURES})
    for name, value in report.items():
        print(f"{name:20} PSI = {value:.4f}  {psi_status(value)}")
    print(f"Доля дефолтов в новых данных: {new_data[make_dataset.TARGET].mean():.3f}, средняя вероятность от API: {new_probabilities.mean():.3f}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({"n_samples": args.n_samples, "shift": args.shift, "psi": report}, indent=2))


if __name__ == "__main__":
    main()
