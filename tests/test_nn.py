import numpy as np
import onnxruntime as ort
import pytest
import torch

import src.data.make_dataset as make_dataset
import src.features.build_features as build_features
import src.models.nn as nn
import src.models.onnx_conversion as onnx_conversion
import src.models.pipeline as pipeline


@pytest.fixture
def clients(raw_data):
    return make_dataset.clean_data(raw_data).head(2000)


@pytest.fixture
def model(clients):
    torch.manual_seed(0)
    return nn.CreditScoringNet(nn.fit_preprocessing(clients[build_features.INPUT_FEATURES])).eval()


def test_numeric_preprocessing_matches_sklearn(clients, model):
    X = clients[build_features.INPUT_FEATURES]
    sklearn_numeric = pipeline.create_pipeline(None).named_steps["preprocessor"].transformers[0][1]
    expected = sklearn_numeric.fit_transform(build_features.build_features(X)[build_features.NUMERIC_FEATURES])
    actual = model.preprocess(nn.to_tensor(X)).numpy()[:, : len(build_features.NUMERIC_FEATURES)]
    np.testing.assert_allclose(actual, expected, atol=1e-4)


def test_onehot_matches_categories(clients, model):
    X = clients[build_features.INPUT_FEATURES]
    onehot = model.preprocess(nn.to_tensor(X)).numpy()[:, len(build_features.NUMERIC_FEATURES) :]
    age_bins = build_features.build_features(X)["AGE_BIN"]
    expected = [X[name] == value for name, values in nn.CATEGORIES.items() for value in values] + [age_bins == label for label in build_features.AGE_LABELS]
    np.testing.assert_array_equal(onehot, np.stack(expected, axis=1).astype(np.float32))


def test_output_is_probability(clients, model):
    with torch.no_grad():
        proba = model(nn.to_tensor(clients[build_features.INPUT_FEATURES])).numpy()
    assert proba.shape == (len(clients), 1)
    assert ((proba >= 0) & (proba <= 1)).all()


def test_onnx_export_matches_pytorch(clients, model, tmp_path):
    path = tmp_path / "model.onnx"
    onnx_conversion.export(model, path)
    X = clients[build_features.INPUT_FEATURES]
    report = onnx_conversion.validate(model, path, X, clients[make_dataset.TARGET], threshold=0.5)
    assert report["passed"], report
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    assert session.run(None, {"input": nn.to_tensor(X.head(1)).numpy()})[0].shape == (1, 1)
