import argparse
import json
import logging
import pathlib

import great_expectations as gx
import pandas as pd

SUITE_PATH = pathlib.Path("data/expectations/credit_data_suite.json")
PAY_STATUS = ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]
BILL_AMT = [f"BILL_AMT{i}" for i in range(1, 7)]
PAY_AMT = [f"PAY_AMT{i}" for i in range(1, 7)]
TARGET = "default.payment.next.month"
COLUMNS = ["ID", "LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE", *PAY_STATUS, *BILL_AMT, *PAY_AMT, TARGET]


def build_suite():
    suite = gx.ExpectationSuite(name="credit_data_suite")
    expectations = gx.expectations
    suite.add_expectation(expectations.ExpectTableColumnsToMatchSet(column_set=COLUMNS, exact_match=True))
    suite.add_expectation(expectations.ExpectTableRowCountToBeBetween(min_value=1))
    for column in COLUMNS:
        suite.add_expectation(expectations.ExpectColumnValuesToNotBeNull(column=column))
        suite.add_expectation(expectations.ExpectColumnValuesToBeInTypeList(column=column, type_list=["int64", "float64"]))
    suite.add_expectation(expectations.ExpectColumnValuesToBeUnique(column="ID"))
    suite.add_expectation(expectations.ExpectColumnValuesToBeBetween(column="LIMIT_BAL", min_value=1, max_value=10_000_000))
    suite.add_expectation(expectations.ExpectColumnValuesToBeBetween(column="AGE", min_value=18, max_value=100))
    suite.add_expectation(expectations.ExpectColumnValuesToBeInSet(column="SEX", value_set=[1, 2]))
    suite.add_expectation(expectations.ExpectColumnValuesToBeInSet(column="EDUCATION", value_set=[0, 1, 2, 3, 4, 5, 6]))
    suite.add_expectation(expectations.ExpectColumnValuesToBeInSet(column="MARRIAGE", value_set=[0, 1, 2, 3]))
    for column in PAY_STATUS:
        suite.add_expectation(expectations.ExpectColumnValuesToBeBetween(column=column, min_value=-2, max_value=9))
    for column in PAY_AMT:
        suite.add_expectation(expectations.ExpectColumnValuesToBeBetween(column=column, min_value=0))
    suite.add_expectation(expectations.ExpectColumnValuesToBeInSet(column=TARGET, value_set=[0, 1]))
    return suite


def save_suite(suite, path=SUITE_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(suite.to_json_dict(), indent=2, ensure_ascii=False))


def validate(df):
    # Контекст в памяти: правила хранятся в коде и в JSON, файловый проект GE с его каталогами нам не нужен
    context = gx.get_context(mode="ephemeral")
    batch_definition = context.data_sources.add_pandas("credit").add_dataframe_asset("clients").add_batch_definition_whole_dataframe("all")
    return batch_definition.get_batch(batch_parameters={"dataframe": df}).validate(build_suite())


def print_report(result):
    failed = [r for r in result.results if not r.success]
    print(f"Проверок: {len(result.results)}, не прошло: {len(failed)}")
    for r in failed:
        config = r.expectation_config
        print(f"  {config.type} {config.kwargs.get('column', '')}: {r.result.get('unexpected_count', r.exception_info)}")


def main():
    parser = argparse.ArgumentParser(description="Валидация данных набором правил Great Expectations")
    parser.add_argument("path", type=pathlib.Path)
    args = parser.parse_args()
    logging.getLogger("great_expectations").setLevel(logging.ERROR)
    result = validate(pd.read_csv(args.path))
    print_report(result)
    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
