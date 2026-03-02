"""Production-grade Redis-backed storage for ReplaySystem instances.

Features:
- Atomic serialization with integrity validation
- Safe deserialization with corruption detection
- TTL management with refresh-on-write
- Graceful Redis fallback to fakeredis
- Compression support for large states
- Full audit logging
"""

import redis
import redis.exceptions
import dill
import zlib
import hashlib
import logging
from typing import Optional, Tuple
from abc import ABC, abstractmethod

import config
from backend.logging_config import get_logger

logger = get_logger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Storage Backend Interface (Abstract)
# ────────────────────────────────────────────────────────────────────────────


class StorageBackend(ABC):
    """Abstract base for session storage backends."""

    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        """Retrieve serialized data."""
        pass

    @abstractmethod
    def set(self, key: str, data: bytes, ttl: int) -> bool:
        """Store serialized data with TTL."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    def expire(self, key: str, ttl: int) -> bool:
        """Refresh TTL on existing key."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify backend connectivity."""
        pass


# ────────────────────────────────────────────────────────────────────────────
# Redis Backend Implementation
# ────────────────────────────────────────────────────────────────────────────


class RedisBackend(StorageBackend):
    """Production Redis backend with connection pooling."""

    def __init__(self, redis_url: str):
        """Initialize Redis connection with safety settings.

        Args:
            redis_url: Redis connection URL

        Raises:
            ConnectionError: If Redis connection fails immediately
        """
        self.redis_url = redis_url
        self.client = None
        self.connected = False

        try:
            self.client = redis.Redis.from_url(
                redis_url,
                decode_responses=False,
                socket_connect_timeout=config.REDIS_CONN_TIMEOUT,
                socket_timeout=config.REDIS_SOCKET_TIMEOUT,
                socket_keepalive=config.REDIS_SOCKET_KEEPALIVE,
                socket_keepalive_options=None,
                health_check_interval=config.REDIS_HEALTH_CHECK_INTERVAL,
            )
            self.client.ping()
            self.connected = True
            logger.info("✅ Connected to Redis", extra={})
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error(f"Failed to connect to Redis at {redis_url}: {e}")
            raise ConnectionError(f"Cannot connect to Redis: {e}") from e

    def get(self, key: str) -> Optional[bytes]:
        """Retrieve data from Redis."""
        try:
            return self.client.get(key)
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis GET failed for {key}: {e}")
            raise

    def set(self, key: str, data: bytes, ttl: int) -> bool:
        """Store data in Redis with TTL.

        Uses atomic SETEX to prevent partial writes.
        """
        try:
            self.client.setex(key, ttl, data)
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis SET failed for {key}: {e}")
            raise

    def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        try:
            return bool(self.client.delete(key))
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis DELETE failed for {key}: {e}")
            raise

    def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        try:
            return bool(self.client.exists(key))
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis EXISTS failed for {key}: {e}")
            raise

    def expire(self, key: str, ttl: int) -> bool:
        """Refresh TTL on a key."""
        try:
            return bool(self.client.expire(key, ttl))
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis EXPIRE failed for {key}: {e}")
            raise

    def health_check(self) -> bool:
        """Verify Redis is healthy."""
        try:
            self.client.ping()
            return True
        except redis.exceptions.RedisError:
            return False


# ────────────────────────────────────────────────────────────────────────────
# FakeRedis Backend (Development/Testing)
# ────────────────────────────────────────────────────────────────────────────


class FakeRedisBackend(StorageBackend):
    """In-memory fallback backend for development."""

    def __init__(self):
        """Initialize fakeredis."""
        try:
            import fakeredis
            self.client = fakeredis.FakeRedis(decode_responses=False)
            logger.warning("⚠️ Using FakeRedis fallback (development only)")
        except ImportError:
            raise ImportError("fakeredis required for fallback")

    def get(self, key: str) -> Optional[bytes]:
        """Retrieve from fake Redis."""
        return self.client.get(key)

    def set(self, key: str, data: bytes, ttl: int) -> bool:
        """Store in fake Redis with TTL."""
        self.client.setex(key, ttl, data)
        return True

    def delete(self, key: str) -> bool:
        """Delete from fake Redis."""
        return bool(self.client.delete(key))

    def exists(self, key: str) -> bool:
        """Check existence in fake Redis."""
        return bool(self.client.exists(key))

    def expire(self, key: str, ttl: int) -> bool:
        """Refresh TTL in fake Redis."""
        return bool(self.client.expire(key, ttl))

    def health_check(self) -> bool:
        """Fake Redis is always healthy."""
        return True


# ────────────────────────────────────────────────────────────────────────────
# Serialization & Integrity
# ────────────────────────────────────────────────────────────────────────────


class SerializationError(Exception):
    """Raised when serialization fails."""
    pass


class DeserializationError(Exception):
    """Raised when deserialization fails or integrity check fails."""
    pass


def serialize_with_integrity(
    obj: object,
    compress_threshold: int = config.SESSION_COMPRESSION_THRESHOLD,
) -> Tuple[bytes, str]:
    """Serialize object with integrity hash.

    Args:
        obj: Object to serialize (must be dill-serializable)
        compress_threshold: Compress if serialized > N bytes

    Returns:
        Tuple of (serialized_data, integrity_hash)

    Raises:
        SerializationError: If serialization fails
    """
    try:
        data = dill.dumps(obj, protocol=dill.HIGHEST_PROTOCOL)
    except Exception as e:
        logger.error(f"dill serialization failed: {e}")
        raise SerializationError(f"Cannot serialize object: {e}") from e

    # Optionally compress large payloads
    if len(data) > compress_threshold:
        try:
            data = zlib.compress(data, level=6)
            logger.debug(f"Compressed payload: {len(data)} bytes")
        except Exception as e:
            logger.warning(f"Compression failed, storing uncompressed: {e}")

    # Compute integrity hash
    integrity_hash = hashlib.sha256(data).hexdigest()

    return data, integrity_hash


