# syntax=docker/dockerfile:1
# Образ переобучения для Airflow (KubernetesPodOperator): PyTorch только для CPU, данные DVC внутри образа

FROM docker.io/library/python:3.12-slim AS deps
COPY deployment/docker/trainer/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --prefix=/install torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --prefix=/install -r /tmp/requirements.txt

FROM docker.io/library/python:3.12-slim AS data
RUN pip install --no-cache-dir dvc==3.67.1 dvc-s3==3.3.0
WORKDIR /repo
COPY .dvc/config .dvc/config
COPY dvc.yaml dvc.lock params.yaml ./
RUN --mount=type=secret,id=aws_access_key_id --mount=type=secret,id=aws_secret_access_key \
    export AWS_ACCESS_KEY_ID="$(cat /run/secrets/aws_access_key_id)" AWS_SECRET_ACCESS_KEY="$(cat /run/secrets/aws_secret_access_key)" \
    && dvc config core.no_scm true && dvc pull prepare

FROM docker.io/library/python:3.12-slim AS runtime
RUN useradd --uid 10001 --create-home app
COPY --from=deps /install /usr/local
WORKDIR /app
COPY --from=data /repo/data/processed data/processed
COPY params.yaml ./
COPY src src
RUN chown -R 10001 /app
USER 10001
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.pipelines.retrain"]
