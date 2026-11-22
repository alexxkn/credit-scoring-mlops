# syntax=docker/dockerfile:1.7
# Мониторинг дрифта: Evidently требует pandas 2, поэтому у него своё окружение, отдельное от обучения и сервиса

FROM docker.io/library/python:3.12-slim AS deps
COPY deployment/docker/drift/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /tmp/requirements.txt

FROM docker.io/library/python:3.12-slim AS data
RUN pip install --no-cache-dir dvc==3.67.1 dvc-s3==3.3.0
WORKDIR /repo
COPY .dvc/config .dvc/config
COPY dvc.yaml dvc.lock params.yaml ./
# Эталон для сравнения: обучающая выборка и модель той же версии, что в DVC
RUN --mount=type=secret,id=aws_access_key_id,env=AWS_ACCESS_KEY_ID \
    --mount=type=secret,id=aws_secret_access_key,env=AWS_SECRET_ACCESS_KEY \
    dvc config core.no_scm true && dvc pull prepare convert_onnx

FROM docker.io/library/python:3.12-slim AS runtime
RUN useradd --uid 10001 --create-home app
COPY --from=deps /install /usr/local
WORKDIR /app
COPY --from=data /repo/data/processed/train.csv data/processed/train.csv
COPY --from=data /repo/models/nn/model.onnx models/nn/model.onnx
COPY models/nn/metrics.json models/nn/metrics.json
COPY src/__init__.py src/__init__.py
COPY src/features/__init__.py src/features/schema.py src/features/
COPY src/monitoring/__init__.py src/monitoring/evidently_drift.py src/monitoring/
USER 10001
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.monitoring.evidently_drift", "--out-dir", "/tmp/drift"]
