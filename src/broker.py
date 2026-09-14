from taskiq_redis import RedisStreamBroker
import docker

docker_client = docker.from_env()
broker = RedisStreamBroker(
    url="redis://redis:6379/0"
)