// ============================================================================
// BANDWIDTH CAPPING VIEW
// ============================================================================

const Bandwidth = (() => {
  const FIELDS = [
    { key: 'IP', label: 'IP', required: true },
    { key: 'Interface', label: 'Interface', required: true },
    { key: 'Allocated BW', label: 'Allocated BW' },
    { key: 'Region', label: 'Region' },
    { key: 'Center', label: 'Center' },
    { key: 'Link Type', label: 'Link Type' },
    { key: 'Interface_description', label: 'Interface Description' },
  ];

  async function render() {
    const content = document.getElementById('content');
    content.innerHTML = `
      <div class="flex justify-between items-center mb-16">
        <div class="flex gap-8">
          <button class="btn btn-primary" id="btn-add-bw">+ Add Row</button>
          <button class="btn" id="btn-import-bw">Import from Excel</button>
        </div>
        <div class="text-dim">${state.bandwidth.length} row(s)</div>
      </div>
      <div class="panel">
        <div class="table-wrap">${renderTable()}</div>
      </div>
    `;
    wireTableActions();
    document.getElementById('btn-add-bw').addEventListener('click', () => openForm(null));
    document.getElementById('btn-import-bw').addEventListener('click', () => openImportDialog());
  }

  function renderTable() {
    if (state.bandwidth.length === 0) {
      return `<div class="empty-state">No bandwidth caps yet. Add one or import from Excel.</div>`;
    }
    const rows = state.bandwidth.map(b => `
      <tr data-id="${escapeHtml(b.id)}">
        <td class="mono">${escapeHtml(b.IP)}</td>
        <td class="mono">${escapeHtml(b.Interface)}</td>
        <td>${escapeHtml(b['Allocated BW'])}</td>
        <td>${escapeHtml(b.Region)}</td>
        <td>${escapeHtml(b.Center)}</td>
        <td>${escapeHtml(b['Link Type'])}</td>
        <td>${escapeHtml(b.Interface_description)}</td>
        <td>${(b.customTags || []).map(t => `<span class="badge badge-neutral">${escapeHtml(t)}</span>`).join(' ')}</td>
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
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function wireTableActions() {
    document.querySelectorAll('#content tbody tr').forEach(tr => {
      const id = tr.dataset.id;
      const row = state.bandwidth.find(b => String(b.id) === String(id));
      const editBtn = tr.querySelector('[data-act="edit"]');
      const delBtn = tr.querySelector('[data-act="delete"]');
      if (editBtn) editBtn.addEventListener('click', () => openForm(row));
      if (delBtn) delBtn.addEventListener('click', () => handleDelete(row));
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
              </div>
            `).join('')}
            <div class="field span-2">
              <label>Custom Tags</label>
              <input type="text" name="customTags" value="${escapeHtml((b.customTags || []).join(', '))}" placeholder="env:prod, site:hq">
              <span class="field-hint">Comma-separated.</span>
            </div>
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
      overlay.querySelector('[data-act="delete"]').addEventListener('click', async () => {
        closeModal(overlay);
        await handleDelete(b);
      });
    }
    overlay.querySelector('[data-act="save"]').addEventListener('click', async () => {
      const form = overlay.querySelector('#bw-form');
      if (!form.reportValidity()) return;
      const fd = new FormData(form);
      const payload = isEdit ? { id: b.id } : {};
      for (const [k, v] of fd.entries()) {
        payload[k] = k === 'customTags' ? v.split(',').map(s => s.trim()).filter(Boolean) : v;
      }
      if (!payload.customTags) payload.customTags = [];
      try {
        const saved = await Api.saveBandwidth(payload);
        const newRow = saved.bandwidth || saved.device || saved;
        if (isEdit) {
          state.bandwidth = state.bandwidth.map(r => r.id === b.id ? newRow : r);
        } else {
          state.bandwidth.push(newRow);
        }
        toast(isEdit ? 'Row updated' : 'Row added', 'success');
        closeModal(overlay);
        render();
        refreshCounts();
      } catch (e) {
        reportError(e, 'Save failed');
      }
    });
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

      const records = [];
      for (const r of rows) {
        if (!String(r['IP'] || '').trim() || !String(r['Interface'] || '').trim()) continue;
        const rec = {};
        for (const f of FIELDS) rec[f.key] = String(r[f.key] || '');
        rec.customTags = [];
        records.push(rec);
      }

      try {
        importBtn.disabled = true;
        importBtn.textContent = 'Importing…';
        await Api.importBandwidth(records, mode);
        toast(`Imported ${records.length} row(s) (${mode})`, 'success');
        closeModal(overlay);
        const fresh = await Api.getBandwidth();
        state.bandwidth = fresh.bandwidth || fresh.devices || [];
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
