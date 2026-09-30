import os

from taskiq_redis import RedisStreamBroker

broker = RedisStreamBroker(url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
