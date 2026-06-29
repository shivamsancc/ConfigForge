"""
Generate service — orchestrates YAML config generation.

Pulls all inventory data from repositories, runs the pure-logic conversion
and validation passes, persists a history snapshot, and writes an audit
entry.  Returns the full result dict that the HTTP route encodes as JSON.
"""
from typing import Optional

from core.logic import convert_to_collector_configs
from core.validator import validate_inventory
from core.repositories.interfaces import (
    IDeviceRepository,
    IBandwidthRepository,
    ISubnetRepository,
    ITagRepository,
    IHistoryRepository,
    IMetaRepository,
    IAuditRepository,
)
from core.repositories.sqlite.base import now_iso
from formats import yamldump


class GenerateService:
    """Orchestrates the full generate-and-save workflow."""

    def __init__(
        self,
        device_repo: IDeviceRepository,
        bandwidth_repo: IBandwidthRepository,
        subnet_repo: ISubnetRepository,
        tag_repo: ITagRepository,
        history_repo: IHistoryRepository,
        meta_repo: IMetaRepository,
        audit_repo: IAuditRepository,
    ) -> None:
        self._device_repo = device_repo
        self._bandwidth_repo = bandwidth_repo
        self._subnet_repo = subnet_repo
        self._tag_repo = tag_repo
        self._history_repo = history_repo
        self._meta_repo = meta_repo
        self._audit_repo = audit_repo

    def generate(self, actor: Optional[str]) -> dict:
        """Run config generation and return the result dict.

        Steps
        -----
        1. Load all inventory from repositories (one DB read per collection).
        2. Convert to per-collector-region YAML config dicts (pure logic).
        3. Render each config dict to a YAML string.
        4. Run the validation engine over the same data (no extra DB reads).
        5. Persist the history snapshot and update meta timestamps.
        6. Write an audit entry.
        7. Return the result to the caller.
        """
        devices = self._device_repo.list_all()
        bandwidth = self._bandwidth_repo.list_all()
        subnets = self._subnet_repo.list_all()
        tag_defs = self._tag_repo.list_all()

        result = convert_to_collector_configs(devices, bandwidth, subnets, tag_defs)

        # Render config dicts → YAML strings in-place.
        rendered_files = {
            name: yamldump.dump(config) for name, config in result["files"].items()
        }
        result["files"] = rendered_files

        # Run validation on the already-loaded data — no additional DB reads.
        result["findings"] = validate_inventory(devices, bandwidth, subnets, tag_defs)

        # Persist the history snapshot.
        self._history_repo.save(actor, result["summary"], rendered_files)

        # Update the meta timestamps that the dashboard displays.
        ts = now_iso()
        self._meta_repo.set_kv("lastSavedAt", ts)
        self._meta_repo.set_kv("lastSavedBy", actor or "unknown")

        self._audit_repo.log(actor, "generate", {"summary": result["summary"]})

        return result
