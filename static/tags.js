// ============================================================================
// MANAGE TAGS VIEW -- the dynamic tag system.
// A tag def is {id, name, scopes: [devices|bandwidth|subnets], values: [...]}.
// A tag scoped to multiple sections shares one value list across all of them.
// ============================================================================

const Tags = (() => {
  const SCOPE_LABELS = { devices: 'Devices', bandwidth: 'Bandwidth Capping', subnets: 'Subnets' };

  async function render() {
    const content = document.getElementById('content');
    content.innerHTML = `
      <div class="flex justify-between items-center mb-16">
        <button class="btn btn-primary" id="btn-add-tag">+ New Tag</button>
        <div class="text-dim">${state.tagDefs.length} tag(s) defined</div>
      </div>
      <div id="tags-body"></div>
    `;
    document.getElementById('btn-add-tag').addEventListener('click', () => openTagForm(null));
    renderBody();
  }

  function renderBody() {
    const body = document.getElementById('tags-body');
    if (state.tagDefs.length === 0) {
      body.innerHTML = emptyState({
        title: 'No tags defined yet',
        sub: 'Create a tag like "Country" or "Environment" and choose which sections it applies to -- Devices, Bandwidth Capping, and/or Subnets.',
      });
      return;
    }
    body.innerHTML = state.tagDefs.map(td => renderTagCard(td)).join('');
    wireCardActions();
  }

  function renderTagCard(td) {
    const scopeBadges = (td.scopes || []).map(s => `<span class="badge badge-violet">${escapeHtml(SCOPE_LABELS[s] || s)}</span>`).join(' ');
    return `
      <div class="tag-def-card" data-id="${escapeHtml(td.id)}">
        <div class="flex justify-between items-center mb-12">
          <div>
            <div style="font-weight:650;font-size:14.5px;">${escapeHtml(td.name)}</div>
            <div class="flex gap-8 mb-12" style="margin-top:6px;">${scopeBadges}</div>
          </div>
          <div class="flex gap-8">
            <button class="btn btn-sm" data-act="edit-name">Edit</button>
            <button class="btn btn-sm btn-danger" data-act="delete-tag">Delete Tag</button>
          </div>
        </div>
        <div class="list-chip-row" id="chips-${escapeHtml(td.id)}"></div>
        <div class="add-row">
          <input type="text" id="add-input-${escapeHtml(td.id)}" placeholder="Add a value to ${escapeHtml(td.name)}&hellip;">
          <button class="btn btn-primary btn-sm" data-act="add-value">Add</button>
        </div>
      </div>
    `;
  }

  function wireCardActions() {
    state.tagDefs.forEach(td => {
      renderChips(td);
      const card = document.querySelector(`.tag-def-card[data-id="${td.id}"]`);
      if (!card) return;
      card.querySelector('[data-act="edit-name"]').addEventListener('click', () => openTagForm(td));
      card.querySelector('[data-act="delete-tag"]').addEventListener('click', () => handleDeleteTagDef(td));
      card.querySelector('[data-act="add-value"]').addEventListener('click', () => handleAddValue(td));
      const input = document.getElementById(`add-input-${td.id}`);
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddValue(td); } });
    });
  }

  function renderChips(td) {
    const container = document.getElementById(`chips-${td.id}`);
    const items = td.values || [];
    if (items.length === 0) {
      container.innerHTML = `<span class="text-faint" style="font-size:12.5px;">No values yet.</span>`;
      return;
    }
    container.innerHTML = items.map(v => `
      <span class="list-chip">
        ${escapeHtml(v)}
        <button data-remove-value="${escapeHtml(v)}" title="Remove">&times;</button>
      </span>
    `).join('');
    container.querySelectorAll('[data-remove-value]').forEach(btn => {
      btn.addEventListener('click', () => handleRemoveValue(td, btn.dataset.removeValue));
    });
  }

  async function handleAddValue(td) {
    const input = document.getElementById(`add-input-${td.id}`);
    const value = input.value.trim();
    if (!value) return;
    if ((td.values || []).includes(value)) {
      toast('That value already exists', 'warn');
      return;
    }
    const updated = Object.assign({}, td, { values: [...(td.values || []), value] });
    try {
      const saved = await Api.saveTag(updated);
      updateLocalTagDef(saved.tagDef || saved);
      input.value = '';
      render();
      toast('Value added', 'success');
    } catch (e) {
      reportError(e, 'Failed to add value');
    }
  }

  async function handleRemoveValue(td, value) {
    const proceed = await confirmDependentDelete({
      itemLabel: `"${value}"`,
      checkUsage: () => Api.getTagUsage(td.id, value).then(r => r.count),
      zeroUsageMessage: `Remove "${value}" from ${td.name}?`,
    });
    if (!proceed) return;

    const updated = Object.assign({}, td, { values: (td.values || []).filter(v => v !== value) });
    try {
      const saved = await Api.saveTag(updated);
      updateLocalTagDef(saved.tagDef || saved);
      render();
      toast('Value removed', 'success');
    } catch (e) {
      reportError(e, 'Failed to remove value');
    }
  }

  async function handleDeleteTagDef(td) {
    let dependents = 0;
    try {
      const usage = await Api.getTagUsage(td.id);
      dependents = usage.count;
    } catch (e) { /* fall through to a plain confirm below */ }

    const message = dependents > 0
      ? `"${td.name}" is currently used by ${dependents} record(s) across ${(td.scopes || []).map(s => SCOPE_LABELS[s] || s).join(', ')}. Deleting it will remove the tag everywhere it's used. Delete anyway?`
      : `Delete the tag "${td.name}"? This cannot be undone.`;
    const ok = await confirmDialog(message, { confirmLabel: 'Delete anyway' });
    if (!ok) return;

    try {
      await Api.deleteTag(td.id, dependents > 0);
      state.tagDefs = state.tagDefs.filter(t => t.id !== td.id);
      render();
      toast('Tag deleted', 'success');
    } catch (e) {
      if (e.status === 409) {
        // Race: something started using it between our check and the delete.
        // Surface clearly and let the person retry, rather than silently failing.
        const retry = await confirmDialog(
          `"${td.name}" is now in use by ${e.data?.dependents ?? 'some'} record(s) (this changed since you opened this dialog). Delete anyway?`,
          { confirmLabel: 'Delete anyway' }
        );
        if (retry) {
          try {
            await Api.deleteTag(td.id, true);
            state.tagDefs = state.tagDefs.filter(t => t.id !== td.id);
            render();
            toast('Tag deleted', 'success');
          } catch (e2) {
            reportError(e2, 'Delete failed');
          }
        }
      } else {
        reportError(e, 'Delete failed');
      }
    }
  }

  function updateLocalTagDef(tagDef) {
    const idx = state.tagDefs.findIndex(t => t.id === tagDef.id);
    if (idx >= 0) state.tagDefs[idx] = tagDef;
    else state.tagDefs.push(tagDef);
  }

  function openTagForm(td) {
    const isEdit = !!td;
    const scopes = (td && td.scopes) || [];
    const overlay = openModal(`
      <div class="modal-header">
        <h3>${isEdit ? 'Edit Tag' : 'New Tag'}</h3>
        <button class="modal-close" data-act="close">&times;</button>
      </div>
      <div class="modal-body">
        <form id="tag-form">
          <div class="field mb-16">
            <label>Tag name<span class="req">*</span></label>
            <input type="text" name="name" value="${escapeHtml((td || {}).name || '')}" placeholder="e.g. Country, Environment, Business Unit" required>
          </div>
          <div class="field">
            <label>Applies to</label>
            <div class="scope-pills">
              ${Object.entries(SCOPE_LABELS).map(([key, label]) => `
                <label class="scope-pill${scopes.includes(key) ? ' selected' : ''}" data-scope-pill="${key}">
                  <input type="checkbox" name="scope" value="${key}" ${scopes.includes(key) ? 'checked' : ''}>
                  ${escapeHtml(label)}
                </label>
              `).join('')}
            </div>
            <span class="field-hint">A tag applying to multiple sections shares the same dropdown and value list across all of them.</span>
          </div>
        </form>
      </div>
      <div class="modal-footer">
        <button class="btn" data-act="close">Cancel</button>
        <button class="btn btn-primary" data-act="save">${isEdit ? 'Save Changes' : 'Create Tag'}</button>
      </div>
    `);
    overlay.querySelectorAll('[data-act="close"]').forEach(b => b.addEventListener('click', () => closeModal(overlay)));
    overlay.querySelectorAll('.scope-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        // Let the native checkbox toggle happen, then sync the visual state.
        setTimeout(() => {
          const checked = pill.querySelector('input').checked;
          pill.classList.toggle('selected', checked);
        }, 0);
      });
    });
    overlay.querySelector('[data-act="save"]').addEventListener('click', async () => {
      const form = overlay.querySelector('#tag-form');
      if (!form.reportValidity()) return;
      const fd = new FormData(form);
      const name = fd.get('name').trim();
      const selectedScopes = fd.getAll('scope');
      if (selectedScopes.length === 0) {
        toast('Choose at least one section this tag applies to', 'warn');
        return;
      }
      const payload = isEdit ? Object.assign({}, td, { name, scopes: selectedScopes }) : { name, scopes: selectedScopes, values: [] };
      try {
        const saved = await Api.saveTag(payload);
        updateLocalTagDef(saved.tagDef || saved);
        toast(isEdit ? 'Tag updated' : 'Tag created', 'success');
        closeModal(overlay);
        render();
      } catch (e) {
        reportError(e, 'Save failed');
      }
    });
  }

  return { render };
})();
