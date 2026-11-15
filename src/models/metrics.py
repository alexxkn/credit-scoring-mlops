import matplotlib.pyplot as plt
import sklearn.metrics


def compute_metrics(y_true, y_proba, y_pred):
    return {
        "roc_auc": sklearn.metrics.roc_auc_score(y_true, y_proba),
        "precision": sklearn.metrics.precision_score(y_true, y_pred, zero_division=0),
        "recall": sklearn.metrics.recall_score(y_true, y_pred),
        "f1": sklearn.metrics.f1_score(y_true, y_pred),
    }


def plot_roc_curve(y_true, y_proba, title, path):
    fpr, tpr, _ = sklearn.metrics.roc_curve(y_true, y_proba)
    auc = sklearn.metrics.roc_auc_score(y_true, y_proba)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(fpr, tpr, label=f"ROC-AUC = {auc:.3f}")
    ax.plot([0, 1], [0, 1], linestyle="--", color="grey", label="случайная модель")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(title)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
