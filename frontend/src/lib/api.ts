/**
 * Typed fetch wrappers for the ConfigFoundry /api/v1 REST API.
 *
 * In production (static export served by FastAPI) all URLs are relative.
 * In development the Next.js dev server rewrites /api/* → FastAPI:8420.
 */
import type {
  AuditResponse,
  BandwidthResponse,
  BandwidthRow,
  Device,
  DevicesResponse,
  GenerateResult,
  HistoryDetail,
  HistoryListResponse,
  ImportMode,
  ImportResponse,
  ListsResponse,
  Meta,
  Subnet,
  SubnetsResponse,
  TagDef,
  TagsResponse,
  ValidateImportResponse,
} from './types'

const BASE = '/api/v1'

// ---------------------------------------------------------------------------
// Core fetch helper
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public data?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const opts: RequestInit = { method, headers: {} }

  if (body !== undefined) {
    ;(opts.headers as Record<string, string>)['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, opts)
  } catch (e) {
    throw new ApiError(0, `Network error: ${(e as Error).message}`)
  }

  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!res.ok) {
    const msg =
      (data && typeof data === 'object' && 'error' in data
        ? String((data as Record<string, unknown>).error)
        : null) ??
      res.statusText ??
      `HTTP ${res.status}`
    throw new ApiError(res.status, msg, data)
  }

  return data as T
}

// ---------------------------------------------------------------------------
// Devices
// ---------------------------------------------------------------------------

export const api = {
  // Meta
  getMeta: () => request<Meta>('GET', '/meta'),

  // Devices
  getDevices: () => request<DevicesResponse>('GET', '/devices'),
  upsertDevice: (device: Partial<Device>, actor?: string) =>
    request<{ device: Device }>('POST', '/devices', { device, _actor: actor }),
  deleteDevice: (id: string, actor?: string) =>
    request<{ deleted: string }>('DELETE', `/devices/${encodeURIComponent(id)}?_actor=${encodeURIComponent(actor ?? '')}`),
  validateImportDevices: (devices: unknown[], mode: ImportMode = 'merge') =>
    request<ValidateImportResponse>('POST', '/devices/validate-import', { devices, mode }),
  importDevices: (devices: unknown[], mode: ImportMode = 'merge', actor?: string) =>
    request<ImportResponse>('POST', '/devices/import', { devices, mode, _actor: actor }),

  // Bandwidth
  getBandwidth: () => request<BandwidthResponse>('GET', '/bandwidth'),
  upsertBandwidth: (row: Partial<BandwidthRow>, actor?: string) =>
    request<{ row: BandwidthRow }>('POST', '/bandwidth', { row, _actor: actor }),
  deleteBandwidth: (id: string, actor?: string) =>
    request<{ deleted: string }>('DELETE', `/bandwidth/${encodeURIComponent(id)}?_actor=${encodeURIComponent(actor ?? '')}`),
  validateImportBandwidth: (rows: unknown[], mode: ImportMode = 'merge') =>
    request<ValidateImportResponse>('POST', '/bandwidth/validate-import', { rows, mode }),
  importBandwidth: (rows: unknown[], mode: ImportMode = 'merge', actor?: string) =>
    request<ImportResponse>('POST', '/bandwidth/import', { rows, mode, _actor: actor }),

  // Subnets
  getSubnets: () => request<SubnetsResponse>('GET', '/subnets'),
  upsertSubnet: (subnet: Partial<Subnet>, actor?: string) =>
    request<{ subnet: Subnet }>('POST', '/subnets', { subnet, _actor: actor }),
  deleteSubnet: (id: string, actor?: string) =>
    request<{ deleted: string }>('DELETE', `/subnets/${encodeURIComponent(id)}?_actor=${encodeURIComponent(actor ?? '')}`),
  validateImportSubnets: (subnets: unknown[], mode: ImportMode = 'merge') =>
    request<ValidateImportResponse>('POST', '/subnets/validate-import', { subnets, mode }),
  importSubnets: (subnets: unknown[], mode: ImportMode = 'merge', actor?: string) =>
    request<ImportResponse>('POST', '/subnets/import', { subnets, mode, _actor: actor }),

  // Tags
  getTags: () => request<TagsResponse>('GET', '/tags'),
  upsertTag: (tagDef: Partial<TagDef>, actor?: string) =>
    request<{ tagDef: TagDef }>('POST', '/tags', { tagDef, _actor: actor }),
  deleteTag: (id: string, actor?: string, force = false) =>
    request<{ deleted: string }>(
      'DELETE',
      `/tags/${encodeURIComponent(id)}?_actor=${encodeURIComponent(actor ?? '')}&force=${force}`,
    ),
  tagUsage: (id: string, value?: string) => {
    const q = value !== undefined ? `?value=${encodeURIComponent(value)}` : ''
    return request<{ count: number }>('GET', `/tags/${encodeURIComponent(id)}/usage${q}`)
  },

  // Lists
  getLists: () => request<ListsResponse>('GET', '/lists'),
  setList: (name: string, items: string[], actor?: string) =>
    request<{ items: string[] }>('POST', `/lists/${encodeURIComponent(name)}`, { items, _actor: actor }),

  // Generate
  generate: (actor?: string) => request<GenerateResult>('POST', '/generate', { _actor: actor }),

  // History
  getHistory: (limit = 50) => request<HistoryListResponse>('GET', `/history?limit=${limit}`),
  getHistoryEntry: (id: string) => request<HistoryDetail>('GET', `/history/${encodeURIComponent(id)}`),

  // Audit
  getAudit: (limit = 100) => request<AuditResponse>('GET', `/audit?limit=${limit}`),

  // Export (returns download URL — trigger via link)
  exportUrl: (type: 'devices' | 'bandwidth' | 'subnets') =>
    `${BASE}/export/${type}.xlsx`,
}

export { ApiError }
