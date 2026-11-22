import json
import os
import pathlib

import mlflow
import numpy as np
import pandas as pd
import sklearn.metrics
import sklearn.model_selection
import torch
import yaml

import src.data.make_dataset as make_dataset
import src.features.build_features as build_features
import src.models.metrics as metrics
import src.models.nn as nn

MODEL_DIR = pathlib.Path("models/nn")
EXPERIMENT_NAME = "credit_default_prediction"


def load_split(path):
    df = pd.read_csv(path)
    return df[build_features.INPUT_FEATURES], df[make_dataset.TARGET].to_numpy(np.float32)


def predict_proba(model, X, device="cpu"):
    model.eval()
    with torch.no_grad():
        return model.to(device)(nn.to_tensor(X).to(device)).cpu().numpy().ravel()


def fit(model, X_fit, y_fit, X_val, y_val, params, device, epochs=None):
    """Обучает с ранней остановкой по ROC-AUC на валидации и возвращает лучшие веса."""
    torch.manual_seed(params["random_state"])
    optimizer = torch.optim.Adam(model.parameters(), lr=params["lr"], weight_decay=params["weight_decay"])
    loss_fn = torch.nn.BCELoss()
    dataset = torch.utils.data.TensorDataset(nn.to_tensor(X_fit), torch.tensor(y_fit).unsqueeze(1))
    loader = torch.utils.data.DataLoader(dataset, batch_size=params["batch_size"], shuffle=True)
    best_auc, best_state, bad_epochs = 0.0, None, 0
    for epoch in range(epochs or params["epochs"]):
        model.to(device).train()
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = loss_fn(model(xb.to(device)), yb.to(device))
            loss.backward()
            optimizer.step()
        auc = sklearn.metrics.roc_auc_score(y_val, predict_proba(model, X_val, device))
        if auc > best_auc:
            best_auc, best_state, bad_epochs = auc, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}, 0
        else:
            bad_epochs += 1
            if bad_epochs >= params["patience"]:
                break
    model.load_state_dict(best_state)
    return best_auc, epoch + 1


def best_threshold(y_true, y_proba):
    precision, recall, thresholds = sklearn.metrics.precision_recall_curve(y_true, y_proba)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-12, None)
    return float(thresholds[np.argmax(f1[:-1])])


def save(model, stats, params, threshold, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "stats": stats, "hidden": params["hidden"], "dropout": params["dropout"], "threshold": threshold}, path)


def load(path):
    checkpoint = torch.load(path, weights_only=False)
    model = nn.CreditScoringNet(checkpoint["stats"], tuple(checkpoint["hidden"]), checkpoint["dropout"])
    model.load_state_dict(checkpoint["state_dict"])
    return model.eval(), checkpoint


def main():
    params = yaml.safe_load(pathlib.Path("params.yaml").read_text())["train_nn"]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    X_train, y_train = load_split("data/processed/train.csv")
    X_test, y_test = load_split("data/processed/test.csv")
    X_fit, X_val, y_fit, y_val = sklearn.model_selection.train_test_split(
        X_train, y_train, test_size=params["val_size"], random_state=params["random_state"], stratify=y_train
    )

    stats = nn.fit_preprocessing(X_fit)
    model = nn.CreditScoringNet(stats, tuple(params["hidden"]), params["dropout"])
    val_auc, epochs = fit(model, X_fit, y_fit, X_val, y_val, params, device)
    threshold = best_threshold(y_val, predict_proba(model, X_val, device))
    y_proba = predict_proba(model, X_test)
    test_metrics = metrics.compute_metrics(y_test, y_proba, (y_proba >= threshold).astype(int))
    test_metrics["brier"] = float(sklearn.metrics.brier_score_loss(y_test, y_proba))

    save(model, stats, params, threshold, MODEL_DIR / "model.pt")
    summary = {"val_roc_auc": val_auc, "epochs": epochs, "threshold": threshold, **{f"test_{k}": v for k, v in test_metrics.items()}}
    (MODEL_DIR / "metrics.json").write_text(json.dumps(summary, indent=2))

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
    mlflow.set_experiment(EXPERIMENT_NAME)
    with mlflow.start_run(run_name="mlp"):
        mlflow.log_param("model_type", "mlp")
        mlflow.log_params({k: v for k, v in params.items()})
        mlflow.log_metrics({k: v for k, v in summary.items() if k != "epochs"})
        mlflow.log_artifact(str(MODEL_DIR / "model.pt"))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
