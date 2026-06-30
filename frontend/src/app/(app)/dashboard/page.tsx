'use client'

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { api } from '@/lib/api'
import { LoadingRow } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------
function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: number | string
  sub?: string
  accent?: boolean
}) {
  return (
    <div className="stat-card">
      <div className="stat-card-label">{label}</div>
      <div
        className="stat-card-value"
        style={accent ? { color: 'var(--primary)' } : undefined}
      >
        {value}
      </div>
      {sub && <div className="stat-card-sub">{sub}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Dashboard page
// ---------------------------------------------------------------------------
export default function DashboardPage() {
  const {
    data: meta,
    isLoading: metaLoading,
    error: metaError,
    refetch: refetchMeta,
  } = useQuery({
    queryKey: ['meta'],
    queryFn: () => api.getMeta(),
  })

  const { data: devicesRes, isLoading: devLoading } = useQuery({
    queryKey: ['devices'],
    queryFn: () => api.getDevices(),
  })

  const { data: auditRes, isLoading: auditLoading } = useQuery({
    queryKey: ['audit', 8],
    queryFn: () => api.getAudit(8),
  })

  const { data: historyRes } = useQuery({
    queryKey: ['history', 5],
    queryFn: () => api.getHistory(5),
  })

  if (metaLoading || devLoading) return <LoadingRow text="Loading dashboard…" />
  if (metaError) return <ErrorBanner error={metaError as Error} onRetry={refetchMeta} />

  const devices = devicesRes?.devices ?? []

  // Compute local stats from device data.
  // ICMP-only devices are identified by Config Type = 'icmp' | 'snmp trap' | 'storage'
  // (matches vanilla JS devices.js resolvedDeviceClass logic).
  // SNMPv3 credentials field is snmpUser (not 'SNMPv3 Username').
  const ICMP_TYPES = new Set(['icmp', 'snmp trap', 'storage'])
  const icmpOnly = devices.filter((d) =>
    ICMP_TYPES.has(((d['Config Type'] as string) ?? '').toLowerCase().trim()),
  ).length
  const snmpDevices = devices.length - icmpOnly

  const missingRegion = devices.filter((d) => !d['Collector Region']).length
  const missingCreds = devices.filter((d) => {
    const isIcmp = ICMP_TYPES.has(((d['Config Type'] as string) ?? '').toLowerCase().trim())
    return !isIcmp && !d.snmpUser
  }).length

  const recentHistory = historyRes?.entries ?? []
  const lastGen = recentHistory[0]

  return (
    <div>
      {/* Stat cards */}
      <div className="stat-grid">
        <StatCard
          label="Total Devices"
          value={meta?.deviceCount ?? devices.length}
          sub={`${snmpDevices} SNMP · ${icmpOnly} ICMP-only`}
        />
        <StatCard
          label="Bandwidth Rows"
          value={meta?.bandwidthCount ?? 0}
        />
        <StatCard
          label="Subnets"
          value={meta?.subnetCount ?? 0}
        />
        <StatCard
          label="Validation Issues"
          value={missingRegion + missingCreds}
          sub={
            missingRegion + missingCreds === 0
              ? 'All clear'
              : `${missingRegion} missing region · ${missingCreds} missing creds`
          }
          accent={missingRegion + missingCreds > 0}
        />
      </div>

      {/* Warning banners */}
      {(missingRegion > 0 || missingCreds > 0) && (
        <div className="banner banner-warn mb-16">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <div style={{ flex: 1, fontSize: 13 }}>
            {missingRegion > 0 && (
              <span><strong>{missingRegion}</strong> device{missingRegion !== 1 ? 's' : ''} missing Collector Region. </span>
            )}
            {missingCreds > 0 && (
              <span><strong>{missingCreds}</strong> device{missingCreds !== 1 ? 's' : ''} missing SNMPv3 credentials. </span>
            )}
            <Link href="/inventory" style={{ color: 'var(--warning)', textDecoration: 'underline' }}>
              Review devices →
            </Link>
          </div>
        </div>
      )}

      {/* Two-column grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>
        {/* Recent audit activity */}
        <div className="card">
          <div className="card-header">
            <h3>Recent Activity</h3>
          </div>
          {auditLoading ? (
            <LoadingRow />
          ) : (auditRes?.entries ?? []).length === 0 ? (
            <div className="card-body">
              <p className="text-faint text-sm">No activity recorded yet.</p>
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Entity</th>
                </tr>
              </thead>
              <tbody>
                {(auditRes?.entries ?? []).map((entry, i) => (
                  <tr key={entry.id ?? i}>
                    <td className="dim text-mono">{fmtTs(entry.ts)}</td>
                    <td>{entry.actor ?? '—'}</td>
                    <td>{entry.action}</td>
                    <td className="dim">{entry.entity ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Generation status */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="card">
            <div className="card-header"><h3>Generation Status</h3></div>
            <div className="card-body" style={{ fontSize: 13 }}>
              {lastGen ? (
                <>
                  <div style={{ marginBottom: 8 }}>
                    <span className="text-dim">Last generated</span>
                    <div className="text-mono mt-8">{fmtTs(lastGen.ts)}</div>
                  </div>
                  {lastGen.actor && (
                    <div style={{ marginBottom: 8 }}>
                      <span className="text-dim">By</span>
                      <div className="mt-8">{lastGen.actor}</div>
                    </div>
                  )}
                  {lastGen.summary && (
                    <div className="text-dim" style={{ fontSize: 12, marginBottom: 10 }}>
                      {lastGen.summary}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-faint" style={{ marginBottom: 10 }}>
                  No YAML generated yet.
                </p>
              )}
              <Link href="/generate" className="btn btn-primary w-full" style={{ marginTop: 6 }}>
                Go to Generate
              </Link>
            </div>
          </div>

          {/* Quick links */}
          <div className="card">
            <div className="card-header"><h3>Quick Links</h3></div>
            <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <Link href="/inventory" className="btn btn-secondary w-full">
                Manage Devices
              </Link>
              <Link href="/validation" className="btn btn-secondary w-full">
                Run Validation
              </Link>
              <Link href="/history" className="btn btn-secondary w-full">
                View History
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function fmtTs(ts: string | null | undefined) {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ts
  }
}
