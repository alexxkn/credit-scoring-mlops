# Кредитный скоринг: промышленное развёртывание с MLOps-циклом

Итоговый проект курса "Автоматизация процессов доставки и развёртывания моделей машинного обучения". Основа — PD-модель дефолта по кредитным картам из курса "Автоматизация процессов разработки и тестирования моделей машинного обучения" (данные UCI Default of Credit Card Clients, 30000 клиентов). Новая модель — нейросеть в ONNX, сервис работает в Managed Kubernetes VK Cloud, инфраструктура описана в Terraform, выкатка идёт через GitHub Actions, Istio и Flagger, мониторинг на Prometheus, Grafana и Loki, дрифт считает Evidently, переобучение запускает Airflow.

Архитектура и потоки данных: [docs/architecture.md](docs/architecture.md). Реакция на алерты: [docs/runbook.md](docs/runbook.md).

## Структура

```text
credit-scoring-mlops/
├── src/
│   ├── data/, features/           # загрузка, очистка, валидация Great Expectations, признаки (из курса 17)
│   ├── models/                    # nn.py, train_nn.py — нейросеть; onnx_conversion.py, optimize.py, benchmark.py; train.py — модели курса 17
│   ├── api/                       # FastAPI: app.py, seldon_app.py (протокол Seldon), model_store.py, prediction_log.py (Redis)
│   ├── monitoring/                # evidently_drift.py — data drift, concept drift, качество по версиям; drift.py — PSI из курса 17
│   └── pipelines/retrain.py       # переобучение и сравнение с production-моделью
├── airflow/dags/                  # DAG переобучения и DAG запуска по дрифту
├── infrastructure/                # Terraform: modules (network, kubernetes, storage, monitoring), environments (staging, production)
├── deployment/
│   ├── docker/                    # многостадийные Dockerfile: backend, frontend, trainer, drift, mlflow
│   ├── kubernetes/                # kustomize: base и overlays staging, production
│   ├── platform/                  # Istio, Flagger, gateway, права CI
│   ├── mlops/                     # MLflow и Airflow в кластере
│   ├── seldon/                    # Seldon Core: operator и SeldonDeployment
│   └── monitoring/dashboards/     # дашборды Grafana
├── .github/workflows/             # build-and-test, deploy-staging, deploy-production, canary-release, rollback, mirror-images
├── scripts/                       # deploy.sh, wait_canary.sh, smoke_test.sh, check_alerts.sh
├── loadtest/                      # Locust, генератор трафика с дрифтом
├── reports/                       # бенчмарки, нагрузочный тест, логи демонстраций (reports/demo)
├── notebooks/                     # EDA и эксперименты курса 17
├── docs/                          # архитектура, runbook
└── dvc.yaml, params.yaml          # стадии prepare, train, train_nn, convert_onnx, optimize
```

## Этап 1. Модель для продакшена

Подробный отчёт: [reports/performance.md](reports/performance.md).

- Нейросеть: MLP 40 → 128 → 64 → 1 на PyTorch (src/models/nn.py). Агрегаты платежей, масштабирование и one-hot находятся внутри графа, поэтому ONNX-модель принимает 23 исходных признака клиента и не нуждается в отдельной предобработке. ROC-AUC на тесте 0.7745, F1 0.525.
- Конвертация: src/models/onnx_conversion.py экспортирует модель и проверяет её на 6000 строках теста. Расхождение вероятностей с PyTorch 1.2e-07, при расхождении больше 1e-5 скрипт падает вместе со стадией DVC.
- Оптимизация (src/models/optimize.py): dynamic quantization int8 уменьшает модель в 2 раза и ускоряет батч 1024 на 22% при потере ROC-AUC 0.0014. Pruning 50% весов качество не меняет, но и не ускоряет: ONNX Runtime не пропускает нули в плотных матрицах.
- Инференс: ONNX Runtime в 5 раз быстрее PyTorch на одиночном запросе. GPU (RTX 3080 Ti) для этой модели медленнее CPU: копирование данных на карту дороже вычислений.
- Нагрузочный тест API (Locust, 200 пользователей): 1 CPU — 754 запроса/с, 2 CPU — 1362, 4 CPU — 2213. Вывод для продакшена: CPU-узлы, под с 1 vCPU, масштабирование подов через HPA.