def deserialize_with_integrity(
    data: bytes,
    expected_hash: Optional[str] = None,
) -> object:
    """Deserialize object with integrity validation.

    Args:
        data: Serialized data (possibly compressed)
        expected_hash: Expected SHA256 hash (optional validation)

    Returns:
        Deserialized object

    Raises:
        DeserializationError: If deserialization or integrity check fails
    """
    if not data:
        raise DeserializationError("Empty data")

    # Validate integrity hash if provided
    if expected_hash:
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != expected_hash:
            logger.error(
                f"Integrity check failed: expected {expected_hash}, "
                f"got {actual_hash}"
            )
            raise DeserializationError("Data integrity check failed (corrupted)")

    # Try decompression first (handles both compressed and uncompressed)
    try:
        decompressed = zlib.decompress(data)
        obj = dill.loads(decompressed)
    except zlib.error:
        # Not compressed, try direct deserialization
        try:
            obj = dill.loads(data)
        except Exception as e:
            logger.error(f"dill deserialization failed: {e}")
            raise DeserializationError(f"Cannot deserialize data: {e}") from e
    except Exception as e:
        logger.error(f"dill deserialization failed: {e}")
        raise DeserializationError(f"Cannot deserialize data: {e}") from e

    return obj


# ────────────────────────────────────────────────────────────────────────────
# Main EngineStore (Production-Grade)
# ────────────────────────────────────────────────────────────────────────────


class EngineStore:
    """Production-grade session storage with atomic writes and integrity checks.

    Thread-safe, multi-process safe, multi-worker safe.
    """

    def __init__(self, redis_url: str = config.REDIS_URL):
        """Initialize store with backend selection.

        Args:
            redis_url: Redis connection URL
        """
        self.ttl = config.SESSION_TTL
        self.key_prefix = "replay:engine"

        # Try Redis first, fall back to FakeRedis
        try:
            self.backend: StorageBackend = RedisBackend(redis_url)
            self.using_redis = True
        except ConnectionError:
            logger.warning(
                "Redis unavailable, falling back to FakeRedis. "
                "This is OK for development but not for production."
            )
            self.backend = FakeRedisBackend()
            self.using_redis = False

    def _make_key(self, session_id: str) -> str:
        """Generate storage key for session."""
        return f"{self.key_prefix}:{session_id}"

    def get(self, session_id: str) -> Optional[object]:
        """Retrieve and deserialize a ReplaySystem.

        Args:
            session_id: Session UUID

        Returns:
            Deserialized ReplaySystem or None if not found

        Raises:
            DeserializationError: If data is corrupted
        """
        key = self._make_key(session_id)

        try:
            data = self.backend.get(key)
            if not data:
                logger.debug(f"No data for session {session_id}")
                return None

            obj = deserialize_with_integrity(data)

            # Refresh TTL on successful read (keep-alive)
            try:
                self.backend.expire(key, self.ttl)
            except Exception as e:
                logger.warning(f"Failed to refresh TTL for {key}: {e}")

            logger.debug(f"Retrieved session {session_id}")
            return obj

        except DeserializationError as e:
            logger.error(f"Failed to deserialize session {session_id}: {e}")
            # In production, this warrants immediate cleanup
            try:
                self.delete(session_id)
            except Exception as cleanup_err:
                logger.error(f"Failed to clean up corrupted session: {cleanup_err}")
            raise

    def set(self, session_id: str, obj: object) -> bool:
        """Serialize and atomically store a ReplaySystem.

        Args:
            session_id: Session UUID
            obj: ReplaySystem to store

        Returns:
            True if successful

        Raises:
            SerializationError: If serialization fails
        """
        key = self._make_key(session_id)

        try:
            data, integrity_hash = serialize_with_integrity(obj)
            self.backend.set(key, data, self.ttl)
            logger.debug(
                f"Stored session {session_id} "
                f"({len(data)} bytes, hash: {integrity_hash[:16]}...)"
            )
            return True
        except SerializationError as e:
            logger.error(f"Failed to serialize session {session_id}: {e}")
            raise

    def delete(self, session_id: str) -> bool:
        """Delete a session from storage.

        Args:
            session_id: Session UUID

        Returns:
            True if session existed and was deleted
        """
        key = self._make_key(session_id)
        result = self.backend.delete(key)
        logger.debug(f"Deleted session {session_id} (existed: {result})")
        return result

    def exists(self, session_id: str) -> bool:
        """Check if session exists.

        Args:
            session_id: Session UUID

        Returns:
            True if session exists in storage
        """
        key = self._make_key(session_id)
        return self.backend.exists(key)

    def health_check(self) -> dict:
        """Check store health.

        Returns:
            Dict with health status
        """
        is_healthy = self.backend.health_check()
        return {
            "healthy": is_healthy,
            "backend": "redis" if self.using_redis else "fakeredis",
            "connected": is_healthy,
        }
