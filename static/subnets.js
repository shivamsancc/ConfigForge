// ============================================================================
// SUBNETS VIEW
// ============================================================================

const Subnets = (() => {
  let searchQuery = '';

  const FIELDS = [
    { key: 'CIDR', label: 'CIDR', required: true, placeholder: 'e.g. 10.1.1.0/24' },
    { key: 'Description', label: 'Description' },
  ];

  function isValidCidr(value) {
    // Lightweight client-side sanity check; the server is the source of
    // truth for actual matching at generate time.
    return /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\/\d{1,2}$/.test((value || '').trim());
  }

  function filteredSubnets() {
    if (!searchQuery) return state.subnets;
    return state.subnets.filter(s => rowMatchesSearch(s, searchQuery));
  }

  async function render() {
    const content = document.getElementById('content');
    const mode = state.viewMode.subnets;
    content.innerHTML = `
      <div class="flex justify-between items-center mb-16 wrap gap-12">
        <div class="flex gap-8 wrap items-center">
          <button class="btn btn-primary" id="btn-add-subnet">+ Add Subnet</button>
          <button class="btn" id="btn-import-subnets">Import from Excel</button>
          <button class="btn" id="btn-export-subnets">Export to Excel</button>
          ${renderSearchBox('subnet-search', 'Search subnets\u2026')}
        </div>
        <div class="flex gap-12 items-center">
          <div class="text-dim" id="subnet-count-label">${state.subnets.length} subnet(s)</div>
          <div class="view-toggle">
            <button class="${mode === 'table' ? 'active' : ''}" data-mode="table">&#9776; Table</button>
            <button class="${mode === 'card' ? 'active' : ''}" data-mode="card">&#9638; Cards</button>
          </div>
        </div>
      </div>
      <div class="banner banner-info mb-16">
        <span>&#9432;</span>
        <div class="banner-content">Devices inside a subnet's CIDR range automatically inherit that subnet's tags for any tag value they don't already set themselves.</div>
      </div>
      <div id="subnets-body"></div>
    `;
    renderBody();
    document.getElementById('btn-add-subnet').addEventListener('click', () => openForm(null));
    document.getElementById('btn-import-subnets').addEventListener('click', () => openImportDialog());
    document.getElementById('btn-export-subnets').addEventListener('click', handleExport);
    content.querySelectorAll('.view-toggle button').forEach(btn => {
      btn.addEventListener('click', () => { state.viewMode.subnets = btn.dataset.mode; saveViewModePrefs(); render(); });
    });
    const searchBox = document.getElementById('subnet-search');
    searchBox.value = searchQuery;
    searchBox.addEventListener('input', (e) => { searchQuery = e.target.value; renderBody(); });
  }

  function renderBody() {
    const body = document.getElementById('subnets-body');
    const subnets = filteredSubnets();
    document.getElementById('subnet-count-label').textContent =
      searchQuery ? `${subnets.length} of ${state.subnets.length} subnet(s)` : `${state.subnets.length} subnet(s)`;

    if (state.subnets.length === 0) {
      body.innerHTML = emptyState({ title: 'No subnets yet', sub: 'Define a CIDR range to start tagging devices by network automatically.' });
      return;
    }
    if (subnets.length === 0) {
      body.innerHTML = emptyState({ title: 'No subnets match your search', sub: `No results for "${searchQuery}".` });
      return;
    }
    body.innerHTML = state.viewMode.subnets === 'card' ? renderCards(subnets) : `<div class="panel"><div class="table-wrap">${renderTable(subnets)}</div></div>`;
    wireRowActions();
  }

  function renderTable(subnets) {
    const rows = subnets.map(s => `
      <tr data-id="${escapeHtml(s.id)}">
        <td class="mono">${escapeHtml(s.CIDR)}</td>
        <td>${escapeHtml(s.Description)}</td>
        <td>${TagFields.renderBadges('subnets', s.tags) || '<span class="text-faint">&mdash;</span>'}</td>
        <td>
          <button class="btn btn-sm" data-act="edit">Edit</button>
          <button class="btn btn-sm btn-danger" data-act="delete">Delete</button>
        </td>
      </tr>
    `).join('');
    return `
      <table>
        <thead><tr><th>CIDR</th><th>Description</th><th>Tags</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function renderCards(subnets) {
    const cards = subnets.map(s => `
      <div class="data-card" data-id="${escapeHtml(s.id)}" data-open-detail="1">
        <div class="data-card-header">
          <div>
            <div class="data-card-title">${escapeHtml(s.CIDR)}</div>
            <div class="data-card-sub">${escapeHtml(s.Description || '')}</div>
          </div>
        </div>
        <div class="data-card-meta">${TagFields.renderBadges('subnets', s.tags)}</div>
        <div class="data-card-actions">
          <button class="btn btn-sm" data-act="edit">Edit</button>
          <button class="btn btn-sm btn-danger" data-act="delete">Delete</button>
        </div>
      </div>
    `).join('');
    return `<div class="card-grid">${cards}</div>`;
  }

  function wireRowActions() {
    document.querySelectorAll('#subnets-body [data-id]').forEach(el => {
      const id = el.dataset.id;
      const s = state.subnets.find(x => String(x.id) === String(id));
      el.querySelectorAll('[data-act="edit"]').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); openForm(s); }));
      el.querySelectorAll('[data-act="delete"]').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); handleDelete(s); }));
      if (el.dataset.openDetail) {
        el.addEventListener('click', () => openForm(s));
      }
    });
  }

  async function handleDelete(subnet) {
    const ok = await confirmDialog(`Delete subnet ${subnet.CIDR}? Devices in this range will no longer inherit its tags. This cannot be undone.`);
    if (!ok) return;
    try {
      await Api.deleteSubnet(subnet.id);
      state.subnets = state.subnets.filter(s => s.id !== subnet.id);
      toast('Subnet deleted', 'success');
      render();
      refreshCounts();
    } catch (e) {
      reportError(e, 'Delete failed');
    }
  }

  function openForm(subnet) {
    const isEdit = !!subnet;
    const s = subnet || {};
    const overlay = openModal(`
      <div class="modal-header">
        <h3>${isEdit ? 'Edit Subnet' : 'Add Subnet'}</h3>
        <button class="modal-close" data-act="close">&times;</button>
      </div>
      <div class="modal-body">
        <form id="subnet-form">
          <div class="form-grid mb-16">
            ${FIELDS.map(f => `
              <div class="field">
                <label>${escapeHtml(f.label)}${f.required ? '<span class="req">*</span>' : ''}</label>
                <input type="text" name="${f.key}" value="${escapeHtml(s[f.key] || '')}" placeholder="${escapeHtml(f.placeholder || '')}" ${f.required ? 'required' : ''}>
              </div>
            `).join('')}
          </div>
          <div class="panel-header" style="padding:0 0 10px 0;border-bottom:1px solid var(--border-soft);margin-bottom:14px;">
            <h2 style="font-size:13px;color:var(--text-dim);">Tags</h2>
          </div>
          <div class="form-grid">
            ${TagFields.renderFormFields('subnets', s.tags)}
          </div>
        </form>
      </div>
      <div class="modal-footer">
        ${isEdit ? `<button class="btn btn-danger" data-act="delete" style="margin-right:auto;">Delete</button>` : ''}
        <button class="btn" data-act="close">Cancel</button>
        <button class="btn btn-primary" data-act="save">${isEdit ? 'Save Changes' : 'Add Subnet'}</button>
      </div>
    `);
    overlay.querySelectorAll('[data-act="close"]').forEach(el => el.addEventListener('click', () => closeModal(overlay)));
    if (isEdit) {
      overlay.querySelector('[data-act="delete"]').addEventListener('click', async () => { closeModal(overlay); await handleDelete(s); });
    }
    overlay.querySelector('[data-act="save"]').addEventListener('click', async () => {
      const form = overlay.querySelector('#subnet-form');
      if (!form.reportValidity()) return;
      const fd = new FormData(form);
      const cidrValue = fd.get('CIDR');
      if (!isValidCidr(cidrValue)) {
        toast('CIDR must look like 10.1.1.0/24', 'warn');
        return;
      }
      const payload = isEdit ? { id: s.id } : {};
      for (const [k, v] of fd.entries()) {
        if (!k.startsWith('tag__')) payload[k] = v;
      }
      payload.tags = TagFields.readFormFields(fd);
      try {
        const saved = await Api.saveSubnet(payload);
        const newSubnet = saved.subnet || saved;
        if (isEdit) state.subnets = state.subnets.map(x => x.id === s.id ? newSubnet : x);
        else state.subnets.push(newSubnet);
        toast(isEdit ? 'Subnet updated' : 'Subnet added', 'success');
        closeModal(overlay);
        render();
        refreshCounts();
      } catch (e) {
        reportError(e, 'Save failed');
      }
    });
  }

  function handleExport() {
    downloadUrl(Api.exportSubnetsUrl(), 'subnets_export.xlsx')
      .then(() => toast('Subnets exported', 'success'))
      .catch(e => reportError(e, 'Export failed'));
  }

  function openImportDialog() {
    const overlay = openModal(`
      <div class="modal-header">
        <h3>Import Subnets from Excel</h3>
        <button class="modal-close" data-act="close">&times;</button>
      </div>
      <div class="modal-body">
        <div class="import-dialog-section">
          <h4>1. Choose file</h4>
          <input type="file" id="import-file" accept=".xlsx,.xls">
          <div class="field-hint" style="margin-top:6px;">Tip: use "Export to Excel" first to get a template with the right columns, including any custom tags.</div>
        </div>
        <div class="import-dialog-section" id="import-sheet-section" style="display:none;">
          <h4>2. Choose sheet</h4>
          <select id="import-sheet-select"></select>
        </div>
        <div class="import-dialog-section">
          <h4>3. Import mode</h4>
          <div class="radio-row">
            <label><input type="radio" name="import-mode" value="merge" checked> Merge (add/update, keep existing)</label>
            <label><input type="radio" name="import-mode" value="replace"> Replace (clear all, then import)</label>
          </div>
        </div>
        <div id="import-preview" class="text-dim" style="font-size:12.5px;"></div>
      </div>
      <div class="modal-footer">
        <button class="btn" data-act="close">Cancel</button>
        <button class="btn btn-primary" id="btn-do-import" disabled>Import</button>
      </div>
    `);
    overlay.querySelectorAll('[data-act="close"]').forEach(b => b.addEventListener('click', () => closeModal(overlay)));

    let workbook = null;
    const fileInput = overlay.querySelector('#import-file');
    const sheetSection = overlay.querySelector('#import-sheet-section');
    const sheetSelect = overlay.querySelector('#import-sheet-select');
    const importBtn = overlay.querySelector('#btn-do-import');
    const preview = overlay.querySelector('#import-preview');

    fileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const buf = await file.arrayBuffer();
      workbook = XLSX.read(buf, { type: 'array' });
      const names = workbook.SheetNames;
      const preferred = names.find(n => n.toLowerCase() === 'subnets') || names[0];
      sheetSelect.innerHTML = names.map(n => `<option value="${escapeHtml(n)}"${n === preferred ? ' selected' : ''}>${escapeHtml(n)}</option>`).join('');
      sheetSection.style.display = '';
      importBtn.disabled = false;
      updatePreview();
    });
    sheetSelect.addEventListener('change', updatePreview);

    function updatePreview() {
      if (!workbook) return;
      const sheet = workbook.Sheets[sheetSelect.value];
      const rows = XLSX.utils.sheet_to_json(sheet, { defval: '' });
      preview.textContent = `${rows.length} row(s) found in "${sheetSelect.value}".`;
    }

    importBtn.addEventListener('click', async () => {
      if (!workbook) return;
      const sheet = workbook.Sheets[sheetSelect.value];
      const rows = XLSX.utils.sheet_to_json(sheet, { defval: '' });
      const mode = overlay.querySelector('input[name="import-mode"]:checked').value;
      const subnetTagDefs = TagFields.defsForScope('subnets');

      const records = [];
      let skippedInvalidCidr = 0;
      for (const r of rows) {
        const cidr = String(r['CIDR'] || '').trim();
        if (!cidr) continue;
        if (!isValidCidr(cidr)) { skippedInvalidCidr++; continue; }
        const rec = { CIDR: cidr, Description: String(r['Description'] || '') };
        rec.tags = {};
        for (const td of subnetTagDefs) {
          const v = r[td.name];
          if (v !== undefined && v !== '') rec.tags[td.id] = String(v);
        }
        records.push(rec);
      }

      try {
        importBtn.disabled = true;
        importBtn.textContent = 'Importing\u2026';
        await Api.importSubnets(records, mode);
        await TagFields.registerNewValuesFromImport('subnets', records);
        const msg = skippedInvalidCidr > 0
          ? `Imported ${records.length} subnet(s) (${mode}) \u2014 skipped ${skippedInvalidCidr} row(s) with an invalid CIDR`
          : `Imported ${records.length} subnet(s) (${mode})`;
        toast(msg, skippedInvalidCidr > 0 ? 'warn' : 'success');
        closeModal(overlay);
        await reloadAllData();
        render();
        refreshCounts();
      } catch (e) {
        reportError(e, 'Import failed');
        importBtn.disabled = false;
        importBtn.textContent = 'Import';
      }
    });
  }

  return { render };
})();
