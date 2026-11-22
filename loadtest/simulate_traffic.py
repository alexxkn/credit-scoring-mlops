import argparse
import concurrent.futures
import random

import pandas as pd
import requests

import src.features.schema as schema

TARGET = "default"


def shift_features(df):
    # Сдвиг входных данных: банк снизил лимиты, клиенты чаще просрочивают последний платёж
    df = df.copy()
    df["LIMIT_BAL"] = df["LIMIT_BAL"] * 0.6
    df["PAY_0"] = (df["PAY_0"] + 1).clip(upper=8)
    df["BILL_AMT1"] = df["BILL_AMT1"] * 1.3
    return df


def shift_concept(df, rate, seed):
    # Сдвиг концепции: признаки те же, но часть клиентов без просрочек тоже уходит в дефолт
    df = df.copy()
    rng = random.Random(seed)
    mask = (df["PAY_0"] <= 0) & (df[TARGET] == 0)
    flip = [index for index in df.index[mask] if rng.random() < rate]
    df.loc[flip, TARGET] = 1
    return df


def main():
    parser = argparse.ArgumentParser(description="Отправка клиентов из тестовой выборки в API и ответов через /feedback")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--data-shift", action="store_true")
    parser.add_argument("--concept-shift", type=float, default=0.0, help="доля клиентов без просрочек, у которых дефолт подменяется")
    parser.add_argument("--feedback-share", type=float, default=1.0, help="доля запросов, по которым приходит факт дефолта")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    data = pd.read_csv("data/processed/test.csv").sample(n=args.n, random_state=args.seed, replace=args.n > 6000).reset_index(drop=True)
    if args.data_shift:
        data = shift_features(data)
    if args.concept_shift:
        data = shift_concept(data, args.concept_shift, args.seed)
    rng = random.Random(args.seed)

    def send(row):
        with requests.Session() as session:
            record = {name: row[name] for name in schema.INPUT_FEATURES}
            response = session.post(f"{args.api_url}/predict", json=record, timeout=10)
            response.raise_for_status()
            if rng.random() < args.feedback_share:
                feedback = {"request_id": response.json()["request_id"], "actual": int(row[TARGET])}
                session.post(f"{args.api_url}/feedback", json=feedback, timeout=10).raise_for_status()

    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(send, [row for _, row in data.iterrows()]))
    print(f"отправлено {len(data)} клиентов")


if __name__ == "__main__":
    main()
