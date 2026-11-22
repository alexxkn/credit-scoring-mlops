import gzip
import json
import pathlib

import onnxruntime.quantization
import sklearn.metrics
import sklearn.model_selection
import torch
import torch.nn.utils.prune
import yaml

import src.models.benchmark as benchmark
import src.models.onnx_conversion as onnx_conversion
import src.models.train_nn as train_nn

MODEL_DIR = pathlib.Path("models/nn")
INT8_PATH = MODEL_DIR / "model.int8.onnx"
PRUNED_PATH = MODEL_DIR / "model.pruned.onnx"
REPORT_PATH = pathlib.Path("reports/optimization.json")


def quantize(source, target):
    # Динамическая квантизация: веса Linear (MatMul/Gemm) в int8, активации квантуются на лету, калибровочные данные не нужны
    onnxruntime.quantization.quantize_dynamic(str(source), str(target), weight_type=onnxruntime.quantization.QuantType.QInt8)


def prune(model, amount, X_fit, y_fit, X_val, y_val, params, epochs):
    """Обнуляет долю amount весов Linear с наименьшим модулем по всей сети и дообучает оставшиеся веса с маской."""
    layers = [(module, "weight") for module in model.mlp if isinstance(module, torch.nn.Linear)]
    torch.nn.utils.prune.global_unstructured(layers, pruning_method=torch.nn.utils.prune.L1Unstructured, amount=amount)
    train_nn.fit(model, X_fit, y_fit, X_val, y_val, params, "cpu", epochs=epochs)
    for module, name in layers:
        torch.nn.utils.prune.remove(module, name)
    weights = [module.weight for module, _ in layers]
    return float(sum((w == 0).sum().item() for w in weights) / sum(w.numel() for w in weights))


def evaluate(path, X, y, threshold):
    session = benchmark.onnx_session(path, threads=1)
    data = benchmark.as_array(X)
    proba = session.run(None, {"input": data})[0].ravel()
    return {
        "size_kb": round(path.stat().st_size / 1024, 1),
        "gzip_kb": round(len(gzip.compress(path.read_bytes())) / 1024, 1),
        "roc_auc": float(sklearn.metrics.roc_auc_score(y, proba)),
        "f1": float(sklearn.metrics.f1_score(y, proba >= threshold)),
        "latency_ms_batch1": benchmark.measure(lambda: session.run(None, {"input": data[:1]}))["p50_ms"],
        "latency_ms_batch1024": benchmark.measure(lambda: session.run(None, {"input": data[:1024]}))["p50_ms"],
    }


def main():
    params = yaml.safe_load(pathlib.Path("params.yaml").read_text())
    nn_params, opt_params = params["train_nn"], params["optimize"]
    model, checkpoint = train_nn.load(MODEL_DIR / "model.pt")
    X_train, y_train = train_nn.load_split("data/processed/train.csv")
    X_test, y_test = train_nn.load_split("data/processed/test.csv")
    X_fit, X_val, y_fit, y_val = sklearn.model_selection.train_test_split(
        X_train, y_train, test_size=nn_params["val_size"], random_state=nn_params["random_state"], stratify=y_train
    )

    quantize(onnx_conversion.ONNX_PATH, INT8_PATH)
    sparsity = prune(model, opt_params["prune_amount"], X_fit, y_fit, X_val, y_val, nn_params, opt_params["finetune_epochs"])
    onnx_conversion.export(model.eval(), PRUNED_PATH)

    threshold = checkpoint["threshold"]
    report = {
        "original": evaluate(onnx_conversion.ONNX_PATH, X_test, y_test, threshold),
        "quantized_int8": evaluate(INT8_PATH, X_test, y_test, threshold),
        "pruned": {**evaluate(PRUNED_PATH, X_test, y_test, threshold), "sparsity": sparsity},
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
