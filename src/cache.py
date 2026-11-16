import json
import logging

import fakeredis

logger = logging.getLogger(__name__)


class MovieCache:
    def __init__(self):
        self.client = fakeredis.FakeRedis(decode_responses=True)

    def make_key(self, limit):
        return f"movies:limit:{limit}"

    def get(self, limit):
        """Return the cached response dictionary, or None."""
        key = self.make_key(limit)
        value = self.client.get(key)
        if value is None:
            logger.debug(f"Cache MISS: {key}")
            return None
        logger.debug(f"Cache HIT: {key}")
        return json.loads(value)

    def set(self, limit, response):
        """Cache the response dictionary for 90 seconds."""
        key = self.make_key(limit)
        self.client.set(key, json.dumps(response), ex=90)

    def invalidate(self):
        """Remove all cached movie retrievals."""
        self.client.flushdb()
        logger.debug("Invalidated movie cache")