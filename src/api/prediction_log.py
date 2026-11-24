import hashlib
import json
import logging
import time

import redis

import src.api.settings as settings

logger = logging.getLogger("credit_api")


class PredictionLog:
    """Кеш предсказаний и журнал запросов в Redis. Без REDIS_URL всё отключено, сервис работает и без Redis."""

    def __init__(self, url):
        self.client = redis.Redis.from_url(url, socket_timeout=0.2, socket_connect_timeout=0.2) if url else None

    @staticmethod
    def key(version, record):
        digest = hashlib.sha1(json.dumps(record, sort_keys=True).encode()).hexdigest()
        return f"pred:{version}:{digest}"

    # Все записи запроса идут одним MGET и одним pipeline: по обращению на клиента батч из 100 клиентов ждал Redis 300 раз
    def get_many(self, version, records):
        if self.client is None:
            return [None] * len(records)
        try:
            values = self.client.mget([self.key(version, record) for record in records])
        except redis.RedisError as error:
            logger.warning("redis cache read failed: %s", error)
            return [None] * len(records)
        return [None if value is None else float(value) for value in values]

    def write(self, version, computed, journal):
        """computed — пары (признаки, вероятность) для кеша, journal — тройки (request_id, признаки, вероятность) для журнала дрифта."""
        if self.client is None or not (computed or journal):
            return
        pipeline = self.client.pipeline(transaction=False)
        for record, probability in computed:
            pipeline.set(self.key(version, record), probability, ex=settings.CACHE_TTL_SECONDS)
        # Журнал запросов нужен мониторингу дрифта: он сравнивает признаки и предсказания с обучающей выборкой
        for request_id, record, probability in journal:
            fields = {"request_id": request_id, "ts": time.time(), "model_version": version, "features": json.dumps(record), "probability": probability}
            pipeline.xadd(settings.PREDICTION_STREAM, fields, maxlen=settings.PREDICTION_STREAM_MAXLEN, approximate=True)
        try:
            pipeline.execute()
        except redis.RedisError as error:
            logger.warning("redis write failed: %s", error)

    def feedback(self, request_id, actual):
        if self.client is None:
            return False
        self.client.hset("feedback", request_id, actual)
        return True

    def ping(self):
        if self.client is None:
            return True
        try:
            return bool(self.client.ping())
        except redis.RedisError:
            return False
