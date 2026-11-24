import contextlib
import json
import logging
import sys
import time
import uuid

import fastapi
import prometheus_client
import pydantic

import src.api.model_store as model_store
import src.api.prediction_log as prediction_log
import src.api.settings as settings


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {"ts": self.formatTime(record), "level": record.levelname, "logger": record.name, "message": record.getMessage()}
        entry.update(getattr(record, "extra_fields", {}))
        return json.dumps(entry, ensure_ascii=False)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=settings.LOG_LEVEL, handlers=[handler], force=True)
logger = logging.getLogger("credit_api")

REQUESTS = prometheus_client.Counter("credit_api_requests_total", "HTTP-запросы к API", ["method", "path", "status"])
LATENCY = prometheus_client.Histogram(
    "credit_api_request_duration_seconds", "Время обработки запроса", ["path"], buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1)
)
INFERENCE = prometheus_client.Histogram("credit_model_inference_seconds", "Время инференса ONNX", buckets=(0.0001, 0.00025, 0.0005, 0.001, 0.0025, 0.005, 0.01))
PREDICTIONS = prometheus_client.Counter("credit_predictions_total", "Предсказания по классам", ["model_version", "prediction"])
PROBABILITY = prometheus_client.Histogram(
    "credit_prediction_probability", "Распределение вероятности дефолта", ["model_version"], buckets=[i / 10 for i in range(1, 11)]
)
CACHE = prometheus_client.Counter("credit_cache_requests_total", "Обращения к кешу Redis", ["result"])
MODEL_INFO = prometheus_client.Gauge("credit_model_info", "Загруженная версия модели", ["model_version"])


@contextlib.asynccontextmanager
async def lifespan(app):
    app.state.model = model_store.load()
    app.state.log = prediction_log.PredictionLog(settings.REDIS_URL)
    MODEL_INFO.labels(app.state.model.version).set(1)
    logger.info("model loaded", extra={"extra_fields": {"model_version": app.state.model.version, "threshold": app.state.model.threshold}})
    yield


app = fastapi.FastAPI(title="Credit Default Prediction API", version="2.0", lifespan=lifespan)

PayStatus = pydantic.conint(ge=-2, le=9)
Amount = pydantic.confloat(ge=0)


class ClientData(pydantic.BaseModel):
    LIMIT_BAL: float = pydantic.Field(gt=0)
    SEX: int = pydantic.Field(ge=1, le=2)
    EDUCATION: int = pydantic.Field(ge=1, le=4)
    MARRIAGE: int = pydantic.Field(ge=1, le=3)
    AGE: int = pydantic.Field(ge=18, le=100)
    PAY_0: PayStatus
    PAY_2: PayStatus
    PAY_3: PayStatus
    PAY_4: PayStatus
    PAY_5: PayStatus
    PAY_6: PayStatus
    BILL_AMT1: float
    BILL_AMT2: float
    BILL_AMT3: float
    BILL_AMT4: float
    BILL_AMT5: float
    BILL_AMT6: float
    PAY_AMT1: Amount
    PAY_AMT2: Amount
    PAY_AMT3: Amount
    PAY_AMT4: Amount
    PAY_AMT5: Amount
    PAY_AMT6: Amount


class Prediction(pydantic.BaseModel):
    request_id: str
    default_prediction: int
    default_probability: float
    model_version: str


class Feedback(pydantic.BaseModel):
    request_id: str
    actual: int = pydantic.Field(ge=0, le=1)


@app.middleware("http")
async def observe(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    route = request.scope.get("route")
    path = route.path if route else "unmatched"
    if path != "/metrics":
        REQUESTS.labels(request.method, path, response.status_code).inc()
        LATENCY.labels(path).observe(duration)
        logger.info(
            "request",
            extra={"extra_fields": {"method": request.method, "path": path, "status": response.status_code, "duration_ms": round(duration * 1000, 3)}},
        )
    return response


def predict_records(app_state, records, journal=True):
    model, log = app_state.model, app_state.log
    probabilities = log.get_many(model.version, records)
    CACHE.labels("hit").inc(sum(p is not None for p in probabilities))
    missing = [i for i, p in enumerate(probabilities) if p is None]
    if missing:
        CACHE.labels("miss").inc(len(missing))
        with INFERENCE.time():
            computed = model.predict_proba([records[i] for i in missing])
        for i, probability in zip(missing, computed):
            probabilities[i] = float(probability)
    results, entries = [], []
    for record, probability in zip(records, probabilities):
        request_id = str(uuid.uuid4())
        label = int(probability >= model.threshold)
        PREDICTIONS.labels(model.version, str(label)).inc()
        PROBABILITY.labels(model.version).observe(probability)
        entries.append((request_id, record, probability))
        results.append(Prediction(request_id=request_id, default_prediction=label, default_probability=probability, model_version=model.version))
    log.write(model.version, [(records[i], probabilities[i]) for i in missing], entries if journal else [])
    return results


@app.get("/")
def read_root():
    return {"message": "Credit Default Prediction API is alive!"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(request: fastapi.Request):
    if not request.app.state.log.ping():
        # Redis нужен только для кеша и журнала, без него API отвечает, поэтому трафик с пода не снимаем
        logger.warning("redis unavailable")
    return {"status": "ready", "model_version": request.app.state.model.version}


def is_real_traffic(request):
    # Проверки Flagger и нагрузочные тесты шлют одинаковых клиентов: в журнале дрифта они дали бы ложный дрифт и лишнее переобучение
    return "x-synthetic" not in request.headers


@app.post("/predict", response_model=Prediction)
def predict(data: ClientData, request: fastapi.Request):
    return predict_records(request.app.state, [data.model_dump()], is_real_traffic(request))[0]


@app.post("/predict/batch", response_model=list[Prediction])
def predict_batch(data: list[ClientData], request: fastapi.Request):
    if len(data) > 1000:
        raise fastapi.HTTPException(status_code=413, detail="не больше 1000 клиентов за запрос")
    return predict_records(request.app.state, [item.model_dump() for item in data], is_real_traffic(request))


@app.post("/feedback")
def feedback(data: Feedback, request: fastapi.Request):
    if not request.app.state.log.feedback(data.request_id, data.actual):
        raise fastapi.HTTPException(status_code=503, detail="журнал предсказаний не настроен")
    return {"status": "stored"}


@app.get("/metrics")
def metrics():
    return fastapi.Response(prometheus_client.generate_latest(), media_type=prometheus_client.CONTENT_TYPE_LATEST)
