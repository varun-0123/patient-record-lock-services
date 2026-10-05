# lock_manager.py
import uuid
import redis
from typing import Dict, Tuple, Optional

# Release lock only if owner token matches
RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Extend TTL only if owner token matches
RENEW_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
"""

class DistributedLockManager:
    def __init__(self, redis_client: redis.Redis, default_ttl_ms: int = 30000):
        self.redis = redis_client
        self.default_ttl_ms = default_ttl_ms
        try:
            self._release_script = self.redis.register_script(RELEASE_LUA)
            self._renew_script = self.redis.register_script(RENEW_LUA)
            self._has_lua = True
        except Exception:
            self._has_lua = False

    def _lock_key(self, patient_id: str, section: Optional[str] = None) -> str:
        if section:
            return f"lock:patient:{patient_id}:section:{section}"
        return f"lock:patient:{patient_id}:global"

    # --- PESSIMISTIC LOCKING ---

    def acquire_pessimistic(self, patient_id: str, user_id: str, section: Optional[str] = None, ttl_ms: Optional[int] = None) -> Optional[str]:
        key = self._lock_key(patient_id, section)
        ttl = ttl_ms or self.default_ttl_ms
        token = f"{user_id}:{uuid.uuid4()}"
        acquired = self.redis.set(key, token, nx=True, px=ttl)
        return token if acquired else None

    def renew_pessimistic(self, patient_id: str, token: str, section: Optional[str] = None, ttl_ms: Optional[int] = None) -> bool:
        key = self._lock_key(patient_id, section)
        ttl = ttl_ms or self.default_ttl_ms
        
        if self._has_lua:
            try:
                return self._renew_script(keys=[key], args=[token, ttl]) == 1
            except Exception:
                pass
        
        # Fallback if Lua / evalsha is unavailable
        val = self.redis.get(key)
        if val and (val == token or val.decode("utf-8", errors="ignore") == token):
            return bool(self.redis.pexpire(key, ttl))
        return False

    def release_pessimistic(self, patient_id: str, token: str, section: Optional[str] = None) -> bool:
        key = self._lock_key(patient_id, section)
        
        if self._has_lua:
            try:
                return self._release_script(keys=[key], args=[token]) == 1
            except Exception:
                pass
        
        # Fallback if Lua / evalsha is unavailable
        val = self.redis.get(key)
        if val and (val == token or val.decode("utf-8", errors="ignore") == token):
            return bool(self.redis.delete(key))
        return False

    def get_lock_holder(self, patient_id: str, section: Optional[str] = None) -> Optional[str]:
        val = self.redis.get(self._lock_key(patient_id, section))
        if val:
            decoded = val.decode("utf-8", errors="ignore") if isinstance(val, bytes) else str(val)
            return decoded.split(":")[0]
        return None

    # --- OPTIMISTIC CONCURRENCY / VERSION VECTORS ---

    @staticmethod
    def validate_and_advance_vector(
        current_vector: Dict[str, int], 
        client_vector: Dict[str, int], 
        modified_sections: list
    ) -> Tuple[bool, Optional[str], Dict[str, int]]:
        new_vector = dict(current_vector)

        for sec in modified_sections:
            server_ver = current_vector.get(sec, 0)
            client_ver = client_vector.get(sec, 0)

            if client_ver != server_ver:
                return False, f"Conflict on section '{sec}'. Expected version {server_ver}, received {client_ver}.", {}

            new_vector[sec] = server_ver + 1

        return True, None, new_vector