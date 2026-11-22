import pathlib
import random

import locust
import pandas as pd

import src.features.schema as schema

DATA_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "processed" / "test.csv"
CLIENTS = pd.read_csv(DATA_PATH)[schema.INPUT_FEATURES].to_dict(orient="records")


class ApiUser(locust.FastHttpUser):
    wait_time = locust.constant(0)

    @locust.task(9)
    def predict(self):
        self.client.post("/predict", json=random.choice(CLIENTS))

    @locust.task(1)
    def predict_batch(self):
        self.client.post("/predict/batch", json=random.sample(CLIENTS, 100), name="/predict/batch")
