'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { HistoryEntry } from '@/lib/types'
import { LoadingRow } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { EmptyState } from '@/components/ui/EmptyState'

// ---------------------------------------------------------------------------
// History entry detail (lazy-loaded)
// ---------------------------------------------------------------------------
function HistoryDetail({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['history', id],
    queryFn: () => api.getHistoryEntry(id),
  })

  if (isLoading) return <LoadingRow />
  if (error) return <div className="text-faint text-sm" style={{ padding: 12 }}>Failed to load details.</div>
  if (!data) return null

  // Backend returns { files: { filename: yamlContent } }
  const files = Object.entries(data.files ?? {})

  return (
    <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', background: 'var(--bg-raised)' }}>

      {files.length > 0 && (
        <div>
          <div className="section-title" style={{ marginBottom: 8 }}>Files ({files.length})</div>
          {files.map(([name, content]) => (
            <div key={name} style={{ marginBottom: 6 }}>
              <button
                className="btn btn-secondary btn-sm"
                style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}
                onClick={() => {
                  const blob = new Blob([content], { type: 'text/yaml' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = name
                  a.click()
                  URL.revokeObjectURL(url)
                }}
              >
                ↓ {name}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Entry row
// ---------------------------------------------------------------------------
function HistoryRow({ entry }: { entry: HistoryEntry }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="card" style={{ marginBottom: 8 }}>
      <div
        className="card-header"
        style={{ cursor: 'pointer' }}
        onClick={() => setExpanded((o) => !o)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="text-mono">{fmtTs(entry.ts)}</span>
          <span className="text-dim" style={{ fontSize: 13 }}>
            {entry.summary ?? 'Generated'}
          </span>
          {entry.actor && (
            <span className="badge badge-neutral">{entry.actor}</span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2"
            style={{ transform: expanded ? 'rotate(180deg)' : undefined, transition: 'transform 150ms', color: 'var(--text-faint)' }}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
      </div>
      {expanded && <HistoryDetail id={entry.id} />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Audit tab
// ---------------------------------------------------------------------------
function AuditTab() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['audit', 100],
    queryFn: () => api.getAudit(100),
  })

  if (isLoading) return <LoadingRow />
  if (error) return <ErrorBanner error={error as Error} onRetry={refetch} />

  const entries = data?.entries ?? []
  if (entries.length === 0) {
    return <EmptyState title="No audit entries" sub="Actions will appear here as the system is used." />
  }

  return (
    <div className="card">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Entity</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={e.id ?? i}>
                <td className="dim text-mono">{fmtTs(e.ts)}</td>
                <td>{e.actor ?? '—'}</td>
                <td>{e.action}</td>
                <td className="dim">{e.entity ?? '—'}</td>
                <td className="dim" style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {e.details == null
                    ? '—'
                    : typeof e.details === 'string'
                    ? e.details
                    : JSON.stringify(e.details)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function HistoryPage() {
  const [tab, setTab] = useState<'history' | 'audit'>('history')

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['history', 50],
    queryFn: () => api.getHistory(50),
    enabled: tab === 'history',
  })

  return (
    <div>
      <div className="tab-list">
        {([['history', 'YAML History'], ['audit', 'Audit Log']] as const).map(([id, label]) => (
          <button
            key={id}
            className={`tab-btn${tab === id ? ' active' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'history' && (
        <>
          {isLoading && <LoadingRow />}
          {!!error && <ErrorBanner error={error as Error} onRetry={refetch} />}
          {!isLoading && !error && (data?.entries ?? []).length === 0 && (
            <EmptyState title="No history yet" sub="Generated YAML files will appear here." />
          )}
          {(data?.entries ?? []).map((e) => (
            <HistoryRow key={e.id} entry={e} />
          ))}
        </>
      )}

      {tab === 'audit' && <AuditTab />}
    </div>
  )
}

function fmtTs(ts: string) {
  try {
    return new Date(ts).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ts
  }
}
