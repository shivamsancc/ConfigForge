'use client'

import {
  useCallback,
  useMemo,
  useState,
  type ChangeEvent,
} from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/lib/api'
import type { Device, BandwidthRow, Subnet, ImportMode } from '@/lib/types'
import { LoadingRow } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { EmptyState } from '@/components/ui/EmptyState'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function useSorted<T extends Record<string, unknown>>(
  items: T[],
  defaultKey: string,
) {
  const [sortKey, setSortKey] = useState<keyof T>(defaultKey as keyof T)
  const [dir, setDir] = useState<'asc' | 'desc'>('asc')

  const sorted = useMemo(() => {
    return [...items].sort((a, b) => {
      const av = String(a[sortKey] ?? '')
      const bv = String(b[sortKey] ?? '')
      return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    })
  }, [items, sortKey, dir])

  const toggle = useCallback(
    (key: keyof T) => {
      if (key === sortKey) setDir((d) => (d === 'asc' ? 'desc' : 'asc'))
      else { setSortKey(key); setDir('asc') }
    },
    [sortKey],
  )

  return { sorted, sortKey, dir, toggle }
}

function SortTh<T>({
  col,
  label,
  sortKey,
  dir,
  onToggle,
}: {
  col: keyof T
  label: string
  sortKey: keyof T
  dir: 'asc' | 'desc'
  onToggle: (k: keyof T) => void
}) {
  const active = col === sortKey
  return (
    <th
      className={active ? 'sort-active' : ''}
      onClick={() => onToggle(col)}
    >
      {label} {active ? (dir === 'asc' ? '↑' : '↓') : ''}
    </th>
  )
}

const PAGE_SIZE = 25

function usePaged<T>(items: T[]) {
  const [page, setPage] = useState(0)
  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages - 1)
  const slice = items.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE)
  return { slice, page: safePage, totalPages, setPage, total: items.length }
}