```bash
dvc repro                                # данные, модели курса 17, нейросеть, ONNX, оптимизация
python -m src.models.benchmark           # reports/benchmark.md
./loadtest/run_local.sh 2                # нагрузочный тест образа backend с лимитом 2 CPU
```

## Этап 2. Инфраструктура как код

Terraform, провайдер vkcs, VK Cloud. State хранится в Object Storage (backend s3 с блокировкой use_lockfile).

- modules/network: сеть и подсеть узлов на SDN sprut, роутер с выходом наружу. У узлов нет публичных адресов.
- modules/kubernetes: Managed Kubernetes 1.35. Группы узлов: app (STD3-4-8, автомасштабирование от 2 до 6) и system (STD3-4-16, от 1 до 2). Группа GPU включается переменной gpu_enabled. Gatekeeper-политики запрещают hostPath и host namespaces (кроме namespace monitoring) и NodePort. Доступ к API кластера ограничивается переменной api_allowed_cidrs.
- modules/storage: managed PostgreSQL 16 в приватной сети за security group (порт 5432 открыт только из подсети узлов и сети подов), отдельный S3-аккаунт сервисов, приватные бакеты mlflow, models, loki, reports.
- modules/monitoring: helm-релизы kube-prometheus-stack, Loki, Alloy, Pushgateway, правила алертов, дашборды.
- environments/production развёрнут. environments/staging собирается из тех же модулей с меньшими размерами и проверяется terraform validate в CI. Staging работает в production-кластере отдельным namespace, второй кластер удвоил бы стоимость.

```bash
./infrastructure/scripts/tf.sh production init
./infrastructure/scripts/tf.sh production apply
```

tf.sh берёт логин VK Cloud, токен Telegram-бота и ключи S3 для state из ~/.config/vkcs/credit-scoring.env, в репозитории секретов нет.

## Этап 3. Контейнеры и Kubernetes

- Образы собираются многостадийно (deployment/docker): backend (FastAPI + ONNX Runtime, около 330 МБ), frontend (сборка на node, работа на nginx-unprivileged), trainer, drift, mlflow.
- DVC внутри сборки: стадия model выполняет dvc pull и забирает модель нужной версии из S3. Ключи передаются как build secret и не остаются в слоях образа.
- Манифесты (deployment/kubernetes, kustomize):
  - Deployment API со стратегией rolling update (maxSurge 1, maxUnavailable 0), пробами, readOnlyRootFilesystem и запуском без root;
  - HPA по CPU (2–8 подов), PodDisruptionBudget, распределение подов по узлам;
  - ConfigMap с настройками и Secret с ключами S3 (секрет создаёт CI);
  - Service, Ingress (staging) и VirtualService (production);
  - NetworkPolicy: входящий трафик по умолчанию запрещён;
  - Redis для кеша и журнала предсказаний, CronJob мониторинга дрифта.

## Этап 4. CI/CD

GitHub Actions, цепочка build → test → deploy → monitor:

- build-and-test: линтеры (flake8, black, terraform fmt/validate, kubeconform, shellcheck) на каждый push; тесты, валидация данных, Trivy (зависимости, секреты, ошибки конфигурации) и сборка образов с проверкой Trivy — на pull request и в main. Trivy уже останавливал выкатку из-за критической CVE в пакетах nginx.
- deploy-staging: выкатка в namespace credit-scoring-staging. Flagger ведёт blue-green с зеркалированием трафика на новую версию, после переключения идут smoke-тесты через Ingress.
- deploy-production: ручное подтверждение в окружении production, затем canary (10% → 50% трафика шагами по 10%). Этап monitor запускает smoke-тесты и через 5 минут проверяет, что в Prometheus нет критических алертов.
- canary-release: выкатка новой версии модели из S3 без пересборки образа.
- rollback: abort прерывает идущую выкатку, version возвращает прежний образ или модель.

