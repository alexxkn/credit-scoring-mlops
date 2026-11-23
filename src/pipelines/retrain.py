import argparse
import datetime
import json
import os
import pathlib
import tempfile

import boto3
import mlflow
import mlflow.onnx
import numpy as np
import onnx
import onnxruntime as ort
import pandas as pd
import redis
import sklearn.metrics
import sklearn.model_selection
import yaml

import src.data.make_dataset as make_dataset
import src.features.build_features as build_features
import src.models.nn as nn
import src.models.onnx_conversion as onnx_conversion
import src.models.train_nn as train_nn

S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "https://hb.ru-msk.vkcloud-storage.ru")
REGISTERED_MODEL = "CreditScoringNN"
XCOM_PATH = pathlib.Path("/airflow/xcom/return.json")


def labeled_traffic(redis_url, stream, window):
    """Запросы из журнала API, по которым через /feedback пришёл факт дефолта: это новые размеченные данные."""
    client = redis.Redis.from_url(redis_url)
    labels = {key.decode(): int(value) for key, value in client.hgetall("feedback").items()}
    rows = []
    for _, fields in client.xrevrange(stream, count=window):
        request_id = fields[b"request_id"].decode()
        if request_id in labels:
            rows.append({**json.loads(fields[b"features"]), make_dataset.TARGET: labels[request_id]})
    return pd.DataFrame(rows, columns=build_features.INPUT_FEATURES + [make_dataset.TARGET])


def onnx_proba(path, X):
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return session.run(None, {"input": nn.to_tensor(X).numpy()})[0].ravel()


def evaluate(proba, y, threshold):
    return {"roc_auc": float(sklearn.metrics.roc_auc_score(y, proba)), "f1": float(sklearn.metrics.f1_score(y, proba >= threshold))}


def download_production(s3, bucket, target_dir):
    """Текущая production-модель: models/production.json указывает её версию."""
    pointer = json.loads(s3.get_object(Bucket=bucket, Key="production.json")["Body"].read())
    model_path, meta_path = pathlib.Path(target_dir) / "model.onnx", pathlib.Path(target_dir) / "metrics.json"
    s3.download_file(bucket, f"{pointer['version']}/model.onnx", str(model_path))
    s3.download_file(bucket, f"{pointer['version']}/metrics.json", str(meta_path))
    return pointer["version"], model_path, json.loads(meta_path.read_text())


def main():
    parser = argparse.ArgumentParser(description="Переобучение нейросети на исходных и новых размеченных данных и проверка против production")
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL", ""))
    parser.add_argument("--stream", default=os.environ.get("PREDICTION_STREAM", "predictions"))
    parser.add_argument("--window", type=int, default=50000)
    parser.add_argument("--models-bucket", default=os.environ.get("MODELS_BUCKET", ""))
    parser.add_argument("--min-gain", type=float, default=float(os.environ.get("MIN_GAIN", "0.0")), help="на сколько ROC-AUC кандидат должен быть лучше")
    parser.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("models/candidate"))
    args = parser.parse_args()

    params = yaml.safe_load(pathlib.Path("params.yaml").read_text())["train_nn"]
    base = pd.read_csv("data/processed/train.csv")
    holdout = pd.read_csv("data/processed/test.csv")
    traffic = labeled_traffic(args.redis_url, args.stream, args.window) if args.redis_url else base.iloc[:0]
    # Свежие размеченные данные делим так же, как исходные: часть идёт в обучение, часть в проверку против production
    traffic_train, traffic_eval = (
        (traffic.iloc[:0], traffic) if len(traffic) < 200 else sklearn.model_selection.train_test_split(traffic, test_size=0.3, random_state=42)
    )
    train = pd.concat([base, traffic_train], ignore_index=True)
    evaluation = pd.concat([holdout, traffic_eval], ignore_index=True)

    X, y = train[build_features.INPUT_FEATURES], train[make_dataset.TARGET].to_numpy(np.float32)
    X_fit, X_val, y_fit, y_val = sklearn.model_selection.train_test_split(X, y, test_size=params["val_size"], random_state=params["random_state"], stratify=y)
    stats = nn.fit_preprocessing(X_fit)
    model = nn.CreditScoringNet(stats, tuple(params["hidden"]), params["dropout"])
    train_nn.fit(model, X_fit, y_fit, X_val, y_val, params, "cpu")
    threshold = train_nn.best_threshold(y_val, train_nn.predict_proba(model, X_val))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = args.out_dir / "model.onnx"
    onnx_conversion.export(model.eval(), onnx_path)
    X_eval, y_eval = evaluation[build_features.INPUT_FEATURES], evaluation[make_dataset.TARGET]
    validation = onnx_conversion.validate(model, onnx_path, X_eval, y_eval, threshold)
    candidate = evaluate(onnx_proba(onnx_path, X_eval), y_eval, threshold)

    version = "v" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    result = {"model_version": version, "train_rows": len(train), "new_labeled_rows": len(traffic), "candidate": candidate, "onnx_validation": validation}
    s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT_URL) if args.models_bucket else None
    if s3 is not None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                production_version, production_path, production_meta = download_production(s3, args.models_bucket, tmp)
                result["production"] = {
                    "model_version": production_version,
                    **evaluate(onnx_proba(production_path, X_eval), y_eval, production_meta["threshold"]),
                }
            except s3.exceptions.NoSuchKey:
                result["production"] = None
    production_auc = result.get("production", {}) and result["production"]["roc_auc"]
    result["promote"] = bool(validation["passed"] and (not production_auc or candidate["roc_auc"] >= production_auc + args.min_gain))

    metrics = {"threshold": threshold, "test_roc_auc": candidate["roc_auc"], "test_f1": candidate["f1"], "model_version": version}
    (args.out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    if result["promote"] and s3 is not None:
        for name in ("model.onnx", "metrics.json"):
            s3.upload_file(str(args.out_dir / name), args.models_bucket, f"{version}/{name}")
    if os.environ.get("MLFLOW_TRACKING_URI"):
        mlflow.set_experiment("credit_default_retraining")
        with mlflow.start_run(run_name=version):
            mlflow.log_params({"model_version": version, "train_rows": len(train), "new_labeled_rows": len(traffic)})
            mlflow.log_metrics({f"candidate_{k}": v for k, v in candidate.items()})
            if result.get("production"):
                mlflow.log_metrics({f"production_{k}": v for k, v in result["production"].items() if k != "model_version"})
            mlflow.log_artifact(str(args.out_dir / "metrics.json"))
            # В MLflow 3 в реестр попадает только модель, записанная через log_model, а не просто файл
            mlflow.onnx.log_model(onnx.load(onnx_path), name="model", registered_model_name=REGISTERED_MODEL if result["promote"] else None)
    if XCOM_PATH.parent.exists():
        XCOM_PATH.write_text(json.dumps(result))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
