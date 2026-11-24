import json
import socket
import urllib.request

import fakeredis
import fastapi.testclient
import pandas as pd
import prometheus_client
import pytest
import torch

import src.api.app as app_module
import src.api.prediction_log as prediction_log
import src.api.seldon_app as seldon_app
import src.api.settings as settings
import src.data.make_dataset as make_dataset
import src.features.build_features as build_features
import src.features.schema as schema
import src.models.nn as nn
import src.models.onnx_conversion as onnx_conversion
import tests.conftest as conftest


@pytest.fixture(scope="module")
def onnx_model(tmp_path_factory):
    # Обученной модели в CI нет (её создаёт dvc repro), поэтому экспортируем необученную сеть: API проверяется без качества модели
    directory = tmp_path_factory.mktemp("model")
    data = make_dataset.clean_data(pd.read_csv(conftest.RAW_PATH)).head(1000)
    torch.manual_seed(0)
    model = nn.CreditScoringNet(nn.fit_preprocessing(data[build_features.INPUT_FEATURES])).eval()
    onnx_conversion.export(model, directory / "model.onnx")
    (directory / "metrics.json").write_text(json.dumps({"threshold": 0.5}))
    return directory


@pytest.fixture
def client(onnx_model, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_PATH", str(onnx_model / "model.onnx"))
    monkeypatch.setattr(settings, "MODEL_META_PATH", str(onnx_model / "metrics.json"))
    monkeypatch.setattr(settings, "REDIS_URL", "")
    with fastapi.testclient.TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture
def redis_client(client, monkeypatch):
    log = prediction_log.PredictionLog("")
    log.client = fakeredis.FakeRedis()
    client.app.state.log = log
    return client


def test_schema_order_matches_api_fields():
    assert list(app_module.ClientData.model_fields) == schema.INPUT_FEATURES


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json()["status"] == "ready"


def test_predict(client, client_row):
    response = client.post("/predict", json=client_row)
    assert response.status_code == 200
    body = response.json()
    assert body["default_prediction"] in (0, 1)
    assert 0 <= body["default_probability"] <= 1
    assert body["model_version"] == settings.MODEL_VERSION


def test_predict_batch(client, client_row):
    response = client.post("/predict/batch", json=[client_row, client_row | {"PAY_0": 3}])
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_batch_limit(client, client_row):
    assert client.post("/predict/batch", json=[client_row] * 1001).status_code == 413


@pytest.mark.parametrize("field, value", [("AGE", 10), ("SEX", 3), ("EDUCATION", 5), ("PAY_0", 15), ("PAY_AMT1", -5)])
def test_predict_rejects_invalid_values(client, client_row, field, value):
    assert client.post("/predict", json=client_row | {field: value}).status_code == 422


def test_predict_rejects_missing_field(client, client_row):
    client_row.pop("LIMIT_BAL")
    assert client.post("/predict", json=client_row).status_code == 422


def test_metrics_exposed(client, client_row):
    client.post("/predict", json=client_row)
    text = client.get("/metrics").text
    assert "credit_predictions_total" in text
    assert "credit_api_request_duration_seconds_bucket" in text


def test_metrics_on_separate_port(onnx_model, monkeypatch, client_row):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    monkeypatch.setattr(settings, "MODEL_PATH", str(onnx_model / "model.onnx"))
    monkeypatch.setattr(settings, "MODEL_META_PATH", str(onnx_model / "metrics.json"))
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "METRICS_PORT", port)
    with fastapi.testclient.TestClient(app_module.app) as test_client:
        test_client.post("/predict", json=client_row)
        text = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics").read().decode()
    assert "credit_predictions_total" in text


def test_cache_and_prediction_stream(redis_client, client_row):
    hits_before = prometheus_client.REGISTRY.get_sample_value("credit_cache_requests_total", {"result": "hit"}) or 0
    first = redis_client.post("/predict", json=client_row).json()
    second = redis_client.post("/predict", json=client_row).json()
    assert first["default_probability"] == second["default_probability"]
    stream = redis_client.app.state.log.client.xrange(settings.PREDICTION_STREAM)
    assert len(stream) == 2
    assert prometheus_client.REGISTRY.get_sample_value("credit_cache_requests_total", {"result": "hit"}) == hits_before + 1


def test_batch_cache_and_stream(redis_client, client_row):
    rows = [client_row | {"AGE": age} for age in (25, 35, 45)]
    hits_before = prometheus_client.REGISTRY.get_sample_value("credit_cache_requests_total", {"result": "hit"}) or 0
    first = redis_client.post("/predict/batch", json=rows).json()
    second = redis_client.post("/predict/batch", json=rows).json()
    assert [p["default_probability"] for p in first] == [p["default_probability"] for p in second]
    assert len(redis_client.app.state.log.client.xrange(settings.PREDICTION_STREAM)) == 6
    assert prometheus_client.REGISTRY.get_sample_value("credit_cache_requests_total", {"result": "hit"}) == hits_before + 3


def test_synthetic_traffic_not_in_stream(redis_client, client_row):
    response = redis_client.post("/predict", json=client_row, headers={"X-Synthetic": "flagger"})
    assert response.status_code == 200
    assert redis_client.app.state.log.client.xrange(settings.PREDICTION_STREAM) == []


def test_feedback(redis_client, client_row):
    request_id = redis_client.post("/predict", json=client_row).json()["request_id"]
    assert redis_client.post("/feedback", json={"request_id": request_id, "actual": 1}).status_code == 200
    assert redis_client.app.state.log.client.hget("feedback", request_id) == b"1"


def test_feedback_without_redis(client):
    assert client.post("/feedback", json={"request_id": "x", "actual": 0}).status_code == 503


@pytest.fixture
def seldon_client(onnx_model, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_PATH", str(onnx_model / "model.onnx"))
    monkeypatch.setattr(settings, "MODEL_META_PATH", str(onnx_model / "metrics.json"))
    monkeypatch.setattr(settings, "REDIS_URL", "")
    with fastapi.testclient.TestClient(seldon_app.app) as test_client:
        yield test_client


def test_seldon_protocol(seldon_client, client_row):
    body = {"data": {"names": list(client_row), "ndarray": [list(client_row.values())]}}
    response = seldon_client.post("/predict", json=body)
    assert response.status_code == 200
    probability, label = response.json()["data"]["ndarray"][0]
    assert 0 <= probability <= 1 and label in (0, 1)


def test_seldon_protocol_rejects_invalid(seldon_client, client_row):
    body = {"data": {"names": list(client_row), "ndarray": [list((client_row | {"AGE": 10}).values())]}}
    assert seldon_client.post("/predict", json=body).status_code == 422
