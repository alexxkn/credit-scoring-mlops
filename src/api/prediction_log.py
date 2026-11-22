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

    def get(self, version, record):
        if self.client is None:
            return None
        try:
            value = self.client.get(self.key(version, record))
        except redis.RedisError as error:
            logger.warning("redis cache read failed: %s", error)
            return None
        return None if value is None else float(value)

    def put(self, version, record, probability):
        if self.client is None:
            return
        try:
            self.client.set(self.key(version, record), probability, ex=settings.CACHE_TTL_SECONDS)
        except redis.RedisError as error:
            logger.warning("redis cache write failed: %s", error)

    def append(self, request_id, version, record, probability):
        # Журнал запросов нужен мониторингу дрифта: он сравнивает признаки и предсказания с обучающей выборкой
        if self.client is None:
            return
        fields = {"request_id": request_id, "ts": time.time(), "model_version": version, "features": json.dumps(record), "probability": probability}
        try:
            self.client.xadd(settings.PREDICTION_STREAM, fields, maxlen=settings.PREDICTION_STREAM_MAXLEN, approximate=True)
        except redis.RedisError as error:
            logger.warning("redis stream write failed: %s", error)

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
