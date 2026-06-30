// ---------------------------------------------------------------------------
// TypeScript types for the ConfigFoundry v1 API
// ---------------------------------------------------------------------------

/** Network device (SNMP / ICMP-only) */
export interface Device {
  id: string
  IP: string
  Device?: string
  'Collector Region'?: string
  'Config Type'?: string
  snmpUser?: string
  authProtocol?: string
  authKey?: string
  privProtocol?: string
  privKey?: string
  Remarks?: string
  // Dynamic tag keys
  [key: string]: unknown
}

/** Bandwidth cap row */
export interface BandwidthRow {
  id: string
  IP: string
  Interface?: string
  'Allocated BW'?: number | string
  Region?: string
  Center?: string
  'Link Type'?: string
  Interface_description?: string
  [key: string]: unknown
}

/** Subnet definition */
export interface Subnet {
  id: string
  CIDR: string
  Description?: string
  tags?: Record<string, string>
  [key: string]: unknown
}

/** Tag definition */
export interface TagDef {
  id: string
  name: string
  label?: string
  type: 'enum' | 'text' | 'boolean'
  values?: string[]
  required?: boolean
  /** Which inventory sections this tag applies to: 'devices' | 'bandwidth' | 'subnets' */
  scopes?: string[]
}

/** Audit entry — details is a parsed dict from the backend, not a string */
export interface AuditEntryDetails {
  [key: string]: unknown
}

/** A managed list (e.g. Collector Regions) */
export interface ManagedList {
  name: string
  items: string[]
}

/** /api/v1/lists response */
export interface ListsResponse {
  lists: Record<string, string[]>
}

/** /api/v1/meta response */
export interface Meta {
  deviceCount: number
  bandwidthCount: number
  subnetCount: number
  lastSavedAt: string | null
  lastSavedBy: string | null
}

/** A single finding from validation / generation */
export interface Finding {
  severity: 'error' | 'warning' | 'info'
  code?: string
  message: string
  deviceId?: string
  device?: string
  field?: string
  details?: string
}

/**
 * Generation group statistics keyed by normalised group key.
 * Matches what core/logic.py returns under "groupStats".
 */
export type GroupStats = Record<string, {
  snmp_count: number
  icmp_only_count: number
  missing_creds_count: number
  bw_devices: number
  bw_interfaces: number
}>

/** /api/v1/generate response */
export interface GenerateResult {
  files: Record<string, string>
  groupStats: GroupStats
  summary: string
  findings: Finding[]
  snmpTotal?: number
  icmpTotal?: number
  /** Devices missing SNMPv3 credentials (included in output with warnings) */
  missingCredsDevices?: unknown[]
  /** Devices with no Collector Region (excluded from all output files) */
  missingRegionDevices?: unknown[]
  /** Count of devices skipped due to no IP */
  skippedDevices?: number
  /** Bandwidth rows with no matching device */
  orphanedBwIps?: string[]
}

/** Compact history entry from GET /api/v1/history */
export interface HistoryEntry {
  id: string
  ts: string
  actor?: string
  summary?: string
}

/** Full history entry from GET /api/v1/history/{id}
 *  The backend returns { id, ts, actor, summary, files: {filename: yamlContent} }
 */
export interface HistoryDetail {
  id: string
  ts: string
  actor?: string
  summary?: string
  /** Map of filename → YAML content */
  files: Record<string, string>
}

/** Audit log entry.
 *  NOTE: backend returns details as a parsed dict (json.loads), NOT a string.
 */
export interface AuditEntry {
  id?: string
  ts: string
  actor?: string
  action: string
  entity?: string
  entityId?: string
  details?: Record<string, unknown> | string | null
}

// ---------------------------------------------------------------------------
// API response wrappers
// ---------------------------------------------------------------------------

export interface DevicesResponse { devices: Device[] }
export interface BandwidthResponse { rows: BandwidthRow[] }
export interface SubnetsResponse { subnets: Subnet[] }
export interface TagsResponse { tagDefs: TagDef[] }
export interface HistoryListResponse { entries: HistoryEntry[] }
export interface AuditResponse { entries: AuditEntry[] }

// ---------------------------------------------------------------------------
// Import / validate
// ---------------------------------------------------------------------------

export type ImportMode = 'merge' | 'replace'

export interface ValidationIssue {
  row: number
  field?: string
  message: string
  severity: 'error' | 'warning'
}

export interface ValidateImportResponse {
  valid: boolean
  errors?: ValidationIssue[]
  warnings?: ValidationIssue[]
  preview?: Device[] | BandwidthRow[] | Subnet[]
}

export interface ImportResponse {
  imported: number
  updated?: number
  deleted?: number
  skipped?: number
}
