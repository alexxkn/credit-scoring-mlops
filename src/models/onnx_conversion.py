import json
import pathlib
import sys

import numpy as np
import onnx
import onnxruntime as ort
import sklearn.metrics
import torch

import src.models.nn as nn
import src.models.train_nn as train_nn

MODEL_DIR = pathlib.Path("models/nn")
ONNX_PATH = MODEL_DIR / "model.onnx"
TOLERANCE = 1e-5


def export(model, path):
    dummy = torch.zeros(4, len(nn.build_features.INPUT_FEATURES))
    torch.onnx.export(
        model,
        (dummy,),
        str(path),
        input_names=["input"],
        output_names=["probability"],
        dynamic_shapes={"x": {0: torch.export.Dim("batch")}},
        dynamo=True,
        external_data=False,
    )
    exported = onnx.load(str(path))
    # Экспортёр пишет в каждый узел ссылки на исходный код PyTorch: это 2/3 файла, для инференса они не нужны
    for node in exported.graph.node:
        del node.metadata_props[:]
    onnx.checker.check_model(exported)
    onnx.save(exported, str(path))


def onnx_predict(session, X):
    return session.run(None, {"input": nn.to_tensor(X).numpy()})[0].ravel()


def validate(model, onnx_path, X, y, threshold):
    """Сравнивает ответы PyTorch и ONNX Runtime на всей выборке: вероятности, классы и ROC-AUC."""
    expected = train_nn.predict_proba(model, X)
    actual = onnx_predict(ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"]), X)
    report = {
        "rows": len(X),
        "max_abs_diff": float(np.abs(expected - actual).max()),
        "class_mismatches": int(((expected >= threshold) != (actual >= threshold)).sum()),
        "roc_auc_torch": float(sklearn.metrics.roc_auc_score(y, expected)),
        "roc_auc_onnx": float(sklearn.metrics.roc_auc_score(y, actual)),
    }
    report["passed"] = report["max_abs_diff"] < TOLERANCE and report["class_mismatches"] == 0
    return report


def main():
    model, checkpoint = train_nn.load(MODEL_DIR / "model.pt")
    export(model, ONNX_PATH)
    X_test, y_test = train_nn.load_split("data/processed/test.csv")
    report = validate(model, ONNX_PATH, X_test, y_test, checkpoint["threshold"])
    (MODEL_DIR / "onnx_validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
