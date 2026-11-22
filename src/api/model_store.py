import json
import pathlib
import tempfile
import urllib.parse

import boto3
import numpy as np
import onnxruntime as ort

import src.api.settings as settings
import src.features.schema as schema


def download(uri, target_dir):
    parsed = urllib.parse.urlparse(uri)
    client = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL)
    paths = {}
    for name in ("model.onnx", "metrics.json"):
        paths[name] = pathlib.Path(target_dir) / name
        client.download_file(parsed.netloc, f"{parsed.path.strip('/')}/{name}", str(paths[name]))
    return paths["model.onnx"], paths["metrics.json"]


class Model:
    def __init__(self, model_path, meta_path, version):
        options = ort.SessionOptions()
        options.intra_op_num_threads = settings.ORT_THREADS
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])
        self.threshold = json.loads(pathlib.Path(meta_path).read_text())["threshold"]
        self.version = version

    def predict_proba(self, records):
        batch = np.array([[record[name] for name in schema.INPUT_FEATURES] for record in records], dtype=np.float32)
        return self.session.run(None, {"input": batch})[0].ravel()


def load():
    if settings.MODEL_URI:
        model_path, meta_path = download(settings.MODEL_URI, tempfile.mkdtemp(prefix="model-"))
    else:
        model_path, meta_path = settings.MODEL_PATH, settings.MODEL_META_PATH
    return Model(model_path, meta_path, settings.MODEL_VERSION)
