"""Cache operations compatible with a Redis/Valkey proxy spanning hash slots."""

from flask_caching.backends.rediscache import RedisCache


class ClusterCompatibleRedisCache(RedisCache):
    def get_many(self, *keys):
        # Serverless Valkey rejects cross-slot MGET. Independent GET commands
        # preserve key placement, serialization, ordering and missing values.
        pipeline = self._read_client.pipeline(transaction=False)
        for key in keys:
            pipeline.get(self.key_prefix + key)
        return [self.serializer.loads(value) for value in pipeline.execute()]
