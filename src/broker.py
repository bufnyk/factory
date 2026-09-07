from taskiq_redis import RedisStreamBroker

broker = RedisStreamBroker(
    url="redis://redis:6379/0"
)