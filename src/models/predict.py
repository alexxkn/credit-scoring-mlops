import joblib
import pandas as pd

import src.features.build_features as build_features


def load_model(path):
    return joblib.load(path)


def predict(model, records):
    df = pd.DataFrame(records, columns=build_features.INPUT_FEATURES)
    return model.predict(df), model.predict_proba(df)[:, 1]
