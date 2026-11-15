import json
import pathlib
import tempfile

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
import sklearn.model_selection
import yaml

import src.data.make_dataset as make_dataset
import src.features.build_features as build_features
import src.models.metrics as metrics
import src.models.pipeline as pipeline

TRACKING_URI = "sqlite:///mlflow.db"
EXPERIMENT_NAME = "credit_default_prediction"
REGISTERED_MODEL_NAME = "CreditDefaultModel"
MODEL_PATH = pathlib.Path("models/credit_default_model.pkl")
METRICS_PATH = pathlib.Path("metrics.json")
ROC_PATH = pathlib.Path("reports/roc_curve.png")


def load_split(path):
    df = pd.read_csv(path)
    return df[build_features.INPUT_FEATURES], df[make_dataset.TARGET]


def train_candidate(name, classifier, distributions, X_train, y_train, params):
    search = sklearn.model_selection.RandomizedSearchCV(
        pipeline.create_pipeline(classifier),
        distributions,
        n_iter=params["n_iter"],
        scoring="roc_auc",
        cv=sklearn.model_selection.StratifiedKFold(n_splits=params["cv"], shuffle=True, random_state=params["random_state"]),
        n_jobs=params["n_jobs"],
        random_state=params["random_state"],
    )
    search.fit(X_train, y_train)
    # Порог 0.5 при доле дефолтов около 22% даёт низкий recall, поэтому подбираем порог по F1 на кросс-валидации обучающей выборки
    model = sklearn.model_selection.TunedThresholdClassifierCV(search.best_estimator_, scoring="f1", cv=params["cv"], n_jobs=params["n_jobs"])
    model.fit(X_train, y_train)
    return search, model


def run_experiment(name, classifier, distributions, X_train, y_train, X_test, y_test, params):
    with mlflow.start_run(run_name=name) as run:
        search, model = train_candidate(name, classifier, distributions, X_train, y_train, params)
        y_proba = model.predict_proba(X_test)[:, 1]
        test_metrics = metrics.compute_metrics(y_test, y_proba, model.predict(X_test))

        mlflow.log_param("model_type", name)
        mlflow.log_params({"cv": params["cv"], "n_iter": params["n_iter"]})
        mlflow.log_params({key.removeprefix("classifier__"): value for key, value in search.best_params_.items()})
        mlflow.log_metric("cv_roc_auc", search.best_score_)
        mlflow.log_metric("threshold", model.best_threshold_)
        mlflow.log_metrics({f"test_{key}": value for key, value in test_metrics.items()})

        with tempfile.TemporaryDirectory() as tmp:
            roc_path = pathlib.Path(tmp) / "roc_curve.png"
            metrics.plot_roc_curve(y_test, y_proba, f"ROC-кривая на тестовой выборке: {name}", roc_path)
            mlflow.log_artifact(str(roc_path))
            cv_results_path = pathlib.Path(tmp) / "cv_results.csv"
            pd.DataFrame(search.cv_results_).to_csv(cv_results_path, index=False)
            mlflow.log_artifact(str(cv_results_path))
        # skops не пропускает функцию признаков из src, поэтому сохраняем через cloudpickle и прикладываем код src к модели
        mlflow.sklearn.log_model(model, name="model", input_example=X_train.head(3), serialization_format="cloudpickle", code_paths=["src"])

        print(f"{name}: cv_roc_auc={search.best_score_:.4f} test={json.dumps({k: round(v, 4) for k, v in test_metrics.items()})}")
        return {"name": name, "run_id": run.info.run_id, "cv_roc_auc": search.best_score_, "model": model, "test": test_metrics}


def main():
    params = yaml.safe_load(pathlib.Path("params.yaml").read_text())["train"]
    X_train, y_train = load_split("data/processed/train.csv")
    X_test, y_test = load_split("data/processed/test.csv")

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)
    results = [
        run_experiment(name, classifier, distributions, X_train, y_train, X_test, y_test, params)
        for name, (classifier, distributions) in pipeline.get_candidates(params["random_state"]).items()
    ]

    # Лучшую модель выбираем по ROC-AUC на кросс-валидации, тестовая выборка в выборе не участвует
    best = max(results, key=lambda result: result["cv_roc_auc"])
    mlflow.register_model(f"runs:/{best['run_id']}/model", REGISTERED_MODEL_NAME)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best["model"], MODEL_PATH)
    ROC_PATH.parent.mkdir(parents=True, exist_ok=True)
    metrics.plot_roc_curve(y_test, best["model"].predict_proba(X_test)[:, 1], f"ROC-кривая на тестовой выборке: {best['name']}", ROC_PATH)
    summary = {"model": best["name"], "run_id": best["run_id"], "cv_roc_auc": best["cv_roc_auc"], **{f"test_{k}": v for k, v in best["test"].items()}}
    METRICS_PATH.write_text(json.dumps(summary, indent=2))
    print(f"Лучшая модель: {best['name']}, сохранена в {MODEL_PATH}")


if __name__ == "__main__":
    main()
