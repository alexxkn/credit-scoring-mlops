# syntax=docker/dockerfile:1
# MLflow Tracking Server: метаданные в managed PostgreSQL, артефакты и реестр моделей в S3

FROM docker.io/library/python:3.12-slim AS deps
RUN pip install --no-cache-dir --prefix=/install mlflow==3.18.0 psycopg2-binary==2.9.11 boto3==1.43.117

FROM docker.io/library/python:3.12-slim AS runtime
RUN useradd --uid 10001 --create-home mlflow
COPY --from=deps /install /usr/local
USER 10001
EXPOSE 5000
ENTRYPOINT ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000"]
