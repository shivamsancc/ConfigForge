// ============================================================================
// MANAGE TAGS VIEW -- create and define tags.
// A tag def is {id, name, scopes: [devices|bandwidth|subnets], values: [...]}.
// This page handles creating a tag and choosing which sections it applies
// to. Editing the tag's VALUE LIST happens on Manage Lists instead, so
// every value list (Collector Region plus every tag) lives in one place.
// ============================================================================

const Tags = (() => {
  const SCOPE_LABELS = { devices: 'Devices', bandwidth: 'Bandwidth Capping', subnets: 'Subnets' };

  async function render() {
    const content = document.getElementById('content');
    content.innerHTML = `
      <div class="flex justify-between items-center mb-16">
        <button class="btn btn-primary" id="btn-add-tag">${icon('plus', { size: 14 })} New Tag</button>
        <div class="text-dim">${state.tagDefs.length} tag(s) defined</div>
      </div>
      <div class="banner banner-info mb-16">
        <span>${icon('info', { size: 16 })}</span>
        <div class="banner-content">
          This page creates a tag and chooses which sections it applies to. To add or remove its values,
          use <button class="link" data-nav="lists">Manage Lists</button> once it's created.
        </div>
      </div>
      <div id="tags-body"></div>
    `;
    document.getElementById('btn-add-tag').addEventListener('click', () => openTagForm(null));
    content.querySelectorAll('[data-nav]').forEach(el => el.addEventListener('click', () => navigateTo(el.dataset.nav)));
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
    body.innerHTML = `<div class="card-grid">${state.tagDefs.map(td => renderTagCard(td)).join('')}</div>`;
    wireCardActions();
  }

  function renderTagCard(td) {
    const scopeBadges = (td.scopes || []).map(s => `<span class="badge badge-violet">${escapeHtml(SCOPE_LABELS[s] || s)}</span>`).join(' ');
    const valueCount = (td.values || []).length;
    return `
      <div class="data-card" data-id="${escapeHtml(td.id)}">
        <div class="data-card-header">
          <div>
            <div class="data-card-title">${escapeHtml(td.name)}</div>
            <div class="data-card-sub">${valueCount} value${valueCount === 1 ? '' : 's'}</div>
          </div>
        </div>
        <div class="data-card-meta">${scopeBadges}</div>
        <div class="data-card-actions">
          <button class="btn btn-sm" data-act="edit">Edit</button>
          <button class="btn btn-sm" data-act="manage-values">Manage Values</button>
          <button class="btn btn-sm btn-danger" data-act="delete-tag">Delete</button>
        </div>
      </div>
    `;
  }

  function wireCardActions() {
    document.querySelectorAll('#tags-body [data-id]').forEach(card => {
      const td = state.tagDefs.find(t => t.id === card.dataset.id);
      if (!td) return;
      card.querySelector('[data-act="edit"]').addEventListener('click', () => openTagForm(td));
      card.querySelector('[data-act="delete-tag"]').addEventListener('click', () => handleDeleteTagDef(td));
      card.querySelector('[data-act="manage-values"]').addEventListener('click', () => navigateTo('lists'));
    });
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
          ${!isEdit ? `<div class="field-hint mt-12">Add values for this tag afterward on the Manage Lists page.</div>` : ''}
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
        toast(isEdit ? 'Tag updated' : 'Tag created \u2014 add values on Manage Lists', 'success');
        closeModal(overlay);
        render();
      } catch (e) {
        reportError(e, 'Save failed');
      }
    });
  }

  return { render };
})();
