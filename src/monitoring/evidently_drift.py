import argparse
import datetime
import json
import os
import pathlib

import boto3
import evidently
import evidently.presets
import numpy as np
import onnxruntime as ort
import pandas as pd
import prometheus_client
import redis
import sklearn.metrics

import src.features.schema as schema

TARGET = "default"
# Доля признаков с дрифтом: 0.1 из 23 признаков значит хотя бы три, одиночный ложный сигнал переобучение не запускает
DRIFT_SHARE_THRESHOLD = float(os.environ.get("DRIFT_SHARE_THRESHOLD", "0.1"))
DECAY_THRESHOLD = float(os.environ.get("DECAY_THRESHOLD", "0.05"))


def read_current(client, stream, window):
    """Последние window предсказаний из журнала API и ответы, пришедшие через /feedback."""
    entries = client.xrevrange(stream, count=window)
    rows = []
    for _, fields in entries:
        record = json.loads(fields[b"features"])
        record["request_id"] = fields[b"request_id"].decode()
        record["probability"] = float(fields[b"probability"])
        record["model_version"] = fields[b"model_version"].decode()
        rows.append(record)
    current = pd.DataFrame(rows)
    if current.empty:
        return current
    labels = {key.decode(): int(value) for key, value in client.hgetall("feedback").items()}
    current[TARGET] = current["request_id"].map(labels)
    return current


def score(model_path, features):
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    return session.run(None, {"input": features[schema.INPUT_FEATURES].to_numpy(np.float32)})[0].ravel()


def metric_values(snapshot):
    values = {}
    for metric in snapshot.dict()["metrics"]:
        config = metric["config"]
        if config["type"].endswith("DriftedColumnsCount"):
            values["drift_share"] = metric["value"]["share"]
            values["drifted_columns"] = metric["value"]["count"]
        elif config["type"].endswith("ValueDrift"):
            values.setdefault("columns", {})[config["column"]] = {
                "score": float(metric["value"]),
                "threshold": float(config["threshold"]),
                "method": config["method"],
            }
    return values


def performance(frame):
    labeled = frame.dropna(subset=[TARGET])
    if labeled[TARGET].nunique() < 2:
        return None
    return {
        "rows": len(labeled),
        "roc_auc": float(sklearn.metrics.roc_auc_score(labeled[TARGET], labeled["probability"])),
        "default_rate": float(labeled[TARGET].mean()),
    }


def analyze(reference, current, reference_auc):
    columns = schema.INPUT_FEATURES + ["probability"]
    data_report = evidently.Report([evidently.presets.DataDriftPreset(columns=columns, drift_share=DRIFT_SHARE_THRESHOLD)])
    snapshot = data_report.run(current_data=current[columns], reference_data=reference[columns])
    values = metric_values(snapshot)
    feature_scores = {name: v for name, v in values["columns"].items() if name != "probability"}
    drifted = [name for name, v in feature_scores.items() if v["score"] >= v["threshold"]]
    summary = {
        "window": len(current),
        "data_drift_share": len(drifted) / len(feature_scores),
        "drifted_features": drifted,
        "feature_scores": {name: v["score"] for name, v in feature_scores.items()},
        "prediction_drift_score": values["columns"]["probability"]["score"],
        "prediction_drift_detected": values["columns"]["probability"]["score"] >= values["columns"]["probability"]["threshold"],
        "reference_roc_auc": reference_auc,
        "current_performance": performance(current),
        # A/B-тест: качество каждой версии модели на тех же по времени запросах
        "performance_by_version": {version: performance(group) for version, group in current.groupby("model_version")},
    }
    summary["data_drift_detected"] = summary["data_drift_share"] >= DRIFT_SHARE_THRESHOLD
    current_perf = summary["current_performance"]
    # Concept drift: признаки могут не сдвинуться, а связь признаков с дефолтом измениться. Её видно по падению качества на размеченных ответах
    summary["performance_decay"] = None if current_perf is None else reference_auc - current_perf["roc_auc"]
    summary["concept_drift_detected"] = summary["performance_decay"] is not None and summary["performance_decay"] > DECAY_THRESHOLD
    summary["retrain_recommended"] = summary["data_drift_detected"] or summary["prediction_drift_detected"] or summary["concept_drift_detected"]
    return summary, snapshot


