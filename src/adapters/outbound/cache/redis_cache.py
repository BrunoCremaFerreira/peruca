from domain.ports.outbound.cache_outbound_port import CacheOutboundPort
import redis
from redis import Redis


class RedisCache(CacheOutboundPort):
    """
    Implementation of REDIS cache database

    :param connection_string: Connection string to the Redis server.
    """

    def __init__(self, connection_string: str):
        self._client: Redis = redis.from_url(connection_string)

    async def set_key(self, key: str, value: str):
        """
        Stores a value associated with a key.
        """
        return await self._client.set(key, value)

    async def get_key(self, key: str) -> str:
        """
        Retrieves the value associated with a key.
        """
        return str(await self._client.get(key))

    async def delete_key(self, key: str) -> bool:
        """
        Deletes a key from the cache.
        """
        return await self._client.delete(key)
