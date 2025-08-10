from domain.interfaces.repository import ContextRepository
from redis import Redis, from_url  # type: ignore


class RedisContextRepository(ContextRepository):
    """
    Implementation of REDIS cache database

    :param connection_string: Connection string to the Redis server.
    """

    def __init__(self, connection_string: str):
        self._connection_string = connection_string
        self._client: Redis
    
    def connect(self):
        self._client = from_url(self._connection_string)

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