function Pagination({
  page,
  total,
  totalPages,
  setPage,
}: {
  page: number
  total: number
  totalPages: number
  setPage: (p: number) => void
}) {
  if (totalPages <= 1) return null
  return (
    <div className="pagination">
      <button className="btn btn-sm btn-ghost" disabled={page === 0} onClick={() => setPage(0)}>«</button>
      <button className="btn btn-sm btn-ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>‹</button>
      <span className="page-info">Page {page + 1} of {totalPages} ({total} rows)</span>
      <button className="btn btn-sm btn-ghost" disabled={page === totalPages - 1} onClick={() => setPage(page + 1)}>›</button>
      <button className="btn btn-sm btn-ghost" disabled={page === totalPages - 1} onClick={() => setPage(totalPages - 1)}>»</button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Import modal — matches vanilla JS openImportDialog() flow exactly:
//   Step 1: choose .xlsx/.xls file
//   Step 2: choose sheet (appears after file loads)
//   Step 3: merge / replace radio buttons
//   Preview: "N row(s) found in 'SheetName'."
// ---------------------------------------------------------------------------
function ImportModal({
  onClose,
  onImport,
  label,
}: {
  onClose: () => void
  onImport: (rows: unknown[], mode: ImportMode) => void
  label: string
}) {
  type XLSXModule = typeof import('xlsx')
  const [wb, setWb] = useState<ReturnType<XLSXModule['read']> | null>(null)
  const [sheetNames, setSheetNames] = useState<string[]>([])
  const [selectedSheet, setSelectedSheet] = useState('')
  const [mode, setMode] = useState<ImportMode>('merge')
  const [previewCount, setPreviewCount] = useState<number | null>(null)
  const [parseError, setParseError] = useState<string | null>(null)

  async function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setParseError(null)
    try {
      const buf = await file.arrayBuffer()
      const XLSX = await import('xlsx')
      const workbook = XLSX.read(buf, { type: 'array' })
      const names = workbook.SheetNames
      // Prefer a sheet named 'devices' / 'bandwidth' / 'subnets' (case-insensitive)
      const preferred =
        names.find((n) => n.toLowerCase() === label.toLowerCase()) ?? names[0]
      setWb(workbook)
      setSheetNames(names)
      setSelectedSheet(preferred)
      // Show preview count for the preferred sheet
      const ws = workbook.Sheets[preferred]
      const rows = (await import('xlsx')).utils.sheet_to_json(ws, { defval: '' })
      setPreviewCount(rows.length)
    } catch {
      setParseError('Failed to read Excel file. Make sure it is a valid .xlsx or .xls file.')
    }
  }

  async function handleSheetChange(name: string) {
    setSelectedSheet(name)
    if (!wb) return
    const XLSX = await import('xlsx')
    const ws = wb.Sheets[name]
    const rows = XLSX.utils.sheet_to_json(ws, { defval: '' })
    setPreviewCount(rows.length)
  }

  async function handleSubmit() {
    if (!wb || !selectedSheet) return
    const XLSX = await import('xlsx')
    const ws = wb.Sheets[selectedSheet]
    const rows = XLSX.utils.sheet_to_json(ws, { defval: '' })
    onImport(rows, mode)
  }

  return (
    <Modal
      title={`Import ${label} from Excel`}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={!wb}>
            Import
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {parseError && <div className="banner banner-error">{parseError}</div>}

        {/* Step 1 */}
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>1. Choose file</div>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={handleFile}
            style={{ fontSize: 13, color: 'var(--text-dim)' }}
          />
          <div className="field-hint" style={{ marginTop: 6 }}>
            Tip: use "Export XLSX" first to get a template with the correct columns.
          </div>
        </div>

        {/* Step 2 — sheet picker, only visible after file loads */}
        {sheetNames.length > 0 && (
          <div>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>2. Choose sheet</div>
            <select
              className="select"
              value={selectedSheet}
              onChange={(e) => handleSheetChange(e.target.value)}
            >
              {sheetNames.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
            {previewCount !== null && (
              <div className="field-hint" style={{ marginTop: 4 }}>
                {previewCount} row(s) found in &ldquo;{selectedSheet}&rdquo;.
              </div>
            )}
          </div>
        )}

        {/* Step 3 */}
        <div>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
            {sheetNames.length > 0 ? '3.' : '2.'} Import mode
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="radio"
                name="import-mode"
                value="merge"
                checked={mode === 'merge'}
                onChange={() => setMode('merge')}
              />
              Merge (add / update, keep existing)
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="radio"
                name="import-mode"
                value="replace"
                checked={mode === 'replace'}
                onChange={() => setMode('replace')}
              />
              Replace (clear all, then import)
            </label>
          </div>
        </div>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Device form modal
// ---------------------------------------------------------------------------
function DeviceModal({
  device,
  onClose,
  onSave,
}: {
  device: Partial<Device> | null
  onClose: () => void
  onSave: (d: Partial<Device>) => void
}) {
  const isNew = !device?.id
  const [form, setForm] = useState<Record<string, string>>({
    IP: device?.IP ?? '',
    Device: String(device?.Device ?? ''),
    'Collector Region': String(device?.['Collector Region'] ?? ''),
    'Config Type': String(device?.['Config Type'] ?? ''),
    snmpUser: String(device?.snmpUser ?? ''),
    authProtocol: String(device?.authProtocol ?? ''),
    authKey: String(device?.authKey ?? ''),
    privProtocol: String(device?.privProtocol ?? ''),
    privKey: String(device?.privKey ?? ''),
    Remarks: String(device?.Remarks ?? ''),
  })

  function set(k: string, v: string) { setForm((f) => ({ ...f, [k]: v })) }

  function handleSave() {
    const out: Partial<Device> = { ...form }
    if (device?.id) out.id = device.id
    onSave(out)
  }

  const configType = (form['Config Type'] || '').toLowerCase().trim()
  const isIcmp = ['icmp', 'snmp trap', 'storage'].includes(configType)

  return (
    <Modal
      title={isNew ? 'Add Device' : 'Edit Device'}
      size="lg"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={!form.IP}
          >
            {isNew ? 'Add' : 'Save'}
          </button>
        </>
      }
    >
      <div className="form-row" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <label className="field-label">IP Address *</label>
          <input className="input" value={form.IP} onChange={(e) => set('IP', e.target.value)} placeholder="10.0.0.1" />
        </div>
        <div className="field">
          <label className="field-label">Device Name</label>
          <input className="input" value={form.Device} onChange={(e) => set('Device', e.target.value)} />
        </div>
        <div className="field">
          <label className="field-label">Collector Region</label>
          <input className="input" value={form['Collector Region']} onChange={(e) => set('Collector Region', e.target.value)} />
        </div>
        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <label className="field-label">Config Type</label>
          <select className="select" value={form['Config Type']} onChange={(e) => set('Config Type', e.target.value)}>
            <option value="">— select —</option>
            <option value="SNMP">SNMP</option>
            <option value="ICMP">ICMP</option>
            <option value="SNMP Trap">SNMP Trap</option>
            <option value="Storage">Storage</option>
          </select>
        </div>
        {!isIcmp && (
          <>
            <div className="field">
              <label className="field-label">SNMPv3 Username</label>
              <input className="input" value={form.snmpUser} onChange={(e) => set('snmpUser', e.target.value)} />
            </div>
            <div className="field">
              <label className="field-label">Auth Protocol</label>
              <input className="input" value={form.authProtocol} onChange={(e) => set('authProtocol', e.target.value)} placeholder="SHA, MD5…" />
            </div>
            <div className="field">
              <label className="field-label">Auth Password</label>
              <input className="input" type="password" value={form.authKey} onChange={(e) => set('authKey', e.target.value)} />
            </div>
            <div className="field">
              <label className="field-label">Priv Protocol</label>
              <input className="input" value={form.privProtocol} onChange={(e) => set('privProtocol', e.target.value)} placeholder="AES, DES…" />
            </div>
            <div className="field">
              <label className="field-label">Priv Password</label>
              <input className="input" type="password" value={form.privKey} onChange={(e) => set('privKey', e.target.value)} />
            </div>
          </>
        )}
        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <label className="field-label">Remarks</label>
          <textarea className="input" rows={2} value={form.Remarks} onChange={(e) => set('Remarks', e.target.value)} />
        </div>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Devices tab
// ---------------------------------------------------------------------------
function DevicesTab() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [editDevice, setEditDevice] = useState<Partial<Device> | null | 'new'>(null)
  const [importOpen, setImportOpen] = useState(false)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['devices'],
    queryFn: () => api.getDevices(),
  })

  const saveMut = useMutation({
    mutationFn: (d: Partial<Device>) => api.upsertDevice(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['devices'] })
      qc.invalidateQueries({ queryKey: ['meta'] })
      setEditDevice(null)
      toast('Device saved', 'success')
    },
    onError: (e) => toast((e as Error).message, 'error'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteDevice(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['devices'] })
      qc.invalidateQueries({ queryKey: ['meta'] })
      toast('Device deleted', 'success')
    },
    onError: (e) => toast((e as Error).message, 'error'),
  })

  const importMut = useMutation({
    mutationFn: ({ rows, mode }: { rows: unknown[]; mode: ImportMode }) =>
      api.importDevices(rows, mode),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['devices'] })
      qc.invalidateQueries({ queryKey: ['meta'] })
      setImportOpen(false)
      toast(`Imported ${(res as { imported?: number }).imported ?? '?'} devices`, 'success')
    },
    onError: (e) => toast((e as Error).message, 'error'),
  })

  const devices = data?.devices ?? []
  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    if (!q) return devices
    return devices.filter(
      (d) =>
        (d.IP ?? '').toLowerCase().includes(q) ||
        (d.Device ?? '').toLowerCase().includes(q) ||
        (d['Collector Region'] ?? '').toLowerCase().includes(q) ||
        (d['Config Type'] ?? '').toLowerCase().includes(q),
    )
  }, [devices, search])

  const { sorted, sortKey, dir, toggle } = useSorted(filtered, 'IP')
  const { slice, page, totalPages, setPage, total } = usePaged(sorted)

  if (isLoading) return <LoadingRow />
  if (error) return <ErrorBanner error={error as Error} onRetry={refetch} />

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-left">
          <div className="search-wrap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              className="input input-sm"
              placeholder="Search IP, device name, region…"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0) }}
              style={{ width: 260 }}
            />
          </div>
        </div>
        <div className="toolbar-right">
          <button className="btn btn-secondary btn-sm" onClick={() => setImportOpen(true)}>
            Import from Excel
          </button>
          <a className="btn btn-secondary btn-sm" href={api.exportUrl('devices')} download>
            Export XLSX
          </a>
          <button className="btn btn-primary btn-sm" onClick={() => setEditDevice('new')}>
            + Add Device
          </button>
        </div>
      </div>

      {total === 0 ? (
        <EmptyState
          title={search ? 'No devices match' : 'No devices yet'}
          sub={search ? 'Try a different search term.' : 'Add one manually or import a spreadsheet to get started.'}
          action={!search && <button className="btn btn-primary" onClick={() => setEditDevice('new')}>Add Device</button>}
        />
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <SortTh col="IP" label="IP Address" sortKey={sortKey as keyof Device} dir={dir} onToggle={(k) => toggle(k)} />
                  <SortTh col="Device" label="Device" sortKey={sortKey as keyof Device} dir={dir} onToggle={(k) => toggle(k)} />
                  <SortTh col="Collector Region" label="Region" sortKey={sortKey as keyof Device} dir={dir} onToggle={(k) => toggle(k)} />
                  <SortTh col="Config Type" label="Type" sortKey={sortKey as keyof Device} dir={dir} onToggle={(k) => toggle(k)} />
                  <th>Protocol</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {slice.map((d) => {
                  const cfgType = (d['Config Type'] as string || '').toLowerCase().trim()
                  const isIcmp = ['icmp', 'snmp trap', 'storage'].includes(cfgType)
                  return (
                    <tr key={d.id}>
                      <td className="mono">{d.IP}</td>
                      <td>{d.Device ?? <span className="text-faint">—</span>}</td>
                      <td>
                        {d['Collector Region'] ?? (
                          <span className="badge badge-warning">missing</span>
                        )}
                      </td>
                      <td className="dim">{(d['Config Type'] as string) ?? '—'}</td>
                      <td>
                        <span className={`badge ${isIcmp ? 'badge-info' : 'badge-neutral'}`}>
                          {isIcmp ? 'ICMP' : 'SNMPv3'}
                        </span>
                      </td>
                      <td className="actions">
                        <div style={{ display: 'flex', gap: 4 }}>
                          <button
                            className="btn btn-ghost btn-icon btn-sm"
                            title="Edit"
                            onClick={() => setEditDevice(d)}
                          >
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                            </svg>
                          </button>
                          <button
                            className="btn btn-ghost btn-icon btn-sm"
                            title="Delete"
                            onClick={() => {
                              if (confirm(`Delete ${d.IP}?`))
                                deleteMut.mutate(d.id)
                            }}
                          >
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <polyline points="3 6 5 6 21 6" />
                              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                              <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                            </svg>
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div style={{ padding: '0 12px 12px' }}>
            <Pagination page={page} total={total} totalPages={totalPages} setPage={setPage} />
          </div>
        </div>
      )}

      {/* Modals */}
      {editDevice !== null && (
        <DeviceModal
          device={typeof editDevice === 'string' ? null : editDevice}
          onClose={() => setEditDevice(null)}
          onSave={(d) => saveMut.mutate(d)}
        />
      )}
      {importOpen && (
        <ImportModal
          label="Devices"
          onClose={() => setImportOpen(false)}
          onImport={(rows, mode) => importMut.mutate({ rows, mode })}
        />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Bandwidth tab
// ---------------------------------------------------------------------------
function BandwidthTab() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [editRow, setEditRow] = useState<Partial<BandwidthRow> | null | 'new'>(null)
  const [importOpen, setImportOpen] = useState(false)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['bandwidth'],
    queryFn: () => api.getBandwidth(),
  })

  const saveMut = useMutation({
    mutationFn: (row: Partial<BandwidthRow>) => api.upsertBandwidth(row),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bandwidth'] }); qc.invalidateQueries({ queryKey: ['meta'] }); setEditRow(null); toast('Saved', 'success') },
    onError: (e) => toast((e as Error).message, 'error'),
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteBandwidth(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bandwidth'] }); qc.invalidateQueries({ queryKey: ['meta'] }); toast('Deleted', 'success') },
    onError: (e) => toast((e as Error).message, 'error'),
  })
  const importMut = useMutation({
    mutationFn: ({ rows, mode }: { rows: unknown[]; mode: ImportMode }) => api.importBandwidth(rows, mode),
    onSuccess: (res) => { qc.invalidateQueries({ queryKey: ['bandwidth'] }); qc.invalidateQueries({ queryKey: ['meta'] }); setImportOpen(false); toast(`Imported ${(res as {imported?:number}).imported ?? '?'} rows`, 'success') },
    onError: (e) => toast((e as Error).message, 'error'),
  })

  const rows = data?.rows ?? []
  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return q ? rows.filter(r => (r.IP ?? '').toLowerCase().includes(q) || (r.Interface ?? '').toLowerCase().includes(q)) : rows
  }, [rows, search])

  const { sorted, sortKey, dir, toggle } = useSorted(filtered, 'IP')
  const { slice, page, totalPages, setPage, total } = usePaged(sorted)

  if (isLoading) return <LoadingRow />
  if (error) return <ErrorBanner error={error as Error} onRetry={refetch} />

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-left">
          <div className="search-wrap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
            <input className="input input-sm" placeholder="Search IP, interface…" value={search} onChange={e => { setSearch(e.target.value); setPage(0) }} style={{ width: 240 }} />
          </div>
        </div>
        <div className="toolbar-right">
          <button className="btn btn-secondary btn-sm" onClick={() => setImportOpen(true)}>Import from Excel</button>
          <a className="btn btn-secondary btn-sm" href={api.exportUrl('bandwidth')} download>Export XLSX</a>
          <button className="btn btn-primary btn-sm" onClick={() => setEditRow('new')}>+ Add Row</button>
        </div>
      </div>

      {total === 0 ? (
        <EmptyState title={search ? 'No rows match' : 'No bandwidth rows yet'} sub="Import or add bandwidth cap entries." />
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <SortTh col="IP" label="IP Address" sortKey={sortKey as keyof BandwidthRow} dir={dir} onToggle={toggle} />
                  <SortTh col="Interface" label="Interface" sortKey={sortKey as keyof BandwidthRow} dir={dir} onToggle={toggle} />
                  <SortTh col="Allocated BW" label="Allocated BW" sortKey={sortKey as keyof BandwidthRow} dir={dir} onToggle={toggle} />
                  <th>Description</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {slice.map((r) => (
                  <tr key={r.id}>
                    <td className="mono">{r.IP}</td>
                    <td>{r.Interface ?? '—'}</td>
                    <td>{r['Allocated BW'] ?? '—'}</td>
                    <td className="dim">{r.Interface_description ?? '—'}</td>
                    <td className="actions">
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="btn btn-ghost btn-icon btn-sm" title="Edit" onClick={() => setEditRow(r)}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                        </button>
                        <button className="btn btn-ghost btn-icon btn-sm" title="Delete" onClick={() => { if (confirm('Delete this row?')) deleteMut.mutate(r.id) }}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /></svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ padding: '0 12px 12px' }}>
            <Pagination page={page} total={total} totalPages={totalPages} setPage={setPage} />
          </div>
        </div>
      )}

      {editRow !== null && (
        <BandwidthModal row={typeof editRow === 'string' ? null : editRow} onClose={() => setEditRow(null)} onSave={(r) => saveMut.mutate(r)} />
      )}
      {importOpen && (
        <ImportModal label="Bandwidth Rows" onClose={() => setImportOpen(false)} onImport={(rows, mode) => importMut.mutate({ rows, mode })} />
      )}
    </>
  )
}

function BandwidthModal({ row, onClose, onSave }: { row: Partial<BandwidthRow> | null; onClose: () => void; onSave: (r: Partial<BandwidthRow>) => void }) {
  const [form, setForm] = useState({ IP: row?.IP ?? '', Interface: String(row?.Interface ?? ''), 'Allocated BW': String(row?.['Allocated BW'] ?? ''), Interface_description: String(row?.Interface_description ?? '') })
  function set(k: string, v: string) { setForm(f => ({ ...f, [k]: v })) }
  function save() { const out: Partial<BandwidthRow> = { ...form }; if (row?.id) out.id = row.id; onSave(out) }
  return (
    <Modal title={row?.id ? 'Edit Row' : 'Add Row'} onClose={onClose} footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={save} disabled={!form.IP}>Save</button></>}>
      <div className="form-row" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div className="field"><label className="field-label">IP Address *</label><input className="input" value={form.IP} onChange={e => set('IP', e.target.value)} /></div>
        <div className="field"><label className="field-label">Interface</label><input className="input" value={form.Interface} onChange={e => set('Interface', e.target.value)} /></div>
        <div className="field"><label className="field-label">Allocated BW</label><input className="input" value={form['Allocated BW']} onChange={e => set('Allocated BW', e.target.value)} /></div>
        <div className="field"><label className="field-label">Description</label><input className="input" value={form.Interface_description} onChange={e => set('Interface_description', e.target.value)} /></div>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Subnets tab
// ---------------------------------------------------------------------------
function SubnetsTab() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [editSubnet, setEditSubnet] = useState<Partial<Subnet> | null | 'new'>(null)
  const [importOpen, setImportOpen] = useState(false)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['subnets'],
    queryFn: () => api.getSubnets(),
  })

  const saveMut = useMutation({
    mutationFn: (s: Partial<Subnet>) => api.upsertSubnet(s),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['subnets'] }); qc.invalidateQueries({ queryKey: ['meta'] }); setEditSubnet(null); toast('Saved', 'success') },
    onError: (e) => toast((e as Error).message, 'error'),
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteSubnet(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['subnets'] }); qc.invalidateQueries({ queryKey: ['meta'] }); toast('Deleted', 'success') },
    onError: (e) => toast((e as Error).message, 'error'),
  })
  const importMut = useMutation({
    mutationFn: ({ rows, mode }: { rows: unknown[]; mode: ImportMode }) => api.importSubnets(rows, mode),
    onSuccess: (res) => { qc.invalidateQueries({ queryKey: ['subnets'] }); qc.invalidateQueries({ queryKey: ['meta'] }); setImportOpen(false); toast(`Imported ${(res as {imported?:number}).imported ?? '?'} subnets`, 'success') },
    onError: (e) => toast((e as Error).message, 'error'),
  })

  const subnets = data?.subnets ?? []
  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return q ? subnets.filter(s => (s.CIDR ?? '').toLowerCase().includes(q) || (s.Description ?? '').toLowerCase().includes(q)) : subnets
  }, [subnets, search])

  const { sorted, sortKey, dir, toggle } = useSorted(filtered, 'CIDR')
  const { slice, page, totalPages, setPage, total } = usePaged(sorted)

  if (isLoading) return <LoadingRow />
  if (error) return <ErrorBanner error={error as Error} onRetry={refetch} />

  return (
    <>
      <div className="toolbar">
        <div className="toolbar-left">
          <div className="search-wrap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
            <input className="input input-sm" placeholder="Search subnet, region…" value={search} onChange={e => { setSearch(e.target.value); setPage(0) }} style={{ width: 240 }} />
          </div>
        </div>
        <div className="toolbar-right">
          <button className="btn btn-secondary btn-sm" onClick={() => setImportOpen(true)}>Import from Excel</button>
          <a className="btn btn-secondary btn-sm" href={api.exportUrl('subnets')} download>Export XLSX</a>
          <button className="btn btn-primary btn-sm" onClick={() => setEditSubnet('new')}>+ Add Subnet</button>
        </div>
      </div>

      {total === 0 ? (
        <EmptyState title={search ? 'No subnets match' : 'No subnets yet'} />
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <SortTh col="CIDR" label="CIDR" sortKey={sortKey as keyof Subnet} dir={dir} onToggle={toggle} />
                  <th>Description</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {slice.map((s) => (
                  <tr key={s.id}>
                    <td className="mono">{s.CIDR}</td>
                    <td className="dim">{s.Description ?? '—'}</td>
                    <td className="actions">
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="btn btn-ghost btn-icon btn-sm" title="Edit" onClick={() => setEditSubnet(s)}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                        </button>
                        <button className="btn btn-ghost btn-icon btn-sm" title="Delete" onClick={() => { if (confirm('Delete this subnet?')) deleteMut.mutate(s.id) }}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /></svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ padding: '0 12px 12px' }}>
            <Pagination page={page} total={total} totalPages={totalPages} setPage={setPage} />
          </div>
        </div>
      )}

      {editSubnet !== null && (
        <SubnetModal subnet={typeof editSubnet === 'string' ? null : editSubnet} onClose={() => setEditSubnet(null)} onSave={(s) => saveMut.mutate(s)} />
      )}
      {importOpen && (
        <ImportModal label="Subnets" onClose={() => setImportOpen(false)} onImport={(rows, mode) => importMut.mutate({ rows, mode })} />
      )}
    </>
  )
}

