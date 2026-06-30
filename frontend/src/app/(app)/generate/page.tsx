'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { GenerateResult } from '@/lib/types'
import { LoadingRow } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { EmptyState } from '@/components/ui/EmptyState'
import { useToast } from '@/components/ui/Toast'

// ---------------------------------------------------------------------------
// File preview
// ---------------------------------------------------------------------------
function FilePreview({
  filename,
  content,
}: {
  filename: string
  content: string
}) {
  const [open, setOpen] = useState(false)
  const lines = content.split('\n').length

  function download() {
    const blob = new Blob([content], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="card" style={{ marginBottom: 10 }}>
      <div
        className="card-header"
        style={{ cursor: 'pointer' }}
        onClick={() => setOpen((o) => !o)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          <span style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{filename}</span>
          <span className="text-faint text-sm">({lines} lines)</span>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={(e) => { e.stopPropagation(); download() }}
          >
            Download
          </button>
          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2"
            style={{ transform: open ? 'rotate(180deg)' : undefined, transition: 'transform 150ms', color: 'var(--text-dim)' }}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
      </div>
      {open && (
        <div style={{ padding: '0 0 0 0' }}>
          <pre style={{ margin: 0, borderRadius: '0 0 var(--radius-lg) var(--radius-lg)', border: 'none', borderTop: '1px solid var(--border)' }}>
            {content}
          </pre>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Group stats table
// ---------------------------------------------------------------------------
function GroupStatsTable({ result }: { result: GenerateResult }) {
  const groupStats = result.groupStats ?? {}
  const entries = Object.entries(groupStats)
  if (entries.length === 0) return null
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-header"><h3>Breakdown by Region</h3></div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Region</th>
              <th>SNMP</th>
              <th>ICMP</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, s]) => (
              <tr key={key}>
                <td>{key}</td>
                <td>{s.snmp_count}</td>
                <td>{s.icmp_only_count}</td>
                <td><strong>{s.snmp_count + s.icmp_only_count}</strong></td>
              </tr>
            ))}
            {/* Totals row */}
            <tr style={{ background: 'var(--bg-raised)', fontWeight: 600 }}>
              <td>Total</td>
              <td>{result.snmpTotal ?? 0}</td>
              <td>{result.icmpTotal ?? 0}</td>
              <td>{(result.snmpTotal ?? 0) + (result.icmpTotal ?? 0)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function GeneratePage() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [result, setResult] = useState<GenerateResult | null>(null)

  const { mutate: runGenerate, isLoading: isPending, error } = useMutation({
    mutationFn: () => api.generate(),
    onSuccess: (res) => {
      setResult(res)
      qc.invalidateQueries({ queryKey: ['meta'] })
      qc.invalidateQueries({ queryKey: ['history'] })
      const fileCount = Object.keys(res.files ?? {}).length
      toast(
        `Generated ${fileCount} file${fileCount !== 1 ? 's' : ''} — ${res.snmpTotal ?? 0} SNMP, ${res.icmpTotal ?? 0} ICMP`,
        'success',
        6000,
      )
    },
    onError: (e) => toast((e as Error).message, 'error'),
  })

  function downloadAll() {
    if (!result) return
    Object.entries(result.files ?? {}).forEach(([name, content]) => {
      const blob = new Blob([content], { type: 'text/yaml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = name
      a.click()
      URL.revokeObjectURL(url)
    })
  }

  const files = Object.entries(result?.files ?? {})
  const errorFindings = result?.findings?.filter((f) => f.severity === 'error') ?? []
  const warnFindings = result?.findings?.filter((f) => f.severity === 'warning') ?? []

  return (
    <div>
      {/* Toolbar */}
      <div className="toolbar" style={{ marginBottom: 20 }}>
        <div className="toolbar-left">
          {result && (
            <div style={{ fontSize: 13, color: 'var(--text-dim)' }}>
              {result.summary}
            </div>
          )}
        </div>
        <div className="toolbar-right">
          {result && files.length > 0 && (
            <button className="btn btn-secondary" onClick={downloadAll}>
              Download All ({files.length})
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={() => runGenerate()}
            disabled={isPending}
          >
            {isPending ? (
              <><span className="spinner" style={{ width: 14, height: 14 }} /> Generating…</>
            ) : (
              'Generate YAML'
            )}
          </button>
        </div>
      </div>

      {!!error && <ErrorBanner error={error as Error} />}
      {isPending && <LoadingRow text="Generating YAML files…" />}

      {!isPending && !result && !error && (
        <EmptyState
          title="Nothing generated yet"
          sub="Click Generate YAML to produce config files from the current inventory."
          action={
            <button className="btn btn-primary" onClick={() => runGenerate()}>
              Generate YAML
            </button>
          }
        />
      )}

      {result && !isPending && (
        <>
          {/* Missing-region devices: excluded from output — danger banner */}
          {(result.missingRegionDevices?.length ?? 0) > 0 && (
            <div className="banner banner-error mb-12">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <div>
                <strong>{result.missingRegionDevices!.length} device{result.missingRegionDevices!.length !== 1 ? 's' : ''}</strong>{' '}
                have no Collector Region and were <strong>excluded</strong> from every output file.{' '}
                <a href="/inventory" style={{ color: 'inherit', textDecoration: 'underline' }}>Review in Inventory →</a>
              </div>
            </div>
          )}
          {/* Missing-creds devices: included with warning */}
          {(result.missingCredsDevices?.length ?? 0) > 0 && (
            <div className="banner banner-warn mb-12">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <div>
                <strong>{result.missingCredsDevices!.length} device{result.missingCredsDevices!.length !== 1 ? 's' : ''}</strong>{' '}
                are missing SNMPv3 credentials and were still included in the output.
              </div>
            </div>
          )}
          {/* Residual findings not covered by the banners above */}
          {errorFindings.length > 0 && (
            <div className="banner banner-error mb-12">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <div>
                <strong>{errorFindings.length} error{errorFindings.length !== 1 ? 's' : ''}</strong> —{' '}
                {errorFindings.slice(0, 2).map((f) => f.message).join('; ')}
                {errorFindings.length > 2 && ` and ${errorFindings.length - 2} more`}.
              </div>
            </div>
          )}
          {warnFindings.length > 0 && (
            <div className="banner banner-warn mb-12">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <div><strong>{warnFindings.length} warning{warnFindings.length !== 1 ? 's' : ''}</strong> detected.</div>
            </div>
          )}

          {/* Breakdown */}
          <GroupStatsTable result={result} />

          {/* Files */}
          {files.length === 0 ? (
            <EmptyState title="No files generated" sub="The inventory may be empty or no devices matched the generation criteria." />
          ) : (
            <div>
              <div className="section-title">{files.length} file{files.length !== 1 ? 's' : ''} generated</div>
              {files.map(([name, content]) => (
                <FilePreview key={name} filename={name} content={content} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
