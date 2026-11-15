import fastapi.testclient
import joblib
import pytest
import sklearn.linear_model

import src.api.app as app_module
import src.data.make_dataset as make_dataset
import src.features.build_features as build_features
import src.models.pipeline as pipeline


@pytest.fixture
def client(raw_data, tmp_path, monkeypatch):
    # Обученной модели в CI нет (её создаёт dvc repro), поэтому обучаем логистическую регрессию на исходных данных
    data = make_dataset.clean_data(raw_data)
    model = pipeline.create_pipeline(sklearn.linear_model.LogisticRegression(max_iter=1000))
    model.fit(data[build_features.INPUT_FEATURES], data[make_dataset.TARGET])
    model_path = tmp_path / "model.pkl"
    joblib.dump(model, model_path)
    monkeypatch.setattr(app_module, "MODEL_PATH", str(model_path))
    with fastapi.testclient.TestClient(app_module.app) as test_client:
        yield test_client


def test_root(client):
    assert client.get("/").status_code == 200


def test_predict(client, client_row):
    response = client.post("/predict", json=client_row)
    assert response.status_code == 200
    body = response.json()
    assert body["default_prediction"] in (0, 1)
    assert 0 <= body["default_probability"] <= 1


@pytest.mark.parametrize("field, value", [("AGE", 10), ("SEX", 3), ("EDUCATION", 5), ("PAY_0", 15), ("PAY_AMT1", -5)])
def test_predict_rejects_invalid_values(client, client_row, field, value):
    assert client.post("/predict", json=client_row | {field: value}).status_code == 422


def test_predict_rejects_missing_field(client, client_row):
    client_row.pop("LIMIT_BAL")
    assert client.post("/predict", json=client_row).status_code == 422
