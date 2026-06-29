"""Audit service — exposes the append-only audit log for querying."""
from core.repositories.interfaces import IAuditRepository


class AuditService:
    def __init__(self, audit_repo: IAuditRepository) -> None:
        self._audit_repo = audit_repo

    def list_recent(self, limit: int = 100) -> list[dict]:
        return self._audit_repo.list_recent(limit)
