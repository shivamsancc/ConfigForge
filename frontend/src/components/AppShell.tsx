'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useCallback, useEffect, useState, type ReactNode, type ReactElement } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

// ---------------------------------------------------------------------------
// Icons (inline SVG, no icon library dependency)
// ---------------------------------------------------------------------------
function Icon({ name }: { name: string }) {
  const icons: Record<string, ReactElement> = {
    dashboard: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
    inventory: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18" />
      </svg>
    ),
    validation: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M9 12l2 2 4-4" />
        <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z" />
      </svg>
    ),
    generate: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </svg>
    ),
    history: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
        <path d="M3 3v5h5" />
        <path d="M12 7v5l4 2" />
      </svg>
    ),
    settings: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    ),
    sun: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <circle cx="12" cy="12" r="5" />
        <line x1="12" y1="1" x2="12" y2="3" />
        <line x1="12" y1="21" x2="12" y2="23" />
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
        <line x1="1" y1="12" x2="3" y2="12" />
        <line x1="21" y1="12" x2="23" y2="12" />
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
      </svg>
    ),
    moon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    ),
    logo: (
      <svg viewBox="0 0 28 28" fill="none">
        <rect x="2" y="2" width="10" height="10" rx="2" fill="currentColor" opacity=".3" />
        <rect x="16" y="2" width="10" height="10" rx="2" fill="currentColor" opacity=".6" />
        <rect x="2" y="16" width="10" height="10" rx="2" fill="currentColor" opacity=".6" />
        <rect x="16" y="16" width="10" height="10" rx="2" fill="currentColor" />
      </svg>
    ),
  }
  return icons[name] ?? null
}

// ---------------------------------------------------------------------------
// Nav config
// ---------------------------------------------------------------------------
const NAV_GROUPS = [
  {
    label: 'Overview',
    items: [
      { href: '/dashboard',  label: 'Dashboard',    icon: 'dashboard',   countKey: null },
    ],
  },
  {
    label: 'Work',
    items: [
      { href: '/inventory',  label: 'Inventory',    icon: 'inventory',   countKey: 'deviceCount' as const },
      { href: '/validation', label: 'Validation',   icon: 'validation',  countKey: null },
      { href: '/generate',   label: 'Generate YAML', icon: 'generate',   countKey: null },
    ],
  },
  {
    label: 'System',
    items: [
      { href: '/history',    label: 'History',      icon: 'history',     countKey: null },
      { href: '/settings',   label: 'Settings',     icon: 'settings',    countKey: null },
    ],
  },
]

// ---------------------------------------------------------------------------
// Page titles
// ---------------------------------------------------------------------------
const PAGE_TITLES: Record<string, string> = {
  '/dashboard':  'Dashboard',
  '/inventory':  'Inventory',
  '/validation': 'Validation',
  '/generate':   'Generate YAML',
  '/history':    'History',
  '/settings':   'Settings',
}

// ---------------------------------------------------------------------------
// AppShell
// ---------------------------------------------------------------------------
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [theme, setThemeState] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    try {
      const saved = localStorage.getItem('cf-theme')
      if (saved === 'light' || saved === 'dark') setThemeState(saved)
    } catch {}
  }, [])

  const toggleTheme = useCallback(() => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setThemeState(next)
    document.documentElement.setAttribute('data-theme', next)
    try { localStorage.setItem('cf-theme', next) } catch {}
  }, [theme])

  const { data: meta } = useQuery({
    queryKey: ['meta'],
    queryFn: () => api.getMeta(),
    refetchInterval: 60_000,
  })

  const pageTitle = PAGE_TITLES[pathname] ?? 'ConfigFoundry'

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span style={{ color: 'var(--primary)' }}>
            <Icon name="logo" />
          </span>
          <span className="sidebar-brand-name">
            Config<span className="accent">Forge</span>
          </span>
        </div>

        <nav className="sidebar-nav">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map((item) => {
                const active = pathname === item.href ||
                  (item.href !== '/' && pathname.startsWith(item.href))
                const count = item.countKey && meta ? meta[item.countKey] : null
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`nav-item${active ? ' active' : ''}`}
                  >
                    <Icon name={item.icon} />
                    <span>{item.label}</span>
                    {count != null && (
                      <span className="nav-badge">{count}</span>
                    )}
                  </Link>
                )
              })}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span>v0.5</span>
          <a
            href="https://github.com/shivamsancc/ConfigForge"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub ↗
          </a>
        </div>
      </aside>

      {/* Main */}
      <div className="main-area">
        <header className="topbar">
          <span className="topbar-title">{pageTitle}</span>
          <div className="topbar-actions">
            {meta && (
              <>
                <span className="topbar-stat">
                  <strong>{meta.deviceCount}</strong> devices
                </span>
                <span className="topbar-stat">
                  <strong>{meta.bandwidthCount}</strong> bw rows
                </span>
                <span className="topbar-stat">
                  <strong>{meta.subnetCount}</strong> subnets
                </span>
              </>
            )}
            <button
              className="btn btn-ghost btn-icon"
              onClick={toggleTheme}
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              style={{ width: 30, height: 30 }}
            >
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            </button>
          </div>
        </header>

        <main className="content">{children}</main>
      </div>
    </div>
  )
}
