import contextlib
import os

import fastapi
import pydantic

import src.models.predict as predict

MODEL_PATH = os.environ.get("MODEL_PATH", "models/credit_default_model.pkl")


@contextlib.asynccontextmanager
async def lifespan(app):
    app.state.model = predict.load_model(MODEL_PATH)
    yield


app = fastapi.FastAPI(title="Credit Default Prediction API", lifespan=lifespan)

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
    default_prediction: int
    default_probability: float


@app.get("/")
def read_root():
    return {"message": "Credit Default Prediction API is alive!"}


@app.post("/predict", response_model=Prediction)
def predict_default(data: ClientData, request: fastapi.Request):
    labels, probabilities = predict.predict(request.app.state.model, [data.model_dump()])
    return Prediction(default_prediction=int(labels[0]), default_probability=float(probabilities[0]))
