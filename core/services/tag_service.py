"""
Tag service — business logic for dynamic tag definition management.

Tags are scoped to one or more entity types ("devices", "bandwidth",
"subnets").  The service validates scope values and delegates persistence
and usage-count queries to the tag repository.
"""
from typing import Optional

from core.repositories.interfaces import ITagRepository, IAuditRepository

# Valid scope identifiers — any other value is rejected at service layer.
TAG_SCOPES: tuple[str, ...] = ("devices", "bandwidth", "subnets")


class TagService:
    """Orchestrates tag definition CRUD with scope validation and audit logging."""

    # Expose as a class constant so callers (e.g. the HTTP handler) can
    # reference the canonical set without importing from the repository layer.
    TAG_SCOPES: tuple[str, ...] = TAG_SCOPES

    def __init__(
        self,
        tag_repo: ITagRepository,
        audit_repo: IAuditRepository,
    ) -> None:
        self._tag_repo = tag_repo
        self._audit_repo = audit_repo

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_tags(self) -> list[dict]:
        return self._tag_repo.list_all()

    def get_tag(self, tag_id: str) -> Optional[dict]:
        return self._tag_repo.get(tag_id)

    def usage_count(self, tag_id: str) -> int:
        """Total records with a non-empty value for this tag (any scope)."""
        return self._tag_repo.usage_count(tag_id)

    def value_usage_count(self, tag_id: str, value: str) -> int:
        """Records with exactly *value* set for this tag (any scope)."""
        return self._tag_repo.value_usage_count(tag_id, value)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def create_or_update(self, tag_def: dict, actor: Optional[str]) -> dict:
        """Validate and persist a tag definition.

        Raises
        ------
        ValueError
            When the tag name is blank or any scope identifier is invalid.
        """
        if not tag_def.get("name", "").strip():
            raise ValueError("tag name is required")
        invalid_scopes = [
            s for s in tag_def.get("scopes", []) if s not in TAG_SCOPES
        ]
        if invalid_scopes:
            raise ValueError(f"invalid scope(s): {invalid_scopes}")

        is_create = not tag_def.get("id")
        saved = self._tag_repo.upsert(tag_def)
        self._audit_repo.log(
            actor,
            "create_tag" if is_create else "update_tag",
            {"id": saved["id"], "name": saved.get("name")},
        )
        return saved

    def delete(
        self,
        tag_id: str,
        actor: Optional[str],
        force: bool = False,
    ) -> dict:
        """Delete a tag definition.

        Returns a result dict with ``deleted`` and ``dependents_forced``
        keys.  When *force* is False and there are active dependents the
        caller should surface this to the user (HTTP layer returns 409).

        Raises
        ------
        TagInUseError
            When *force* is False and the tag has active dependents.
        """
        dependents = self._tag_repo.usage_count(tag_id)
        if dependents > 0 and not force:
            raise TagInUseError(tag_id, dependents)
        self._tag_repo.delete(tag_id)
        self._audit_repo.log(
            actor,
            "delete_tag",
            {"id": tag_id, "dependents_forced": dependents if force else 0},
        )
        return {"deleted": tag_id, "dependents_forced": dependents if force else 0}


class TagInUseError(Exception):
    """Raised when attempting to delete a tag that still has active dependents."""

    def __init__(self, tag_id: str, dependents: int) -> None:
        super().__init__(f"tag '{tag_id}' is in use by {dependents} record(s)")
        self.tag_id = tag_id
        self.dependents = dependents
