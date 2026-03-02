import redis
import dill
import config

class EngineStore:
    """Redis-backed store for serialized ReplaySystem instances."""
    
    def __init__(self, redis_url=config.REDIS_URL):
        try:
            self.r = redis.Redis.from_url(redis_url)
            self.r.ping()
            print(f"✅ Connected to Redis at {redis_url}")
        except Exception:
            import fakeredis
            self.r = fakeredis.FakeRedis()
            print("⚠️ Redis connection failed. Falling back to fakeredis for local state.")
        self.ttl = config.SESSION_TTL

    def _get_key(self, session_id):
        return f"engine_session:{session_id}"

    def get(self, session_id):
        """Retrieve a ReplaySystem from Redis."""
        key = self._get_key(session_id)
        data = self.r.get(key)
        if data:
            # Refresh TTL on access
            self.r.expire(key, self.ttl)
            return dill.loads(data)
        return None

    def set(self, session_id, replay_system):
        """Store a ReplaySystem in Redis."""
        key = self._get_key(session_id)
        data = dill.dumps(replay_system)
        self.r.setex(key, self.ttl, data)

    def delete(self, session_id):
        """Clear a session from Redis."""
        key = self._get_key(session_id)
        self.r.delete(key)

# Singleton instance
store = EngineStore()
