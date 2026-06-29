"""History service — exposes YAML generation history for querying."""
from typing import Optional
from core.repositories.interfaces import IHistoryRepository


class HistoryService:
    def __init__(self, history_repo: IHistoryRepository) -> None:
        self._history_repo = history_repo

    def list_recent(self, limit: int = 50) -> list[dict]:
        return self._history_repo.list_recent(limit)

    def get(self, entry_id: str) -> Optional[dict]:
        return self._history_repo.get(entry_id)
