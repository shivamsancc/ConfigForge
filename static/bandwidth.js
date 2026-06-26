// ============================================================================
// BANDWIDTH CAPPING VIEW
// ============================================================================

const Bandwidth = (() => {
  let searchQuery = '';

  const FIELDS = [
    { key: 'IP', label: 'IP', required: true },
    { key: 'Interface', label: 'Interface', required: true },
    { key: 'Allocated BW', label: 'Allocated BW' },
    { key: 'Region', label: 'Region' },
    { key: 'Center', label: 'Center' },
    { key: 'Link Type', label: 'Link Type' },
    { key: 'Interface_description', label: 'Interface Description' },
  ];

  function filteredRows() {
    if (!searchQuery) return state.bandwidth;
    return state.bandwidth.filter(b => rowMatchesSearch(b, searchQuery));
  }

  async function render() {
    const content = document.getElementById('content');
    const mode = state.viewMode.bandwidth;
    content.innerHTML = `
      <div class="flex justify-between items-center mb-16 wrap gap-12">
        <div class="flex gap-8 wrap items-center">
          <button class="btn btn-primary" id="btn-add-bw">+ Add Row</button>
          <button class="btn" id="btn-import-bw">Import from Excel</button>
          <button class="btn" id="btn-export-bw">Export to Excel</button>
          ${renderSearchBox('bw-search', 'Search bandwidth rows\u2026')}
        </div>
        <div class="flex gap-12 items-center">
          <div class="text-dim" id="bw-count-label">${state.bandwidth.length} row(s)</div>
          <div class="view-toggle">
            <button class="${mode === 'table' ? 'active' : ''}" data-mode="table">&#9776; Table</button>
            <button class="${mode === 'card' ? 'active' : ''}" data-mode="card">&#9638; Cards</button>
          </div>
        </div>
      </div>
      <div id="bw-body"></div>
    `;
    renderBody();
    document.getElementById('btn-add-bw').addEventListener('click', () => openForm(null));
    document.getElementById('btn-import-bw').addEventListener('click', () => openImportDialog());
    document.getElementById('btn-export-bw').addEventListener('click', handleExport);
    content.querySelectorAll('.view-toggle button').forEach(btn => {
      btn.addEventListener('click', () => { state.viewMode.bandwidth = btn.dataset.mode; saveViewModePrefs(); render(); });
    });
    const searchBox = document.getElementById('bw-search');
    searchBox.value = searchQuery;
    searchBox.addEventListener('input', (e) => { searchQuery = e.target.value; renderBody(); });
  }

  function renderBody() {
    const body = document.getElementById('bw-body');
    const rows = filteredRows();
    document.getElementById('bw-count-label').textContent =
      searchQuery ? `${rows.length} of ${state.bandwidth.length} row(s)` : `${state.bandwidth.length} row(s)`;

    if (state.bandwidth.length === 0) {
      body.innerHTML = emptyState({ title: 'No bandwidth caps yet', sub: 'Add a row manually or import a spreadsheet.' });
      return;
    }
    if (rows.length === 0) {
      body.innerHTML = emptyState({ title: 'No rows match your search', sub: `No results for "${searchQuery}".` });
      return;
    }
    body.innerHTML = state.viewMode.bandwidth === 'card' ? renderCards(rows) : `<div class="panel"><div class="table-wrap">${renderTable(rows)}</div></div>`;
    wireRowActions();
  }

  function renderTable(rows) {
    const trs = rows.map(b => `
      <tr data-id="${escapeHtml(b.id)}">
        <td class="mono">${escapeHtml(b.IP)}</td>
        <td class="mono">${escapeHtml(b.Interface)}</td>
        <td>${escapeHtml(b['Allocated BW'])}</td>
        <td>${escapeHtml(b.Region)}</td>
        <td>${escapeHtml(b.Center)}</td>
        <td>${escapeHtml(b['Link Type'])}</td>
        <td>${escapeHtml(b.Interface_description)}</td>
        <td>${TagFields.renderBadges('bandwidth', b.tags) || '<span class="text-faint">&mdash;</span>'}</td>
        <td>
          <button class="btn btn-sm" data-act="edit">Edit</button>
          <button class="btn btn-sm btn-danger" data-act="delete">Delete</button>
        </td>
      </tr>
    `).join('');
    return `
      <table>
        <thead><tr>
          <th>IP</th><th>Interface</th><th>Allocated BW</th><th>Region</th>
          <th>Center</th><th>Link Type</th><th>Interface Description</th><th>Tags</th><th></th>
        </tr></thead>
        <tbody>${trs}</tbody>
      </table>
    `;
  }

  function renderCards(rows) {
    const cards = rows.map(b => `
      <div class="data-card" data-id="${escapeHtml(b.id)}" data-open-detail="1">
        <div class="data-card-header">
          <div>
            <div class="data-card-title">${escapeHtml(b.Interface)}</div>
            <div class="data-card-sub">${escapeHtml(b.IP)}</div>
          </div>
          ${b['Allocated BW'] ? `<span class="badge badge-neutral">${escapeHtml(b['Allocated BW'])}</span>` : ''}
        </div>
        <div class="data-card-meta">
          ${b['Link Type'] ? `<span class="badge badge-neutral">${escapeHtml(b['Link Type'])}</span>` : ''}
          ${TagFields.renderBadges('bandwidth', b.tags)}
        </div>
        <div class="data-card-actions">
          <button class="btn btn-sm" data-act="edit">Edit</button>
          <button class="btn btn-sm btn-danger" data-act="delete">Delete</button>
        </div>
      </div>
    `).join('');
    return `<div class="card-grid">${cards}</div>`;
  }

  function wireRowActions() {
    document.querySelectorAll('#bw-body [data-id]').forEach(el => {
      const id = el.dataset.id;
      const row = state.bandwidth.find(b => String(b.id) === String(id));
      el.querySelectorAll('[data-act="edit"]').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); openForm(row); }));
      el.querySelectorAll('[data-act="delete"]').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); handleDelete(row); }));
      if (el.dataset.openDetail) {
        el.addEventListener('click', () => openForm(row));
      }
    });
  }

  async function handleDelete(row) {
    const ok = await confirmDialog(`Delete bandwidth row ${row.IP} / ${row.Interface}? This cannot be undone.`);
    if (!ok) return;
    try {
      await Api.deleteBandwidth(row.id);
      state.bandwidth = state.bandwidth.filter(b => b.id !== row.id);
      toast('Row deleted', 'success');
      render();
      refreshCounts();
    } catch (e) {
      reportError(e, 'Delete failed');
    }
  }

  function openForm(row) {
    const isEdit = !!row;
    const b = row || {};
    const overlay = openModal(`
      <div class="modal-header">
        <h3>${isEdit ? 'Edit Bandwidth Row' : 'Add Bandwidth Row'}</h3>
        <button class="modal-close" data-act="close">&times;</button>
      </div>
      <div class="modal-body">
        <form id="bw-form">
          <div class="form-grid mb-16">
            ${FIELDS.map(f => `
              <div class="field">
                <label>${escapeHtml(f.label)}${f.required ? '<span class="req">*</span>' : ''}</label>
                <input type="text" name="${f.key}" value="${escapeHtml(b[f.key] || '')}" ${f.required ? 'required' : ''}>
                ${f.key === 'IP' ? '<span class="field-hint" id="bw-ip-validation-hint"></span>' : ''}
              </div>
            `).join('')}
          </div>
          <div class="panel-header" style="padding:0 0 10px 0;border-bottom:1px solid var(--border-soft);margin-bottom:14px;">
            <h2 style="font-size:13px;color:var(--text-dim);">Tags</h2>
          </div>
          <div class="form-grid">
            ${TagFields.renderFormFields('bandwidth', b.tags)}
          </div>
        </form>
      </div>
      <div class="modal-footer">
        ${isEdit ? `<button class="btn btn-danger" data-act="delete" style="margin-right:auto;">Delete</button>` : ''}
        <button class="btn" data-act="close">Cancel</button>
        <button class="btn btn-primary" data-act="save">${isEdit ? 'Save Changes' : 'Add Row'}</button>
      </div>
    `);
    overlay.querySelectorAll('[data-act="close"]').forEach(el => el.addEventListener('click', () => closeModal(overlay)));
    if (isEdit) {
      overlay.querySelector('[data-act="delete"]').addEventListener('click', async () => { closeModal(overlay); await handleDelete(b); });
    }

    const ipInput = overlay.querySelector('input[name="IP"]');
    const ipHint = overlay.querySelector('#bw-ip-validation-hint');
    ipInput.addEventListener('input', () => {
      if (!ipInput.value.trim()) { ipHint.textContent = ''; return; }
      ipHint.textContent = isValidIp(ipInput.value) ? '' : 'Doesn\u2019t look like a valid IP address.';
      ipHint.style.color = isValidIp(ipInput.value) ? '' : 'var(--red)';
    });

    overlay.querySelector('[data-act="save"]').addEventListener('click', async () => {
      const form = overlay.querySelector('#bw-form');
      if (!form.reportValidity()) return;
      if (!isValidIp(ipInput.value)) {
        toast('Please enter a valid IP address', 'warn');
        ipInput.focus();
        return;
      }
      const fd = new FormData(form);
      const payload = isEdit ? { id: b.id } : {};
      for (const [k, v] of fd.entries()) {
        if (!k.startsWith('tag__')) payload[k] = v;
      }
      payload.tags = TagFields.readFormFields(fd);
      try {
        const saved = await Api.saveBandwidth(payload);
        const newRow = saved.row || saved;
        if (isEdit) state.bandwidth = state.bandwidth.map(r => r.id === b.id ? newRow : r);
        else state.bandwidth.push(newRow);
        toast(isEdit ? 'Row updated' : 'Row added', 'success');
        closeModal(overlay);
        render();
        refreshCounts();
      } catch (e) {
        reportError(e, 'Save failed');
      }
    });
  }

  function handleExport() {
    downloadUrl(Api.exportBandwidthUrl(), 'bandwidth_export.xlsx')
      .then(() => toast('Bandwidth caps exported', 'success'))
      .catch(e => reportError(e, 'Export failed'));
  }

  function openImportDialog() {
    const overlay = openModal(`
      <div class="modal-header">
        <h3>Import Bandwidth Caps from Excel</h3>
        <button class="modal-close" data-act="close">&times;</button>
      </div>
      <div class="modal-body">
        <div class="import-dialog-section">
          <h4>1. Choose file</h4>
          <input type="file" id="import-file" accept=".xlsx,.xls">
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
      const preferred = names.find(n => n.toLowerCase() === 'bandwidth_capping') || names[0];
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
      const bwTagDefs = TagFields.defsForScope('bandwidth');

      const records = [];
      let skippedInvalidIp = 0;
      for (const r of rows) {
        const ip = String(r['IP'] || '').trim();
        if (!ip || !String(r['Interface'] || '').trim()) continue;
        if (!isValidIp(ip)) { skippedInvalidIp++; continue; }
        const rec = {};
        for (const f of FIELDS) rec[f.key] = String(r[f.key] || '');
        rec.tags = {};
        for (const td of bwTagDefs) {
          const v = r[td.name];
          if (v !== undefined && v !== '') rec.tags[td.id] = String(v);
        }
        records.push(rec);
      }

      try {
        importBtn.disabled = true;
        importBtn.textContent = 'Importing\u2026';
        await Api.importBandwidth(records, mode);
        await TagFields.registerNewValuesFromImport('bandwidth', records);
        const msg = skippedInvalidIp > 0
          ? `Imported ${records.length} row(s) (${mode}) \u2014 skipped ${skippedInvalidIp} row(s) with an invalid IP`
          : `Imported ${records.length} row(s) (${mode})`;
        toast(msg, skippedInvalidIp > 0 ? 'warn' : 'success');
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
