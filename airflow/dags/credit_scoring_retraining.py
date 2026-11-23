import datetime
import json
import os
import time

import airflow.providers.cncf.kubernetes.operators.pod as pod
import airflow.sdk as sdk
import boto3
import kubernetes
import kubernetes.client.models as k8s

DEPLOYMENT = "credit-scoring-api"
CANARY_TIMEOUT_SECONDS = 1800


def s3_client():
    return boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT_URL"])


def read_json(bucket, key):
    client = s3_client()
    try:
        return json.loads(client.get_object(Bucket=bucket, Key=key)["Body"].read())
    except client.exceptions.NoSuchKey:
        return None


with sdk.DAG(
    dag_id="credit_scoring_retraining",
    description="Переобучение PD-модели: проверка дрифта, обучение, сравнение с production, canary через Flagger",
    schedule="@weekly",
    start_date=datetime.datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    tags=["mlops", "retraining"],
    default_args={"owner": "ml-team", "retries": 1, "retry_delay": datetime.timedelta(minutes=5)},
    params={"reason": "schedule"},
) as dag:

    @sdk.task
    def check_drift(params=None):
        """Причина запуска и последний отчёт Evidently: по расписанию переобучаемся всегда, отчёт попадает в лог для разбора."""
        summary = read_json(sdk.Variable.get("reports_bucket"), "drift/latest.json")
        brief = (
            None if summary is None else {k: summary.get(k) for k in ("data_drift_share", "prediction_drift_score", "performance_decay", "retrain_recommended")}
        )
        return {"reason": params["reason"], "drift": brief}

    retrain = pod.KubernetesPodOperator(
        task_id="retrain_model",
        namespace="mlops",
        name="retrain-model",
        image="{{ var.value.trainer_image }}",
        cmds=["python", "-m", "src.pipelines.retrain"],
        arguments=["--redis-url", "{{ var.value.redis_url }}", "--models-bucket", "{{ var.value.models_bucket }}"],
        env_vars={"MLFLOW_TRACKING_URI": "{{ var.value.mlflow_tracking_uri }}", "S3_ENDPOINT_URL": os.environ.get("S3_ENDPOINT_URL", "")},
        env_from=[k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name="mlops-s3"))],
        container_resources=k8s.V1ResourceRequirements(requests={"cpu": "1", "memory": "2Gi"}, limits={"memory": "4Gi"}),
        node_selector={"node-role.credit-scoring/pool": "system"},
        annotations={"sidecar.istio.io/inject": "false"},
        do_xcom_push=True,
        get_logs=True,
        on_finish_action="delete_pod",
    )

    @sdk.task.short_circuit
    def candidate_is_better(result):
        # Модель не выкатывается, если ONNX не совпал с PyTorch или новая версия хуже production на тех же данных
        print(json.dumps(result, indent=2))
        # Значение short_circuit уходит следующей задаче, поэтому возвращаем сам результат, а не флаг
        return result if result["promote"] else False

    @sdk.task
    def deploy_canary(result):
        """Меняет модель у Deployment: Flagger видит новую ревизию и начинает canary-анализ."""
        kubernetes.config.load_incluster_config()
        version = result["model_version"]
        env = [
            {"name": "MODEL_URI", "value": f"s3://{sdk.Variable.get('models_bucket')}/{version}"},
            {"name": "MODEL_VERSION", "value": version},
        ]
        patch = {"spec": {"template": {"spec": {"containers": [{"name": "api", "env": env}]}}}}
        kubernetes.client.AppsV1Api().patch_namespaced_deployment(DEPLOYMENT, sdk.Variable.get("prod_namespace"), patch)
        return version

    @sdk.task(retries=0)
    def wait_for_canary(version):
        """Ждёт вердикт Flagger. Успех — версия становится production, провал — Flagger уже вернул трафик, задача падает и шлёт алерт."""
        kubernetes.config.load_incluster_config()
        api = kubernetes.client.CustomObjectsApi()
        deadline = time.monotonic() + CANARY_TIMEOUT_SECONDS
        time.sleep(60)
        while time.monotonic() < deadline:
            canary = api.get_namespaced_custom_object("flagger.app", "v1beta1", sdk.Variable.get("prod_namespace"), "canaries", DEPLOYMENT)
            phase = canary.get("status", {}).get("phase")
            print(f"canary phase: {phase}, weight: {canary.get('status', {}).get('canaryWeight')}")
            if phase == "Succeeded":
                body = json.dumps({"version": version, "promoted_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
                s3_client().put_object(Bucket=sdk.Variable.get("models_bucket"), Key="production.json", Body=body.encode())
                return version
            if phase == "Failed":
                raise RuntimeError(f"canary {version} не прошёл анализ Flagger, трафик возвращён на прежнюю версию")
            time.sleep(30)
        raise TimeoutError("canary не завершился за 30 минут")

    drift = check_drift()
    result = retrain.output
    drift >> retrain
    wait_for_canary(deploy_canary(candidate_is_better(result)))
