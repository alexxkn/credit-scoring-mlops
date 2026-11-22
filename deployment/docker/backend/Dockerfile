# syntax=docker/dockerfile:1.7
# Сервис инференса: FastAPI + ONNX Runtime. Модель берётся из DVC remote на этапе сборки, sklearn и PyTorch в образ не попадают

FROM docker.io/library/python:3.12-slim AS deps
COPY deployment/docker/backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /tmp/requirements.txt

FROM docker.io/library/python:3.12-slim AS model
RUN pip install --no-cache-dir dvc==3.67.1 dvc-s3==3.3.0
WORKDIR /repo
COPY .dvc/config .dvc/config
COPY dvc.yaml dvc.lock params.yaml ./
# Ключи S3 передаются как build secret и не остаются в слоях образа
RUN --mount=type=secret,id=aws_access_key_id,env=AWS_ACCESS_KEY_ID \
    --mount=type=secret,id=aws_secret_access_key,env=AWS_SECRET_ACCESS_KEY \
    dvc config core.no_scm true && dvc pull convert_onnx optimize

FROM docker.io/library/python:3.12-slim AS runtime
RUN useradd --uid 10001 --create-home app
COPY --from=deps /install /usr/local
WORKDIR /app
COPY --from=model /repo/models/nn/model.onnx /repo/models/nn/model.int8.onnx models/nn/
COPY models/nn/metrics.json models/nn/metrics.json
COPY src/__init__.py src/__init__.py
COPY src/features/__init__.py src/features/schema.py src/features/
COPY src/api src/api
USER 10001
EXPOSE 8000
ENV PYTHONUNBUFFERED=1 MODEL_PATH=models/nn/model.onnx MODEL_META_PATH=models/nn/metrics.json
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
