// ============================================================================
// MANAGE LISTS VIEW (fixed: Collector Region, Device Class, Device Category, Device Type)
// ============================================================================

const Lists = (() => {
  const LIST_DEFS = [
    { key: 'collectorRegions', label: 'Collector Region', hint: 'Required on every device for it to be included in generated YAML.' },
    { key: 'deviceClasses', label: 'Device Class', hint: '"Storage" forces a device to ICMP-only regardless of credentials.' },
    { key: 'deviceCategories', label: 'Device Category', hint: '' },
    { key: 'deviceTypes', label: 'Device Type', hint: '' },
  ];

  async function render() {
    const content = document.getElementById('content');
    content.innerHTML = LIST_DEFS.map(def => `
      <div class="panel mb-16">
        <div class="panel-header"><h2>${escapeHtml(def.label)}</h2></div>
        <div class="panel-body">
          ${def.hint ? `<div class="field-hint mb-12">${escapeHtml(def.hint)}</div>` : ''}
          <div class="list-chip-row" id="chips-${def.key}"></div>
          <div class="add-row">
            <input type="text" id="add-input-${def.key}" placeholder="Add new ${escapeHtml(def.label.toLowerCase())}&hellip;">
            <button class="btn btn-primary btn-sm" data-add="${def.key}">Add</button>
          </div>
        </div>
      </div>
    `).join('');

    LIST_DEFS.forEach(def => renderChips(def.key));
    document.querySelectorAll('[data-add]').forEach(btn => btn.addEventListener('click', () => handleAdd(btn.dataset.add)));
    LIST_DEFS.forEach(def => {
      const input = document.getElementById(`add-input-${def.key}`);
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); handleAdd(def.key); } });
    });
  }

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
        <button data-remove="${escapeHtml(listKey)}" data-value="${escapeHtml(v)}" title="Remove">&times;</button>
      </span>
    `).join('');
    container.querySelectorAll('[data-remove]').forEach(btn => {
      btn.addEventListener('click', () => handleRemove(btn.dataset.remove, btn.dataset.value));
    });
  }

  async function handleAdd(listKey) {
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

  async function handleRemove(listKey, value) {
    const def = LIST_DEFS.find(d => d.key === listKey);
    const proceed = await confirmDependentDelete({
      itemLabel: `"${value}" in ${def ? def.label : listKey}`,
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

  return { render };
})();
