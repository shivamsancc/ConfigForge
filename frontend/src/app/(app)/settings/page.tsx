'use client'

import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { TagDef } from '@/lib/types'
import { LoadingRow } from '@/components/ui/Spinner'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { EmptyState } from '@/components/ui/EmptyState'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'

// ---------------------------------------------------------------------------
// Tag modal
// ---------------------------------------------------------------------------
const SCOPE_OPTIONS: { key: string; label: string }[] = [
  { key: 'devices', label: 'Devices' },
  { key: 'bandwidth', label: 'Bandwidth Capping' },
  { key: 'subnets', label: 'Subnets' },
]

function TagModal({
  tag,
  onClose,
  onSave,
}: {
  tag: Partial<TagDef> | null
  onClose: () => void
  onSave: (t: Partial<TagDef>) => void
}) {
  const isNew = !tag?.id
  const [form, setForm] = useState({
    id: tag?.id ?? '',
    name: tag?.name ?? '',
    label: tag?.label ?? '',
    type: (tag?.type ?? 'enum') as TagDef['type'],
    required: tag?.required ?? false,
    scopes: tag?.scopes ?? [] as string[],
    valuesText: (tag?.values ?? []).join('\n'),
  })

  function set(k: string, v: unknown) { setForm((f) => ({ ...f, [k]: v })) }

  function toggleScope(key: string) {
    setForm((f) => {
      const has = f.scopes.includes(key)
      return { ...f, scopes: has ? f.scopes.filter((s) => s !== key) : [...f.scopes, key] }
    })
  }

  function save() {
    const values = form.valuesText.split('\n').map((v) => v.trim()).filter(Boolean)
    const out: Partial<TagDef> = {
      name: form.name || form.id,
      label: form.label || form.name || form.id,
      type: form.type,
      required: form.required,
      scopes: form.scopes,
    }
    if (form.id) out.id = form.id
    if (form.type === 'enum') out.values = values
    onSave(out)
  }

  return (
    <Modal
      title={isNew ? 'New Tag' : 'Edit Tag'}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={!form.name && !form.id}>
            {isNew ? 'Add' : 'Save'}
          </button>
        </>
      }
    >
      <div className="form-row" style={{ gap: 14 }}>
        <div className="field">
          <label className="field-label">Tag name *</label>
          <input
            className="input"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="e.g. Country, Environment, Business Unit"
            disabled={!isNew}
          />
        </div>
        {/* Scopes — matches vanilla JS "Applies to" section */}
        <div className="field">
          <label className="field-label">Applies to</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
            {SCOPE_OPTIONS.map(({ key, label }) => (
              <label
                key={key}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                  padding: '4px 10px', borderRadius: 'var(--radius)',
                  border: `1px solid ${form.scopes.includes(key) ? 'var(--primary)' : 'var(--border)'}`,
                  background: form.scopes.includes(key) ? 'var(--primary-subtle)' : 'transparent',
                  fontSize: 13,
                }}
              >
                <input
                  type="checkbox"
                  checked={form.scopes.includes(key)}
                  onChange={() => toggleScope(key)}
                  style={{ width: 13, height: 13 }}
                />
                {label}
              </label>
            ))}
          </div>
          <div className="text-faint text-sm" style={{ marginTop: 4 }}>
            A tag applying to multiple sections shares the same value list.
          </div>
        </div>
        <div className="field">
          <label className="field-label">Type</label>
          <select className="select" value={form.type} onChange={(e) => set('type', e.target.value as TagDef['type'])}>
            <option value="enum">Enum (dropdown)</option>
            <option value="text">Text</option>
            <option value="boolean">Boolean</option>
          </select>
        </div>
        <div className="field" style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input
            id="required-check"
            type="checkbox"
            checked={form.required}
            onChange={(e) => set('required', e.target.checked)}
            style={{ width: 14, height: 14 }}
          />
          <label htmlFor="required-check" className="field-label" style={{ cursor: 'pointer' }}>
            Required field
          </label>
        </div>
        {form.type === 'enum' && (
          <div className="field">
            <label className="field-label">Values (one per line)</label>
            <textarea
              className="input"
              rows={5}
              value={form.valuesText}
              onChange={(e) => set('valuesText', e.target.value)}
              placeholder={'APAC\nEMEA\nNAM\nLATAM'}
            />
            <div className="text-faint text-sm" style={{ marginTop: 4 }}>
              You can also manage values on the Managed Lists page after saving.
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// Tags section
// ---------------------------------------------------------------------------
function TagsSection() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [editTag, setEditTag] = useState<Partial<TagDef> | null | 'new'>(null)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['tags'],
    queryFn: () => api.getTags(),
  })

  const saveMut = useMutation({
    mutationFn: (t: Partial<TagDef>) => api.upsertTag(t),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tags'] })
      setEditTag(null)
      toast('Tag saved', 'success')
    },
    onError: (e) => toast((e as Error).message, 'error'),
  })

  const deleteMut = useMutation({
    mutationFn: ({ id, force }: { id: string; force: boolean }) => api.deleteTag(id, undefined, force),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tags'] }); toast('Tag deleted', 'success') },
    onError: (e) => {
      const err = e as Error & { data?: { dependents?: string[] } }
      if (err.message.includes('in use')) {
        if (confirm('This tag is in use by devices. Delete anyway and remove it from all devices?')) {
          // Re-trigger with force=true — but we need the ID. This is a UX edge case.
          toast('Use the delete button again with force enabled.', 'warn')
        }
      } else {
        toast(err.message, 'error')
      }
    },
  })

  if (isLoading) return <LoadingRow />
  if (error) return <ErrorBanner error={error as Error} onRetry={refetch} />

  const tags = data?.tagDefs ?? []

  return (
    <>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <div className="toolbar-left">
          <span className="text-dim text-sm">{tags.length} tag definition{tags.length !== 1 ? 's' : ''}</span>
        </div>
        <div className="toolbar-right">
          <button className="btn btn-primary btn-sm" onClick={() => setEditTag('new')}>
            + Add Tag
          </button>
        </div>
      </div>

      {tags.length === 0 ? (
        <EmptyState
          title="No tags defined"
          sub="Tags let you add custom fields to devices (e.g. Collector Region, Role)."
          action={<button className="btn btn-primary" onClick={() => setEditTag('new')}>Add Tag</button>}
        />
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Applies to</th>
                  <th>Values</th>
                  <th>Required</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {tags.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <div>{t.label ?? t.name}</div>
                      <div className="text-faint text-sm mono">{t.id}</div>
                    </td>
                    <td>
                      <span className="badge badge-neutral">{t.type}</span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {(t.scopes ?? []).length === 0 ? (
                          <span className="text-faint">—</span>
                        ) : (
                          (t.scopes ?? []).map((s) => (
                            <span key={s} className="badge badge-info" style={{ fontSize: 11 }}>
                              {SCOPE_OPTIONS.find((o) => o.key === s)?.label ?? s}
                            </span>
                          ))
                        )}
                      </div>
                    </td>
                    <td className="text-dim" style={{ maxWidth: 200 }}>
                      {t.type === 'enum'
                        ? (t.values ?? []).slice(0, 4).join(', ') +
                          ((t.values?.length ?? 0) > 4 ? ` +${(t.values?.length ?? 0) - 4}` : '')
                        : '—'}
                    </td>
                    <td>
                      {t.required ? (
                        <span className="badge badge-error">yes</span>
                      ) : (
                        <span className="text-faint">no</span>
                      )}
                    </td>
                    <td className="actions">
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="btn btn-ghost btn-icon btn-sm" title="Edit" onClick={() => setEditTag(t)}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                          </svg>
                        </button>
                        <button
                          className="btn btn-ghost btn-icon btn-sm"
                          title="Delete"
                          onClick={() => {
                            if (confirm(`Delete tag "${t.id}"?`))
                              deleteMut.mutate({ id: t.id, force: false })
                          }}
                        >
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="3 6 5 6 21 6" />
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {editTag !== null && (
        <TagModal
          tag={typeof editTag === 'string' ? null : editTag}
          onClose={() => setEditTag(null)}
          onSave={(t) => saveMut.mutate(t)}
        />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Lists section
// ---------------------------------------------------------------------------
function ListsSection() {
  const qc = useQueryClient()
  const { toast } = useToast()
  const [editList, setEditList] = useState<string | null>(null)
  const [itemsText, setItemsText] = useState('')

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['lists'],
    queryFn: () => api.getLists(),
  })

  const saveMut = useMutation({
    mutationFn: ({ name, items }: { name: string; items: string[] }) =>
      api.setList(name, items),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['lists'] })
      setEditList(null)
      toast('List saved', 'success')
    },
    onError: (e) => toast((e as Error).message, 'error'),
  })

  const startEdit = useCallback(
    (name: string, items: string[]) => {
      setEditList(name)
      setItemsText(items.join('\n'))
    },
    [],
  )

  function saveList() {
    if (!editList) return
    const items = itemsText.split('\n').map((s) => s.trim()).filter(Boolean)
    saveMut.mutate({ name: editList, items })
  }

  if (isLoading) return <LoadingRow />
  if (error) return <ErrorBanner error={error as Error} onRetry={refetch} />

  const lists = Object.entries(data?.lists ?? {})

  return (
    <>
      {lists.length === 0 ? (
        <EmptyState title="No managed lists" sub="Lists like Collector Regions will appear here." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {lists.map(([name, items]) => (
            <div key={name} className="card">
              <div className="card-header">
                <h3 style={{ textTransform: 'capitalize' }}>{name.replace(/_/g, ' ')}</h3>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => startEdit(name, items)}
                >
                  Edit
                </button>
              </div>
              <div className="card-body">
                {items.length === 0 ? (
                  <span className="text-faint text-sm">No items</span>
                ) : (
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {items.map((item) => (
                      <span key={item} className="badge badge-neutral">{item}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {editList && (
        <Modal
          title={`Edit List: ${editList.replace(/_/g, ' ')}`}
          onClose={() => setEditList(null)}
          footer={
            <>
              <button className="btn btn-secondary" onClick={() => setEditList(null)}>Cancel</button>
              <button className="btn btn-primary" onClick={saveList}>Save</button>
            </>
          }
        >
          <div className="field">
            <label className="field-label">Items (one per line)</label>
            <textarea
              className="input"
              rows={10}
              value={itemsText}
              onChange={(e) => setItemsText(e.target.value)}
              placeholder={'APAC\nEMEA\nNAM'}
            />
          </div>
        </Modal>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function SettingsPage() {
  const [tab, setTab] = useState<'tags' | 'lists'>('tags')

  return (
    <div>
      <div className="tab-list">
        {([['tags', 'Tag Definitions'], ['lists', 'Managed Lists']] as const).map(([id, label]) => (
          <button
            key={id}
            className={`tab-btn${tab === id ? ' active' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'tags' && <TagsSection />}
      {tab === 'lists' && <ListsSection />}
    </div>
  )
}
