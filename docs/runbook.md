# Runbook: реагирование на алерты

Алерты приходят в Telegram (@mifiroboalertbot) из Alertmanager. В каждом сообщении есть ссылка на раздел этого документа.

Доступ к кластеру и интерфейсам:

```bash
source ~/.config/vkcs/credit-scoring.env
export KUBECONFIG=~/.kube/credit-scoring-prod.yaml
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
kubectl -n monitoring port-forward svc/kube-prometheus-stack-alertmanager 9093:9093
kubectl -n mlops port-forward svc/airflow-api-server 8080:8080
```

Дашборды Grafana: Credit Scoring API, Credit Scoring: дрифт и качество модели, Credit Scoring: логи.

Общий порядок: подтвердить, что алерт настоящий (дашборд, логи), оценить влияние на клиентов, восстановить сервис (откат, масштабирование), после этого искать причину. Откат всегда безопаснее починки на ходу.

## CreditApiDown

Prometheus не может собрать метрики ни с одного пода API в namespace. Клиенты, скорее всего, получают ошибки.

1. Поды и события:
   ```bash
   kubectl -n credit-scoring-prod get pods -l 'app in (credit-scoring-api-primary, credit-scoring-api)'
   kubectl -n credit-scoring-prod get events --sort-by=.lastTimestamp | tail -20
   ```
2. Под в CrashLoopBackOff: смотреть логи `kubectl -n credit-scoring-prod logs deploy/credit-scoring-api-primary -c api --previous`. Частая причина — модель по MODEL_URI не скачалась из S3 (ключи в секрете credit-scoring-secrets, версия в бакете mifirobo-prod-models).
3. Если сломала последняя выкатка — workflow rollback, mode=version, указать прошлый тег образа или версию модели.
4. Поды Pending: не хватает узлов. Проверить `kubectl get nodes` и группу app в Terraform (max_size), автоскейлер добавляет узел за 3–5 минут.

## CreditApiHighErrorRate

Больше 2% ответов 5xx за 5 минут.

1. Дашборд Credit Scoring: логи, панель «Ошибки и предупреждения»: текст исключения.
2. Если ошибки начались после выкатки и canary ещё идёт, Flagger откатит её сам. Если версия уже стала primary — rollback mode=version.
3. Ошибки при недоступном Redis не возникают: API работает без кеша. Если 5xx связаны с S3 или моделью, см. CreditApiDown, пункт 2.

## CreditApiHighLatency

p95 /predict выше 300 мс 10 минут. Нормальное значение — единицы миллисекунд.

1. Дашборд API: «Поды API», «CPU подов API». Если CPU у лимита 1 ядро, HPA должен добавить поды. Проверить `kubectl -n credit-scoring-prod get hpa`.
2. HPA упёрся в maxReplicas — поднять maxReplicas в deployment/kubernetes/base/api-hpa.yaml и выкатить.
3. Задержка без нагрузки по CPU: смотреть «Инференс ONNX, p95» и Redis (таймаут Redis 200 мс на каждый запрос, см. CreditRedisUnavailable).

## CreditDefaultRateShift

Доля прогнозов «дефолт» за час выросла в 1.5 раза к прошлым суткам. Это не ошибка сервиса: либо изменились клиенты, либо модель.

1. Дашборд дрифта: есть ли дрифт признаков и вероятностей.
2. Если менялась модель (поле model_version на дашборде API) — сравнить с прошлой версией, при сомнениях откатить модель (rollback mode=version, model_version).
3. Если сдвинулись входные данные — согласовать с бизнесом, переобучение запустится по дрифту само (DAG credit_scoring_drift_trigger).

## CreditApiPodRestarting

Под API перезапустился больше 2 раз за 30 минут.

1. `kubectl -n credit-scoring-prod describe pod <pod>`: причина последнего завершения. OOMKilled — поднять limits.memory, сейчас 512 МБ.
2. Liveness-проба не проходит — смотреть логи пода перед рестартом (`--previous`).

## CreditDataDrift

Evidently нашёл дрифт: признаков больше 10% или распределение вероятностей сдвинулось. Влияние на клиентов не сразу.

1. Дашборд дрифта: какие признаки сдвинулись. HTML-отчёт Evidently лежит в бакете mifirobo-prod-reports, drift/<время>/drift_report.html.
2. Сдвиг одного-двух признаков из-за ошибки выгрузки (например, сумма в другой валюте) лечится на стороне источника, а не переобучением.
3. Настоящее изменение клиентов: DAG credit_scoring_drift_trigger запустит переобучение в течение часа (не чаще раза в сутки). Можно запустить вручную в Airflow: DAG credit_scoring_retraining, conf {"reason": "drift"}.

## CreditConceptDrift

ROC-AUC на запросах с известным исходом (/feedback) упал больше чем на 0.05 к тестовой выборке. Модель хуже различает клиентов, решения о выдаче ухудшаются.

1. Дашборд дрифта: «Качество на размеченных ответах», сколько размеченных ответов в окне (credit_labeled_rows). На нескольких десятках ответов ROC-AUC шумный.
2. Если работает A/B-тест, сравнить версии по credit_model_roc_auc_by_version.
3. Запустить переобучение (как в CreditDataDrift, пункт 3). Новая модель выкатится только если на свежих данных лучше текущей, и пройдёт canary.

## CreditDriftMonitorStale

CronJob drift-monitor не отправлял метрики больше 2 часов, дрифт не контролируется.

1. `kubectl -n credit-scoring-prod get cronjob,jobs -l app=drift-monitor` и логи последнего job.
2. Частые причины: в журнале Redis меньше 200 записей (job пишет skipped и метрики не шлёт), нет доступа к S3 или Pushgateway.

## CreditApiErrorLogs

Алерт Loki: в логах API больше 10 записей уровня ERROR за 5 минут. Срабатывает раньше, чем доля 5xx, если ошибки в фоне (запись в журнал, кеш).

1. Дашборд Credit Scoring: логи, панель «Ошибки и предупреждения».
2. Дальше по тексту ошибки, как в CreditApiHighErrorRate.

## CreditRedisUnavailable

Алерт Loki: API пишет предупреждения о недоступном Redis. API продолжает отвечать без кеша, но журнал предсказаний для мониторинга дрифта и /feedback не пишутся.

1. `kubectl -n credit-scoring-prod get pods -l app=redis`, логи Redis.
2. Под Redis не запускается из-за диска — проверить PVC data-redis-0.
3. После восстановления данных за период простоя в журнале не будет, отчёт о дрифте за этот период строится по меньшему окну.
