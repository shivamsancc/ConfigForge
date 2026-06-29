"""
Export service — builds Excel export files from inventory data.

All column layout logic that previously lived in handler.py now lives here.
The service is purely functional: given repositories, it loads the data and
delegates byte generation to the xlsxwriter format module.
"""
from core.repositories.interfaces import (
    IDeviceRepository,
    IBandwidthRepository,
    ISubnetRepository,
    ITagRepository,
)
from formats import xlsxwriter


class ExportService:
    """Builds xlsx export bytes from live repository data."""

    def __init__(
        self,
        device_repo: IDeviceRepository,
        bandwidth_repo: IBandwidthRepository,
        subnet_repo: ISubnetRepository,
        tag_repo: ITagRepository,
    ) -> None:
        self._device_repo = device_repo
        self._bandwidth_repo = bandwidth_repo
        self._subnet_repo = subnet_repo
        self._tag_repo = tag_repo

    # ------------------------------------------------------------------
    # Public build methods
    # ------------------------------------------------------------------

    def build_devices_xlsx(self) -> bytes:
        devices = self._device_repo.list_all()
        tag_defs = self._tag_repo.list_all()
        return _devices_to_xlsx(devices, tag_defs)

    def build_bandwidth_xlsx(self) -> bytes:
        rows = self._bandwidth_repo.list_all()
        tag_defs = self._tag_repo.list_all()
        return _bandwidth_to_xlsx(rows, tag_defs)

    def build_subnets_xlsx(self) -> bytes:
        subnets = self._subnet_repo.list_all()
        tag_defs = self._tag_repo.list_all()
        return _subnets_to_xlsx(subnets, tag_defs)


# ---------------------------------------------------------------------------
# Private helpers (extracted from handler.py build_*_xlsx functions)
# ---------------------------------------------------------------------------

def _devices_to_xlsx(devices: list[dict], tag_defs: list[dict]) -> bytes:
    fixed_cols = [
        "IP", "Device", "Collector Region", "Config Type", "Remarks",
        "snmpUser", "authProtocol", "authKey", "privProtocol", "privKey",
    ]
    device_tag_defs = [td for td in tag_defs if "devices" in td.get("scopes", [])]
    tag_cols = [td["name"] for td in device_tag_defs]
    headers = fixed_cols + tag_cols

    rows = []
    for d in devices:
        row = [d.get(c, "") for c in fixed_cols]
        for td in device_tag_defs:
            row.append((d.get("tags") or {}).get(td["id"], ""))
        rows.append(row)

    return xlsxwriter.write_xlsx("devices", headers, rows)


def _bandwidth_to_xlsx(rows_in: list[dict], tag_defs: list[dict]) -> bytes:
    fixed_cols = [
        "IP", "Interface", "Allocated BW", "Region", "Center",
        "Link Type", "Interface_description",
    ]
    bw_tag_defs = [td for td in tag_defs if "bandwidth" in td.get("scopes", [])]
    tag_cols = [td["name"] for td in bw_tag_defs]
    headers = fixed_cols + tag_cols

    rows = []
    for r in rows_in:
        row = [r.get(c, "") for c in fixed_cols]
        for td in bw_tag_defs:
            row.append((r.get("tags") or {}).get(td["id"], ""))
        rows.append(row)

    return xlsxwriter.write_xlsx("bandwidth_capping", headers, rows)


def _subnets_to_xlsx(subnets_in: list[dict], tag_defs: list[dict]) -> bytes:
    fixed_cols = ["CIDR", "Description"]
    subnet_tag_defs = [td for td in tag_defs if "subnets" in td.get("scopes", [])]
    tag_cols = [td["name"] for td in subnet_tag_defs]
    headers = fixed_cols + tag_cols

    rows = []
    for s in subnets_in:
        row = [s.get(c, "") for c in fixed_cols]
        for td in subnet_tag_defs:
            row.append((s.get("tags") or {}).get(td["id"], ""))
        rows.append(row)

    return xlsxwriter.write_xlsx("subnets", headers, rows)
