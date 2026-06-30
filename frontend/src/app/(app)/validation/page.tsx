'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { api } from '@/lib/api'
import type { GenerateResult, Finding } from '@/lib/types'
import { SeverityBadge } from '@/components/ui/Badge'
import { LoadingRow } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { EmptyState } from '@/components/ui/EmptyState'

// ---------------------------------------------------------------------------
// Group findings by severity
// ---------------------------------------------------------------------------
function FindingsList({
  findings,
  filter,
}: {
  findings: Finding[]
  filter: string
}) {
  const filtered = filter
    ? findings.filter((f) => f.severity === filter)
    : findings

  if (filtered.length === 0) {
    return (
      <EmptyState
        title={filter ? `No ${filter}s` : 'No findings'}
        sub={filter ? `All ${filter}s resolved.` : 'No issues detected.'}
      />
    )
  }

  return (
    <div className="card">
      {filtered.map((f, i) => (
        <div key={i} className="finding-row">
          <SeverityBadge severity={f.severity} />
          <div style={{ flex: 1 }}>
            <div className="finding-message">{f.message}</div>
            {(f.device || f.deviceId) && (
              <div className="finding-device">
                Device:{' '}
                <Link
                  href="/inventory"
                  style={{ color: 'var(--primary)', textDecoration: 'underline' }}
                >
                  {f.device ?? f.deviceId}
                </Link>
                {f.field && ` · field: ${f.field}`}
              </div>
            )}
            {f.details && (
              <div className="finding-device">{f.details}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Summary badges
// ---------------------------------------------------------------------------
function SummaryBar({
  findings,
  filter,
  setFilter,
}: {
  findings: Finding[]
  filter: string
  setFilter: (f: string) => void
}) {
  const counts = findings.reduce(
    (acc, f) => { acc[f.severity] = (acc[f.severity] ?? 0) + 1; return acc },
    {} as Record<string, number>,
  )

  const types: { key: string; label: string; cls: string }[] = [
    { key: '', label: `All (${findings.length})`, cls: 'badge-neutral' },
    { key: 'error', label: `Errors (${counts.error ?? 0})`, cls: 'badge-error' },
    { key: 'warning', label: `Warnings (${counts.warning ?? 0})`, cls: 'badge-warning' },
    { key: 'info', label: `Info (${counts.info ?? 0})`, cls: 'badge-info' },
  ]

  return (
    <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
      {types.map(({ key, label, cls }) => (
        <button
          key={key}
          className={`badge ${cls}`}
          style={{
            cursor: 'pointer',
            outline: filter === key ? '2px solid var(--primary)' : 'none',
            outlineOffset: 2,
            fontSize: 12,
            padding: '4px 10px',
          }}
          onClick={() => setFilter(key)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function ValidationPage() {
  const qc = useQueryClient()
  const [result, setResult] = useState<GenerateResult | null>(null)
  const [filter, setFilter] = useState('')

  const { mutate: runValidation, isLoading: isPending, error } = useMutation({
    mutationFn: () => api.generate(),
    onSuccess: (res) => {
      setResult(res)
      setFilter('')
      // Refresh meta in background
      qc.invalidateQueries({ queryKey: ['meta'] })
      qc.invalidateQueries({ queryKey: ['history'] })
    },
  })

  const findings = result?.findings ?? []
  const errors = findings.filter((f) => f.severity === 'error').length
  const warnings = findings.filter((f) => f.severity === 'warning').length

  return (
    <div>
      {/* Controls */}
      <div className="toolbar" style={{ marginBottom: 20 }}>
        <div className="toolbar-left">
          {result && (
            <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
              {result.summary}
            </div>
          )}
        </div>
        <div className="toolbar-right">
          <button
            className="btn btn-primary"
            onClick={() => runValidation()}
            disabled={isPending}
          >
            {isPending ? (
              <><span className="spinner" style={{ width: 14, height: 14, marginRight: 6 }} />Running…</>
            ) : (
              'Run Validation'
            )}
          </button>
        </div>
      </div>

      {!!error && <ErrorBanner error={error as Error} />}

      {isPending && <LoadingRow text="Validating inventory…" />}

      {!isPending && !result && !error && (
        <EmptyState
          title="No validation run yet"
          sub="Click Run Validation to check your inventory for issues."
          action={
            <button className="btn btn-primary" onClick={() => runValidation()}>
              Run Validation
            </button>
          }
        />
      )}

      {result && !isPending && (
        <>
          {/* Health banner */}
          {errors === 0 && warnings === 0 ? (
            <div className="banner banner-success mb-16">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <div>All checks passed. No errors or warnings found.</div>
            </div>
          ) : (
            <div className={`banner ${errors > 0 ? 'banner-error' : 'banner-warn'} mb-16`}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <div>
                {errors > 0 && <span><strong>{errors}</strong> error{errors !== 1 ? 's' : ''} · </span>}
                {warnings > 0 && <span><strong>{warnings}</strong> warning{warnings !== 1 ? 's' : ''}</span>}
              </div>
            </div>
          )}

          {/* Filter + list */}
          {findings.length > 0 && (
            <SummaryBar findings={findings} filter={filter} setFilter={setFilter} />
          )}

          <FindingsList findings={findings} filter={filter} />
        </>
      )}
    </div>
  )
}
