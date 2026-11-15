import scipy.stats
import sklearn.compose
import sklearn.ensemble
import sklearn.impute
import sklearn.linear_model
import sklearn.pipeline
import sklearn.preprocessing

import src.features.build_features as build_features


def create_pipeline(classifier):
    numeric_transformer = sklearn.pipeline.Pipeline(
        steps=[("imputer", sklearn.impute.SimpleImputer(strategy="median")), ("scaler", sklearn.preprocessing.StandardScaler())]
    )
    categorical_transformer = sklearn.pipeline.Pipeline(
        steps=[("imputer", sklearn.impute.SimpleImputer(strategy="most_frequent")), ("onehot", sklearn.preprocessing.OneHotEncoder(handle_unknown="ignore"))]
    )
    preprocessor = sklearn.compose.ColumnTransformer(
        transformers=[("num", numeric_transformer, build_features.NUMERIC_FEATURES), ("cat", categorical_transformer, build_features.CATEGORICAL_FEATURES)]
    )
    return sklearn.pipeline.Pipeline(
        steps=[
            ("features", sklearn.preprocessing.FunctionTransformer(build_features.build_features)),
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


def get_candidates(random_state):
    return {
        "logistic_regression": (
            sklearn.linear_model.LogisticRegression(max_iter=2000),
            {"classifier__C": scipy.stats.loguniform(1e-3, 1e2), "classifier__class_weight": [None, "balanced"]},
        ),
        "random_forest": (
            sklearn.ensemble.RandomForestClassifier(n_estimators=300, random_state=random_state),
            {
                "classifier__max_depth": [6, 10, 15],
                "classifier__min_samples_leaf": [1, 5, 20, 50],
                "classifier__max_features": ["sqrt", 0.3, 0.5],
                "classifier__class_weight": [None, "balanced"],
            },
        ),
        "extra_trees": (
            sklearn.ensemble.ExtraTreesClassifier(n_estimators=300, random_state=random_state),
            {
                "classifier__max_depth": [6, 10, 15],
                "classifier__min_samples_leaf": [1, 5, 20, 50],
                "classifier__max_features": ["sqrt", 0.3, 0.5],
                "classifier__class_weight": [None, "balanced"],
            },
        ),
        "gradient_boosting": (
            sklearn.ensemble.GradientBoostingClassifier(random_state=random_state),
            {
                "classifier__n_estimators": [100, 200, 300],
                "classifier__learning_rate": [0.03, 0.05, 0.1],
                "classifier__max_depth": [2, 3, 4],
                "classifier__subsample": [0.8, 1.0],
            },
        ),
        "hist_gradient_boosting": (
            sklearn.ensemble.HistGradientBoostingClassifier(random_state=random_state),
            {
                "classifier__learning_rate": [0.03, 0.05, 0.1],
                "classifier__max_iter": [100, 200, 400],
                "classifier__max_leaf_nodes": [15, 31, 63],
                "classifier__min_samples_leaf": [20, 50, 100],
                "classifier__l2_regularization": [0.0, 1.0, 10.0],
            },
        ),
    }