Автоматический откат: Flagger на каждом шаге проверяет долю успешных ответов, задержку, долю 5xx по метрикам API и долю прогнозов дефолта. Последняя метрика ловит сломанную модель, которая отвечает без ошибок, но всем одно и то же. Две проваленные проверки подряд возвращают весь трафик на primary.

Секреты репозитория: KUBECONFIG_B64 (токен ServiceAccount ci-deployer с правами только на два namespace), APP_S3_ACCESS_KEY и APP_S3_SECRET_KEY, DVC_AWS_ACCESS_KEY_ID и DVC_AWS_SECRET_ACCESS_KEY. Переменная INGRESS_HOST.

## Этап 5. Мониторинг

- Prometheus собирает метрики API (запросы, задержка, время инференса, прогнозы по версиям модели, кеш), Envoy, узлов и kube-state-metrics.
- Loki и Alloy собирают JSON-логи подов.
- Дашборды Grafana: Credit Scoring API, дрифт и качество модели, логи.
- Алерты: 8 правил Prometheus (недоступность API, 5xx, задержка, рестарты, сдвиг доли дефолтов, data drift, concept drift, остановка мониторинга дрифта) и 2 правила Loki (ошибки в логах, недоступность Redis). Уведомления приходят в Telegram, в каждом есть ссылка на раздел runbook.

## Этап 6. Дрифт и управление моделями

- Журнал: API пишет признаки, вероятность и версию модели каждого запроса в Redis stream. Факт дефолта приходит позже через POST /feedback.
  Запросы с заголовком X-Synthetic (проверки Flagger, нагрузочные тесты) в журнал не попадают, иначе одинаковые тестовые клиенты дают ложный дрифт.
- CronJob drift-monitor раз в час запускает src/monitoring/evidently_drift.py:
  - Evidently DataDriftPreset по 23 признакам и по вероятности;
  - concept drift — падение ROC-AUC на размеченных ответах больше чем на 0.05;
  - ROC-AUC отдельно по каждой версии модели.

  Метрики уходят в Pushgateway, HTML-отчёт — в S3.
- A/B-тест через Istio: на хосте ab.* трафик делится 50/50 между nn-v1 и квантованной nn-v1-int8, вариант можно выбрать заголовком x-model-variant.
- Seldon Core 1.17.1 (deployment/seldon) — одна SeldonDeployment с тремя предикторами: main (nn-v1, 90%), challenger (nn-v1-int8, 10%) и shadow (получает копию всех запросов, его ответы клиенту не уходят).
- Реестр моделей — MLflow. Версии лежат в S3 (mifirobo-prod-models/<версия>/), текущая production-версия записана в production.json.

## Этап 7. Переобучение и масштабирование

- DAG credit_scoring_retraining (раз в неделю или по триггеру):
  1. проверка отчёта о дрифте;
  2. под trainer: обучение на исходных данных и размеченных ответах из журнала, проверка ONNX, сравнение с production-моделью на одних и тех же данных, запись в MLflow;
  3. если ROC-AUC кандидата выше production-модели меньше чем на 0.01 (разброс метрики на проверочной выборке около 0.006), DAG останавливается;
  4. иначе меняет MODEL_URI у Deployment, Flagger ведёт canary, после продвижения DAG обновляет production.json.
- Логи задач Airflow хранятся в S3 (mifirobo-prod-reports/airflow-logs): под воркера KubernetesExecutor удаляется после задачи.
- DAG credit_scoring_drift_trigger раз в час читает последний отчёт о дрифте и при дрифте запускает переобучение, не чаще раза в сутки.
- Масштабирование: HPA подов API, автомасштабирование группы узлов app, кеш предсказаний в Redis (TTL 1 час).
- Геореплика сведена к распределению подов по узлам (topologySpreadConstraints) и PDB. Standard-кластер VK Cloud ставит все узлы в одну зону, для нескольких зон нужен regional-кластер.

## Развёртывание с нуля

