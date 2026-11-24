import os

MODEL_PATH = os.environ.get("MODEL_PATH", "models/nn/model.onnx")
MODEL_META_PATH = os.environ.get("MODEL_META_PATH", "models/nn/metrics.json")
# s3://bucket/prefix с model.onnx и metrics.json: так новая версия модели выкатывается без пересборки образа
MODEL_URI = os.environ.get("MODEL_URI", "")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "baked")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "https://hb.ru-msk.vkcloud-storage.ru")
REDIS_URL = os.environ.get("REDIS_URL", "")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))
PREDICTION_STREAM = os.environ.get("PREDICTION_STREAM", "predictions")
PREDICTION_STREAM_MAXLEN = int(os.environ.get("PREDICTION_STREAM_MAXLEN", "200000"))
ORT_THREADS = int(os.environ.get("ORT_THREADS", "1"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
# Отдельный порт метрик вне sidecar Istio: иначе опросы Prometheus попадают в istio_requests_total и в success rate Flagger
METRICS_PORT = int(os.environ.get("METRICS_PORT", "0"))
