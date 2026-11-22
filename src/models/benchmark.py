import json
import pathlib
import platform
import time

import numpy as np
import onnxruntime as ort
import torch

import src.models.nn as nn
import src.models.train_nn as train_nn

MODEL_DIR = pathlib.Path("models/nn")
REPORT_JSON = pathlib.Path("reports/benchmark.json")
REPORT_MD = pathlib.Path("reports/benchmark.md")
BATCH_SIZES = [1, 64, 1024]
THREADS = [1, 2, 4, 8]


def as_array(df):
    return nn.to_tensor(df).numpy()


def measure(fn, repeats=200, warmup=20):
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    return {"p50_ms": float(np.percentile(times, 50)), "p95_ms": float(np.percentile(times, 95))}


def onnx_session(path, threads, provider="CPUExecutionProvider"):
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), options, providers=[provider])


def torch_runner(model, device):
    model = model.to(device).eval()

    def run(batch):
        # Время включает копирование входа на устройство и результата обратно: так сервис и работает
        with torch.no_grad():
            return model(torch.from_numpy(batch).to(device)).cpu().numpy()

    return run


def main():
    model, _ = train_nn.load(MODEL_DIR / "model.pt")
    X_test, _ = train_nn.load_split("data/processed/test.csv")
    data = as_array(X_test)
    variants = {"onnx_fp32": MODEL_DIR / "model.onnx", "onnx_int8": MODEL_DIR / "model.int8.onnx", "onnx_pruned": MODEL_DIR / "model.pruned.onnx"}
    rows = []
    for threads in THREADS:
        torch.set_num_threads(threads)
        runners = {"pytorch_cpu": torch_runner(model, "cpu")}
        for name, path in variants.items():
            session = onnx_session(path, threads)
            runners[name] = lambda batch, session=session: session.run(None, {"input": batch})
        for name, run in runners.items():
            for batch_size in BATCH_SIZES:
                batch = data[:batch_size]
                stats = measure(lambda: run(batch))
                rows.append(
                    {"device": "cpu", "threads": threads, "variant": name, "batch": batch_size, **stats, "rows_per_s": batch_size / stats["p50_ms"] * 1000}
                )
    if torch.cuda.is_available():
        run = torch_runner(model, "cuda")
        for batch_size in BATCH_SIZES:
            batch = data[:batch_size]
            stats = measure(lambda: run(batch))
            rows.append(
                {"device": "gpu", "threads": None, "variant": "pytorch_cuda", "batch": batch_size, **stats, "rows_per_s": batch_size / stats["p50_ms"] * 1000}
            )

    env = {
        "cpu": platform.processor() or platform.machine(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torch": torch.__version__,
        "onnxruntime": ort.__version__,
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps({"environment": env, "results": rows}, indent=2))
    lines = ["| device | threads | variant | batch | p50, мс | p95, мс | строк/с |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['device']} | {r['threads'] or '-'} | {r['variant']} | {r['batch']} | {r['p50_ms']:.3f} | {r['p95_ms']:.3f} | {r['rows_per_s']:.0f} |"
        )
    REPORT_MD.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