```bash
./infrastructure/scripts/tf.sh production apply      # сеть, кластер, PostgreSQL, бакеты, мониторинг
./deployment/platform/install.sh                     # Istio, Flagger, gateway, права CI
AIRFLOW_ADMIN_PASSWORD=... ./deployment/mlops/install.sh   # MLflow, Airflow
```

Дальше push в main: CI собирает образы и выкатывает staging, а после подтверждения и production. Seldon ставится после первой выкатки в production: ./deployment/seldon/install.sh.

Сторонние образы узлы берут из зеркала в GHCR (workflow mirror-images): из VK Cloud образы Docker Hub качаются очень медленно и подвисают.

## Демонстрация работы

Логи и вывод команд лежат в reports/demo.

- Дрифт (drift-baseline.log, drift-shifted.log): 2000 обычных клиентов дрифта не дали (доля сдвинутых признаков 0, ROC-AUC на ответах 0.767 против 0.775 на тесте). Потом пришли 5000 клиентов со сдвигом: лимит ×0.6, просрочка PAY_0 +1, счёт ×1.3, и у 30% клиентов без просрочки факт дефолта подменён. Evidently нашёл ровно три сдвинутых признака (LIMIT_BAL, PAY_0, BILL_AMT1) и дрифт вероятностей, ROC-AUC упал до 0.557. Сработали алерты CreditDataDrift и CreditConceptDrift, уведомления ушли в Telegram.
- A/B (ab-test.txt): из 200 запросов 110 обработала nn-v1 и 90 — nn-v1-int8, заголовок x-model-variant выбирает вариант.
- Переобучение (retraining.txt): после сдвинутого трафика DAG credit_scoring_retraining обучил модель v20261123064833 на 28900 строках, из них 7000 размеченных ответов из журнала. На свежих данных кандидат лучше nn-v1: ROC-AUC 0.764 против 0.730. ONNX совпал с PyTorch (расхождение 1.2e-07), модель записана в реестр MLflow. Canary прошёл все шаги до 50%, Flagger перевёл модель в primary, DAG обновил production.json.
- Автономный цикл (auto-retraining.txt): ночью DAG credit_scoring_drift_trigger сам увидел дрифт и запустил переобучение, модель v20261124051643 прошла canary и стала production без участия человека. Прирост ROC-AUC при этом был 0.006 на тех же размеченных данных, то есть шум, и после этого порог продвижения поднят до 0.01. Заодно выяснилось, что дрифт в окне держался из-за синтетического трафика проверок Flagger, и такой трафик исключён из журнала.
- Откат (rollback.txt): canary-release с моделью nn-broken (порог 0, всем клиентам предсказывает дефолт). На шаге 10% метрика default-rate показала 1.00 при пороге 0.6, после двух неудачных проверок Flagger вернул весь трафик на прежнюю модель. Первая проверка выдаёт "no values found": метрики canary появляются в Prometheus не сразу, это нормально.
- Seldon (seldon.txt): из 200 запросов 183 обработал main и 17 — challenger, shadow получил все 200.

## Решения под VK Cloud

- Docker Hub и quay из VK Cloud отдают образы медленно, CRI-O качает их по очереди, и зависшее скачивание блокирует всю очередь. Поэтому сторонние образы копируются в GHCR.
- VK сам увеличил тип мастера, а Terraform пытался вернуть прежний и пересоздавал control plane. master_flavor вынесен в ignore_changes.
- VK Object Storage не поддерживает PutPublicAccessBlock, бакеты закрыты через ACL private. AWS provider 6.x отправляет пустой LocationConstraint, поэтому используется 5.x.
- Gatekeeper-политики кластера управляются из Terraform. node-exporter получил исключение для namespace monitoring.
- MLflow 3.18 по умолчанию запускает исполнитель фоновых задач (+1.6 ГБ памяти), он выключен: проекту он не нужен.

## Ограничения

- GPU-группа узлов описана, но не создавалась. GPU-бенчмарк снят на локальной RTX 3080 Ti, и GPU этой модели не нужен.
- Staging — namespace в production-кластере, а не отдельный кластер.
- Кластер standard, в одной зоне доступности.
