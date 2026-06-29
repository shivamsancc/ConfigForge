"""
Abstract repository interfaces for all ConfigForge persistence entities.

Each interface defines the full persistence contract for one domain aggregate,
independent of the underlying storage technology.  Concrete implementations
live in core/repositories/sqlite/.

Programming against these interfaces (rather than concrete classes) allows:
- Unit-testing services with lightweight mock/stub repositories
- Future database backend support (PostgreSQL, MySQL, SQL Server, etc.)
- Clean separation: services never know which database they are talking to

Naming convention
-----------------
Interfaces are prefixed with ``I`` to distinguish them from concrete classes
and to make dependency injection signatures self-documenting at a glance.
"""
from abc import ABC, abstractmethod
from typing import Optional


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

class IDeviceRepository(ABC):
    """CRUD and bulk-operations for device records."""

    @abstractmethod
    def list_all(self) -> list[dict]:
        """Return all device records ordered by insertion time (oldest first)."""
        ...

    @abstractmethod
    def get(self, device_id: str) -> Optional[dict]:
        """Return a single device by ID, or None if it does not exist."""
        ...

    @abstractmethod
    def upsert(self, device: dict) -> dict:
        """Insert or update a device.  Assigns an ID if one is not present.
        Returns the saved record (with ID populated)."""
        ...

    @abstractmethod
    def delete(self, device_id: str) -> None:
        """Delete a device by ID.  No-op if the device does not exist."""
        ...

    @abstractmethod
    def replace_all(self, devices: list[dict]) -> None:
        """Delete all existing devices and insert the provided list atomically."""
        ...

    @abstractmethod
    def merge(self, devices: list[dict]) -> None:
        """Upsert each device in the list without touching unreferenced records."""
        ...


# ---------------------------------------------------------------------------
# Bandwidth caps
# ---------------------------------------------------------------------------

class IBandwidthRepository(ABC):
    """CRUD and bulk-operations for bandwidth cap records."""

    @abstractmethod
    def list_all(self) -> list[dict]:
        ...

    @abstractmethod
    def get(self, row_id: str) -> Optional[dict]:
        ...

    @abstractmethod
    def upsert(self, row: dict) -> dict:
        ...

    @abstractmethod
    def delete(self, row_id: str) -> None:
        ...

    @abstractmethod
    def replace_all(self, rows: list[dict]) -> None:
        ...

    @abstractmethod
    def merge(self, rows: list[dict]) -> None:
        ...


# ---------------------------------------------------------------------------
# Subnets
# ---------------------------------------------------------------------------

class ISubnetRepository(ABC):
    """CRUD and bulk-operations for subnet (CIDR) records."""

    @abstractmethod
    def list_all(self) -> list[dict]:
        ...

    @abstractmethod
    def get(self, row_id: str) -> Optional[dict]:
        ...

    @abstractmethod
    def upsert(self, row: dict) -> dict:
        ...

    @abstractmethod
    def delete(self, row_id: str) -> None:
        ...

    @abstractmethod
    def replace_all(self, rows: list[dict]) -> None:
        ...

    @abstractmethod
    def merge(self, rows: list[dict]) -> None:
        ...

    @abstractmethod
    def find_for_ip(self, ip_str: str, subnets: Optional[list[dict]] = None) -> Optional[dict]:
        """Return the most-specific subnet (longest prefix) that contains ip_str,
        or None.  Accepts an optional pre-loaded subnet list to avoid a
        redundant DB read when the caller already has one."""
        ...


# ---------------------------------------------------------------------------
# Tag definitions
# ---------------------------------------------------------------------------

class ITagRepository(ABC):
    """CRUD for dynamic tag definitions."""

    @abstractmethod
    def list_all(self) -> list[dict]:
        ...

    @abstractmethod
    def get(self, tag_id: str) -> Optional[dict]:
        ...

    @abstractmethod
    def upsert(self, tag_def: dict) -> dict:
        """Insert or update a tag definition.  Assigns an ID if absent.
        Expected shape: {id?, name, scopes: [...], values: [...]}"""
        ...

    @abstractmethod
    def delete(self, tag_id: str) -> None:
        ...

    @abstractmethod
    def usage_count(self, tag_id: str) -> int:
        """Total number of records (across all scopes this tag applies to)
        that currently have a non-empty value set for this tag."""
        ...

    @abstractmethod
    def value_usage_count(self, tag_id: str, value: str) -> int:
        """How many records currently have this exact value set for this tag."""
        ...


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class IAuditRepository(ABC):
    """Append-only audit log."""

    @abstractmethod
    def log(self, actor: Optional[str], action: str, details=None) -> str:
        """Append an audit entry.  Returns the new entry's UUID."""
        ...

    @abstractmethod
    def list_recent(self, limit: int = 100) -> list[dict]:
        """Return the *limit* most-recent entries, newest first."""
        ...


# ---------------------------------------------------------------------------
# YAML generation history
# ---------------------------------------------------------------------------

class IHistoryRepository(ABC):
    """Append-only YAML generation history."""

    @abstractmethod
    def save(self, actor: Optional[str], summary: str, files: dict) -> str:
        """Persist a generation snapshot.  Returns the new entry's UUID."""
        ...

    @abstractmethod
    def list_recent(self, limit: int = 50) -> list[dict]:
        """Return the *limit* most-recent entries, newest first (without files blob)."""
        ...

    @abstractmethod
    def get(self, entry_id: str) -> Optional[dict]:
        """Return a single history entry including its files blob, or None."""
        ...


# ---------------------------------------------------------------------------
# Fixed lists  (Collector Region only — see storage module-level docstring)
# ---------------------------------------------------------------------------

class IListRepository(ABC):
    """Managed dropdown lists.  Only Collector Region remains a fixed list."""

    @abstractmethod
    def get_all(self) -> dict:
        """Return {list_name: [items]} for every managed list."""
        ...

    @abstractmethod
    def set_list(self, list_name: str, items: list) -> None:
        """Replace the items for the named list."""
        ...


# ---------------------------------------------------------------------------
# Meta key-value store
# ---------------------------------------------------------------------------

class IMetaRepository(ABC):
    """Small key-value store (lastSavedAt, lastSavedBy, schema_version, …)."""

    @abstractmethod
    def get_kv(self, key: str) -> Optional[str]:
        """Return the stored string value for *key*, or None."""
        ...

    @abstractmethod
    def set_kv(self, key: str, value: str) -> None:
        """Upsert a single key-value pair."""
        ...
