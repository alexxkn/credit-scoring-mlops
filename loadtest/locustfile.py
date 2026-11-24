import os
import pathlib
import random

import locust
import pandas as pd

import src.features.schema as schema

DATA_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "processed" / "test.csv"
CLIENTS = pd.read_csv(os.environ.get("CLIENTS_PATH", DATA_PATH))[schema.INPUT_FEATURES].to_dict(orient="records")
# В кластере тест идёт через ingress gateway Istio, маршрут выбирается по заголовку Host
# Нагрузочный трафик не пишется в журнал мониторинга дрифта
HEADERS = {"X-Synthetic": "locust"} | ({"Host": os.environ["HOST_HEADER"]} if os.environ.get("HOST_HEADER") else {})


class ApiUser(locust.FastHttpUser):
    wait_time = locust.constant(0)

    @locust.task(9)
    def predict(self):
        self.client.post("/predict", json=random.choice(CLIENTS), headers=HEADERS)

    @locust.task(1)
    def predict_batch(self):
        self.client.post("/predict/batch", json=random.sample(CLIENTS, 100), headers=HEADERS, name="/predict/batch")
