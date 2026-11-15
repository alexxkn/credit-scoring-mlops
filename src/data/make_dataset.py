import argparse
import pathlib

import pandas as pd
import sklearn.model_selection
import yaml

import src.data.validation as validation

RAW_TARGET = "default.payment.next.month"
TARGET = "default"


def load_raw(path):
    return pd.read_csv(path)


def clean_data(df):
    df = df.drop(columns=["ID"]).rename(columns={RAW_TARGET: TARGET})
    # EDUCATION 0 не описан, 5 и 6 описаны как unknown, MARRIAGE 0 не описан, поэтому относим их к категории others
    df["EDUCATION"] = df["EDUCATION"].replace({0: 4, 5: 4, 6: 4})
    df["MARRIAGE"] = df["MARRIAGE"].replace({0: 3})
    return df


def split_data(df, test_size, random_state):
    return sklearn.model_selection.train_test_split(df, test_size=test_size, random_state=random_state, stratify=df[TARGET])


def main():
    parser = argparse.ArgumentParser(description="Загрузка, валидация, очистка и разбиение данных")
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output_dir", type=pathlib.Path)
    args = parser.parse_args()
    params = yaml.safe_load(pathlib.Path("params.yaml").read_text())["prepare"]

    raw = load_raw(args.input)
    result = validation.validate(raw)
    validation.print_report(result)
    if not result.success:
        raise SystemExit("Данные не прошли валидацию")
    validation.save_suite(validation.build_suite())

    train, test = split_data(clean_data(raw), params["test_size"], params["random_state"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    train.to_csv(args.output_dir / "train.csv", index=False)
    test.to_csv(args.output_dir / "test.csv", index=False)
    print(f"train: {len(train)} строк, test: {len(test)} строк")


if __name__ == "__main__":
    main()
