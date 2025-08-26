"""
State Manager for Mock API
Handles object lifecycle and relationships
"""
from typing import Dict, Any, List, Optional
import uuid
import json
from datetime import datetime

class StateManager:
    """Manages stateful objects across API operations"""

    def __init__(self, db, redis_client):
        self.db = db
        self.redis = redis_client
        self.repositories = {}
        self.pending_changes = []

    def create(self, object_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new object instance"""
        if 'id' not in data:
            data['id'] = str(uuid.uuid4())

        # Store in appropriate repository
        repo = self._get_repository(object_type)
        obj = repo.create(data)

        # Track for relationships and side effects
        self.pending_changes.append(('create', object_type, obj))

        # Cache in Redis for fast access
        self._cache_object(object_type, obj['id'], obj)

        return obj

    def read(self, object_type: str, object_id: str) -> Optional[Dict[str, Any]]:
        """Read an object by ID"""
        # Try cache first
        cached = self._get_cached_object(object_type, object_id)
        if cached:
            return cached

        # Fall back to repository
        repo = self._get_repository(object_type)
        obj = repo.get(object_id)

        if obj:
            self._cache_object(object_type, object_id, obj)

        return obj

    def update(self, object_type: str, object_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an existing object"""
        repo = self._get_repository(object_type)
        obj = repo.update(object_id, data)

        if obj:
            self.pending_changes.append(('update', object_type, obj))
            self._cache_object(object_type, object_id, obj)

        return obj

    def delete(self, object_type: str, object_id: str, cascade: bool = True) -> bool:
        """Delete an object, optionally cascading"""
        repo = self._get_repository(object_type)

        if cascade:
            # Handle cascade deletes based on relationships
            self._handle_cascade_delete(object_type, object_id)

        success = repo.delete(object_id)

        if success:
            self.pending_changes.append(('delete', object_type, object_id))
            self._remove_from_cache(object_type, object_id)

        return success

    def query(self, object_type: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Query objects with optional filters"""
        repo = self._get_repository(object_type)
        return repo.query(filters)

    def commit(self):
        """Process pending changes and trigger side effects"""
        for change_type, object_type, data in self.pending_changes:
            self._trigger_side_effects(change_type, object_type, data)

        self.pending_changes = []
        self.db.session.commit()

    def _get_repository(self, object_type: str):
        """Get or create repository for object type"""
        if object_type not in self.repositories:
            from repositories.base import BaseRepository
            self.repositories[object_type] = BaseRepository(object_type, self.db)
        return self.repositories[object_type]

    def _cache_object(self, object_type: str, object_id: str, obj: Dict[str, Any]):
        """Cache object in Redis"""
        key = f"{object_type}:{object_id}"
        self.redis.set(key, json.dumps(obj), ex=3600)  # 1 hour TTL

    def _get_cached_object(self, object_type: str, object_id: str) -> Optional[Dict[str, Any]]:
        """Get object from cache"""
        key = f"{object_type}:{object_id}"
        data = self.redis.get(key)
        return json.loads(data) if data else None

    def _remove_from_cache(self, object_type: str, object_id: str):
        """Remove object from cache"""
        key = f"{object_type}:{object_id}"
        self.redis.delete(key)

    def _handle_cascade_delete(self, object_type: str, object_id: str):
        """Handle cascade deletes based on relationships"""
        # This will be enhanced by the orchestrator based on detected relationships
        pass

    def _trigger_side_effects(self, change_type: str, object_type: str, data):
        """Trigger side effects for state changes"""
        # This will be enhanced based on detected side effects
        pass