def push_metrics(summary, gateway):
    registry = prometheus_client.CollectorRegistry()

    def gauge(name, documentation, labels=()):
        return prometheus_client.Gauge(name, documentation, labels, registry=registry)

    gauge("credit_drift_window_size", "Размер окна текущих данных").set(summary["window"])
    gauge("credit_data_drift_share", "Доля признаков с дрифтом").set(summary["data_drift_share"])
    gauge("credit_data_drift_detected", "Дрифт данных обнаружен").set(int(summary["data_drift_detected"]))
    gauge("credit_prediction_drift_score", "Дрифт распределения вероятностей").set(summary["prediction_drift_score"])
    gauge("credit_prediction_drift_detected", "Дрифт вероятностей обнаружен").set(int(summary["prediction_drift_detected"]))
    gauge("credit_concept_drift_detected", "Падение качества на размеченных данных").set(int(summary["concept_drift_detected"]))
    gauge("credit_retrain_recommended", "Мониторинг рекомендует переобучение").set(int(summary["retrain_recommended"]))
    feature = gauge("credit_feature_drift_score", "Оценка дрифта признака", ["feature"])
    for name, value in summary["feature_scores"].items():
        feature.labels(name).set(value)
    if summary["current_performance"] is not None:
        gauge("credit_model_roc_auc_current", "ROC-AUC на размеченных ответах").set(summary["current_performance"]["roc_auc"])
        gauge("credit_model_performance_decay", "Падение ROC-AUC относительно теста").set(summary["performance_decay"])
        gauge("credit_labeled_rows", "Число размеченных ответов в окне").set(summary["current_performance"]["rows"])
    by_version = gauge("credit_model_roc_auc_by_version", "ROC-AUC версии модели на размеченных ответах", ["model_version"])
    for version, result in summary["performance_by_version"].items():
        if result is not None:
            by_version.labels(version).set(result["roc_auc"])
    gauge("credit_drift_last_run_timestamp", "Время последней проверки").set_to_current_time()
    prometheus_client.push_to_gateway(gateway, job="credit_drift_monitor", registry=registry)


def upload(summary, snapshot, bucket, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    html = out_dir / "drift_report.html"
    snapshot.save_html(str(html))
    (out_dir / "drift_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    if bucket:
        client = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL", "https://hb.ru-msk.vkcloud-storage.ru"))
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for name in ("drift_report.html", "drift_summary.json"):
            client.upload_file(str(out_dir / name), bucket, f"drift/{stamp}/{name}")
        client.upload_file(str(out_dir / "drift_summary.json"), bucket, "drift/latest.json")


def main():
    parser = argparse.ArgumentParser(description="Мониторинг data drift, concept drift и качества модели по журналу предсказаний")
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    parser.add_argument("--stream", default=os.environ.get("PREDICTION_STREAM", "predictions"))
    parser.add_argument("--window", type=int, default=int(os.environ.get("DRIFT_WINDOW", "5000")))
    parser.add_argument("--reference", default=os.environ.get("REFERENCE_PATH", "data/processed/train.csv"))
    parser.add_argument("--model", default=os.environ.get("MODEL_PATH", "models/nn/model.onnx"))
    parser.add_argument("--model-meta", default=os.environ.get("MODEL_META_PATH", "models/nn/metrics.json"))
    parser.add_argument("--pushgateway", default=os.environ.get("PUSHGATEWAY_URL", ""))
    parser.add_argument("--bucket", default=os.environ.get("REPORTS_BUCKET", ""))
    parser.add_argument("--out-dir", default="reports/drift", type=pathlib.Path)
    parser.add_argument("--min-window", type=int, default=200)
    args = parser.parse_args()

    current = read_current(redis.Redis.from_url(args.redis_url), args.stream, args.window)
    if len(current) < args.min_window:
        print(json.dumps({"status": "skipped", "reason": f"в журнале {len(current)} записей, нужно не меньше {args.min_window}"}))
        return
    reference = pd.read_csv(args.reference).sample(n=min(10000, args.window * 2), random_state=42)
    reference["probability"] = score(args.model, reference)
    reference_auc = json.loads(pathlib.Path(args.model_meta).read_text())["test_roc_auc"]
    summary, snapshot = analyze(reference, current, reference_auc)
    upload(summary, snapshot, args.bucket, args.out_dir)
    if args.pushgateway:
        push_metrics(summary, args.pushgateway)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
