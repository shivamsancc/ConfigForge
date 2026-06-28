// ============================================================================
// MANAGE LISTS VIEW
//
// Collector Region is the one categorization that stays a permanent,
// built-in concept -- it's mandatory and drives YAML generation grouping.
// Every tag's VALUE LIST also lives here, so this page is the one place
// to curate every dropdown's options. Creating a brand-new tag (its name
// and which sections it applies to) stays exclusive to Manage Tags --
// this page only edits values for tags that already exist.
// ============================================================================

const Lists = (() => {
  async function render() {
    const content = document.getElementById('content');
    content.innerHTML = `
      <div class="banner banner-info mb-16">
        <span>${icon('info', { size: 16 })}</span>
        <div class="banner-content">
          Every value list lives here \u2014 Collector Region plus the value list for each tag you've created.
          To create a brand-new tag (or change which sections it applies to), use
          <button class="link" data-nav="tags">Manage Tags</button> instead.
        </div>
      </div>

      <div class="panel mb-16">
        <div class="panel-header"><h2>Collector Region</h2></div>
        <div class="panel-body">
          <div class="field-hint mb-12">Required on every device for it to be included in generated YAML.</div>
          <div class="list-chip-row" id="chips-collectorRegions"></div>
          <div class="add-row">
            <input type="text" id="add-input-collectorRegions" placeholder="Add new collector region&hellip;">
            <button class="btn btn-primary btn-sm" data-add-fixed="collectorRegions">Add</button>
          </div>
        </div>
      </div>

      <div id="tag-lists-body"></div>
    `;

    content.querySelectorAll('[data-nav]').forEach(el => el.addEventListener('click', () => navigateTo(el.dataset.nav)));

    renderChips('collectorRegions');
    document.querySelector('[data-add-fixed="collectorRegions"]').addEventListener('click', () => handleAddFixed('collectorRegions'));
    document.getElementById('add-input-collectorRegions').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); handleAddFixed('collectorRegions'); }
    });

    renderTagListsBody();
  }

  function renderTagListsBody() {
    const body = document.getElementById('tag-lists-body');
    if (state.tagDefs.length === 0) {
      body.innerHTML = emptyState({
        title: 'No tags created yet',
        sub: 'Create a tag in Manage Tags first, then its value list will show up here.',
      });
      return;
    }
    const scopeLabels = { devices: 'Devices', bandwidth: 'Bandwidth Capping', subnets: 'Subnets' };
    body.innerHTML = state.tagDefs.map(td => `
      <div class="panel mb-16" data-tag-id="${escapeHtml(td.id)}">
        <div class="panel-header">
          <h2>${escapeHtml(td.name)}</h2>
          <div class="flex gap-6">
            ${(td.scopes || []).map(s => `<span class="badge badge-violet">${escapeHtml(scopeLabels[s] || s)}</span>`).join('')}
          </div>
        </div>
        <div class="panel-body">
          <div class="list-chip-row" id="tag-chips-${escapeHtml(td.id)}"></div>
          <div class="add-row">
            <input type="text" id="tag-add-input-${escapeHtml(td.id)}" placeholder="Add a value to ${escapeHtml(td.name)}&hellip;">
            <button class="btn btn-primary btn-sm" data-add-tag="${escapeHtml(td.id)}">Add</button>
          </div>
        </div>
      </div>
    `).join('');

    state.tagDefs.forEach(td => {
      renderTagChips(td);
      document.querySelector(`[data-add-tag="${td.id}"]`).addEventListener('click', () => handleAddTagValue(td.id));
      document.getElementById(`tag-add-input-${td.id}`).addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); handleAddTagValue(td.id); }
      });
    });
  }

  // ---- Collector Region (fixed list) ----
  function renderChips(listKey) {
    const container = document.getElementById(`chips-${listKey}`);
    const items = state.lists[listKey] || [];
    if (items.length === 0) {
      container.innerHTML = `<span class="text-faint" style="font-size:12.5px;">No items yet.</span>`;
      return;
    }
    container.innerHTML = items.map(v => `
      <span class="list-chip">
        ${escapeHtml(v)}
        <button data-remove-fixed="${escapeHtml(listKey)}" data-value="${escapeHtml(v)}" title="Remove">&times;</button>
      </span>
    `).join('');
    container.querySelectorAll('[data-remove-fixed]').forEach(btn => {
      btn.addEventListener('click', () => handleRemoveFixed(btn.dataset.removeFixed, btn.dataset.value));
    });
  }

  async function handleAddFixed(listKey) {
    const input = document.getElementById(`add-input-${listKey}`);
    const value = input.value.trim();
    if (!value) return;
    const current = state.lists[listKey] || [];
    if (current.includes(value)) { toast('That value already exists in the list', 'warn'); return; }
    const updated = [...current, value];
    try {
      await Api.setList(listKey, updated);
      state.lists[listKey] = updated;
      input.value = '';
      renderChips(listKey);
      toast('Added', 'success');
    } catch (e) {
      reportError(e, 'Failed to update list');
    }
  }

  async function handleRemoveFixed(listKey, value) {
    const proceed = await confirmDependentDelete({
      itemLabel: `"${value}" in Collector Region`,
      checkUsage: () => Api.getListUsage(listKey, value).then(r => r.count),
      zeroUsageMessage: `Remove "${value}" from this list?`,
    });
    if (!proceed) return;

    const updated = (state.lists[listKey] || []).filter(v => v !== value);
    try {
      await Api.setList(listKey, updated);
      state.lists[listKey] = updated;
      renderChips(listKey);
      toast('Removed', 'success');
    } catch (e) {
      reportError(e, 'Failed to update list');
    }
  }

  // ---- Tag value lists ----
  function renderTagChips(td) {
    const container = document.getElementById(`tag-chips-${td.id}`);
    const items = td.values || [];
    if (items.length === 0) {
      container.innerHTML = `<span class="text-faint" style="font-size:12.5px;">No values yet.</span>`;
      return;
    }
    container.innerHTML = items.map(v => `
      <span class="list-chip">
        ${escapeHtml(v)}
        <button data-remove-tag-value="${escapeHtml(v)}" data-tag-id="${escapeHtml(td.id)}" title="Remove">&times;</button>
      </span>
    `).join('');
    container.querySelectorAll('[data-remove-tag-value]').forEach(btn => {
      btn.addEventListener('click', () => handleRemoveTagValue(btn.dataset.tagId, btn.dataset.removeTagValue));
    });
  }

  function findTagDef(tagId) {
    return state.tagDefs.find(t => t.id === tagId);
  }

  async function handleAddTagValue(tagId) {
    const td = findTagDef(tagId);
    if (!td) return;
    const input = document.getElementById(`tag-add-input-${tagId}`);
    const value = input.value.trim();
    if (!value) return;
    if ((td.values || []).includes(value)) { toast('That value already exists', 'warn'); return; }
    const updated = Object.assign({}, td, { values: [...(td.values || []), value] });
    try {
      const saved = await Api.saveTag(updated);
      updateLocalTagDef(saved.tagDef || saved);
      input.value = '';
      renderTagChips(findTagDef(tagId));
      toast('Value added', 'success');
    } catch (e) {
      reportError(e, 'Failed to add value');
    }
  }

  async function handleRemoveTagValue(tagId, value) {
    const td = findTagDef(tagId);
    if (!td) return;
    const proceed = await confirmDependentDelete({
      itemLabel: `"${value}" in ${td.name}`,
      checkUsage: () => Api.getTagUsage(tagId, value).then(r => r.count),
      zeroUsageMessage: `Remove "${value}" from ${td.name}?`,
    });
    if (!proceed) return;

    const updated = Object.assign({}, td, { values: (td.values || []).filter(v => v !== value) });
    try {
      const saved = await Api.saveTag(updated);
      updateLocalTagDef(saved.tagDef || saved);
      renderTagChips(findTagDef(tagId));
      toast('Value removed', 'success');
    } catch (e) {
      reportError(e, 'Failed to remove value');
    }
  }

  function updateLocalTagDef(tagDef) {
    const idx = state.tagDefs.findIndex(t => t.id === tagDef.id);
    if (idx >= 0) state.tagDefs[idx] = tagDef;
    else state.tagDefs.push(tagDef);
  }

  return { render };
})();