function SubnetModal({ subnet, onClose, onSave }: { subnet: Partial<Subnet> | null; onClose: () => void; onSave: (s: Partial<Subnet>) => void }) {
  const [form, setForm] = useState({ CIDR: subnet?.CIDR ?? '', Description: String(subnet?.Description ?? '') })
  function set(k: string, v: string) { setForm(f => ({ ...f, [k]: v })) }
  function save() { const out: Partial<Subnet> = { ...form }; if (subnet?.id) out.id = subnet.id; onSave(out) }
  return (
    <Modal title={subnet?.id ? 'Edit Subnet' : 'Add Subnet'} onClose={onClose} footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={save} disabled={!form.CIDR}>Save</button></>}>
      <div className="form-row" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div className="field" style={{ gridColumn: '1 / -1' }}><label className="field-label">CIDR *</label><input className="input" value={form.CIDR} onChange={e => set('CIDR', e.target.value)} placeholder="192.168.0.0/24" /></div>
        <div className="field" style={{ gridColumn: '1 / -1' }}><label className="field-label">Description</label><input className="input" value={form.Description} onChange={e => set('Description', e.target.value)} /></div>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Main Inventory page
// ---------------------------------------------------------------------------
type Tab = 'devices' | 'bandwidth' | 'subnets'

export default function InventoryPage() {
  const [tab, setTab] = useState<Tab>('devices')

  const { data: meta } = useQuery({ queryKey: ['meta'], queryFn: () => api.getMeta() })

  return (
    <div>
      <div className="tab-list">
        {([
          ['devices', `Devices${meta ? ` (${meta.deviceCount})` : ''}`],
          ['bandwidth', `Bandwidth${meta ? ` (${meta.bandwidthCount})` : ''}`],
          ['subnets', `Subnets${meta ? ` (${meta.subnetCount})` : ''}`],
        ] as [Tab, string][]).map(([id, label]) => (
          <button
            key={id}
            className={`tab-btn${tab === id ? ' active' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'devices' && <DevicesTab />}
      {tab === 'bandwidth' && <BandwidthTab />}
      {tab === 'subnets' && <SubnetsTab />}
    </div>
  )
}
