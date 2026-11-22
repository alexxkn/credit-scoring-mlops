import numpy as np
import pandas as pd
import torch

import src.features.build_features as build_features

CATEGORIES = {"SEX": [1, 2], "EDUCATION": [1, 2, 3, 4], "MARRIAGE": [1, 2, 3]}


def fit_preprocessing(X):
    features = build_features.build_features(X)[build_features.NUMERIC_FEATURES]
    medians = features.median()
    filled = features.fillna(medians)
    stds = filled.std(ddof=0).replace(0, 1)
    return {"medians": medians.to_numpy(np.float32), "means": filled.mean().to_numpy(np.float32), "stds": stds.to_numpy(np.float32)}


class CreditScoringNet(torch.nn.Module):
    """MLP, который принимает 23 исходных признака клиента и сам строит признаки, масштабирует и кодирует категории.

    Вся предобработка внутри графа, поэтому ONNX-модель не требует sklearn в сервисе.
    """

    def __init__(self, stats, hidden=(128, 64), dropout=0.2):
        super().__init__()
        self.register_buffer("medians", torch.tensor(stats["medians"]))
        self.register_buffer("means", torch.tensor(stats["means"]))
        self.register_buffer("stds", torch.tensor(stats["stds"]))
        self.index = {name: i for i, name in enumerate(build_features.INPUT_FEATURES)}
        n_inputs = len(build_features.NUMERIC_FEATURES) + sum(len(v) for v in CATEGORIES.values()) + len(build_features.AGE_LABELS)
        layers = []
        for size in hidden:
            layers += [torch.nn.Linear(n_inputs, size), torch.nn.ReLU(), torch.nn.Dropout(dropout)]
            n_inputs = size
        layers.append(torch.nn.Linear(n_inputs, 1))
        self.mlp = torch.nn.Sequential(*layers)

    def columns(self, x, names):
        return x[:, [self.index[name] for name in names]]

    def preprocess(self, x):
        pay, bill, pay_amt = self.columns(x, build_features.PAY_STATUS), self.columns(x, build_features.BILL_AMT), self.columns(x, build_features.PAY_AMT)
        limit, age = x[:, self.index["LIMIT_BAL"]], x[:, self.index["AGE"]]
        bill_total = bill.sum(dim=1)
        engineered = {
            "PAY_MAX": pay.max(dim=1).values,
            "PAY_DELAY_MONTHS": (pay > 0).float().sum(dim=1),
            "BILL_MEAN": bill.mean(dim=1),
            "PAY_AMT_MEAN": pay_amt.mean(dim=1),
            "UTILIZATION": x[:, self.index["BILL_AMT1"]] / limit,
            "PAY_RATIO": pay_amt.sum(dim=1) / torch.where(bill_total > 0, bill_total, torch.full_like(bill_total, float("nan"))),
        }
        numeric = torch.stack([engineered[name] if name in engineered else x[:, self.index[name]] for name in build_features.NUMERIC_FEATURES], dim=1)
        numeric = torch.where(torch.isnan(numeric), self.medians, numeric)
        numeric = (numeric - self.means) / self.stds
        onehot = [(x[:, self.index[name]] == value).float() for name, values in CATEGORIES.items() for value in values]
        edges = build_features.AGE_BINS
        onehot += [((age > low) & (age <= high)).float() for low, high in zip(edges[:-1], edges[1:])]
        return torch.cat([numeric, torch.stack(onehot, dim=1)], dim=1)

    def forward(self, x):
        return torch.sigmoid(self.mlp(self.preprocess(x)))


def to_tensor(X):
    return torch.tensor(pd.DataFrame(X)[build_features.INPUT_FEATURES].to_numpy(np.float32))
