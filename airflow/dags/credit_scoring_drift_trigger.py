import datetime
import json
import os

import airflow.providers.standard.operators.trigger_dagrun as trigger_dagrun
import airflow.sdk as sdk
import boto3

# Не чаще одного внепланового переобучения в сутки: дрифт держится, пока новая модель не выкачена
COOLDOWN = datetime.timedelta(hours=24)


with sdk.DAG(
    dag_id="credit_scoring_drift_trigger",
    description="Запуск переобучения по сигналу мониторинга Evidently: дрифт данных, вероятностей или падение качества",
    schedule="15 * * * *",
    start_date=datetime.datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    tags=["mlops", "monitoring"],
) as dag:

    @sdk.task.short_circuit
    def drift_requires_retraining():
        client = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT_URL"])
        bucket = sdk.Variable.get("reports_bucket")
        try:
            summary = json.loads(client.get_object(Bucket=bucket, Key="drift/latest.json")["Body"].read())
        except client.exceptions.NoSuchKey:
            return False
        if not summary.get("retrain_recommended"):
            return False
        try:
            last = json.loads(client.get_object(Bucket=bucket, Key="drift/last_trigger.json")["Body"].read())
            if datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(last["at"]) < COOLDOWN:
                return False
        except client.exceptions.NoSuchKey:
            pass
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        client.put_object(Bucket=bucket, Key="drift/last_trigger.json", Body=json.dumps({"at": now}).encode())
        return True

    trigger = trigger_dagrun.TriggerDagRunOperator(
        task_id="trigger_retraining",
        trigger_dag_id="credit_scoring_retraining",
        conf={"reason": "drift"},
    )

    drift_requires_retraining() >> trigger
