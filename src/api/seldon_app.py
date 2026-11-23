import contextlib

import fastapi
import pydantic

import src.api.app as api
import src.api.model_store as model_store
import src.api.prediction_log as prediction_log
import src.api.settings as settings


@contextlib.asynccontextmanager
async def lifespan(app):
    app.state.model = model_store.load()
    app.state.log = prediction_log.PredictionLog(settings.REDIS_URL)
    yield


# Микросервис в протоколе Seldon Core v1: executor Seldon вызывает POST /predict на порту 9000.
# Модель, кеш и журнал те же, что у основного API
app = fastapi.FastAPI(title="Credit Default Seldon microservice", lifespan=lifespan)


class SeldonData(pydantic.BaseModel):
    names: list[str] | None = None
    ndarray: list[list[float]]


class SeldonRequest(pydantic.BaseModel):
    data: SeldonData


@app.get("/health/ping")
def ping():
    return "pong"


@app.get("/health/status")
def status():
    return {"status": "ok"}


@app.post("/predict")
def predict(body: SeldonRequest, request: fastapi.Request):
    names = body.data.names or list(api.ClientData.model_fields)
    try:
        records = [api.ClientData(**dict(zip(names, row))).model_dump() for row in body.data.ndarray]
    except pydantic.ValidationError as error:
        raise fastapi.HTTPException(status_code=422, detail=error.errors(include_url=False, include_context=False))
    predictions = api.predict_records(request.app.state, records)
    return {
        "data": {"names": ["default_probability", "default_prediction"], "ndarray": [[p.default_probability, p.default_prediction] for p in predictions]},
        "meta": {"tags": {"model_version": request.app.state.model.version}},
    }
