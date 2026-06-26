// ============================================================================
// DEVICES VIEW
// ============================================================================

const Devices = (() => {
  const FREE_TEXT_FIELDS = [
    { key: 'IP', label: 'IP', required: true },
    { key: 'Device', label: 'Device' },
    { key: 'Operating Region', label: 'Operating Region' },
    { key: 'geolocation', label: 'Geolocation' },
    { key: 'Region', label: 'Region' },
    { key: 'Center', label: 'Center' },
  ];

  const DROPDOWN_FIELDS = [
    // "flagged" (not "required") on purpose: a device with no Collector Region
    // is a valid, save-able state — it just gets excluded from generated YAML
    // and surfaced in missingRegionDevices. HTML5 `required` would make that
    // state impossible to save, which contradicts the generate-time tracking.
    { key: 'Collector Region', label: 'Collector Region', listKey: 'collectorRegions', flagged: true },
    { key: 'Device Class', label: 'Device Class', listKey: 'deviceClasses' },
    { key: 'Device Category', label: 'Device Category', listKey: 'deviceCategories' },
    { key: 'Device Type', label: 'Device Type', listKey: 'deviceTypes' },
  ];

  function missingCreds(d) {
    return !d.snmpUser || !d.authProtocol || !d.authKey || !d.privProtocol || !d.privKey;
  }

  function isIcmpForced(d) {
    const cls = (d['Device Class'] || '').trim().toLowerCase();
    const cfg = (d['Config Type'] || '').trim().toLowerCase();
    return cls === 'storage' || cfg === 'icmp' || cfg === 'snmp trap';
  }

  function credBadge(d) {
    if (isIcmpForced(d)) return `<span class="badge badge-neutral">ICMP-only</span>`;
    if (missingCreds(d)) return `<span class="badge badge-warn">SNMP ⚠</span>`;
    return `<span class="badge badge-ok">SNMP</span>`;
  }

  function regionBadge(d) {
    if (!d['Collector Region']) return `<span class="badge badge-danger">missing *</span>`;
    return escapeHtml(d['Collector Region']);
  }

  async function render() {
    const content = document.getElementById('content');
    content.innerHTML = `
      <div class="flex justify-between items-center mb-16">
        <div class="flex gap-8">
          <button class="btn btn-primary" id="btn-add-device">+ Add Device</button>
          <button class="btn" id="btn-import-devices">Import from Excel</button>
        </div>
        <div class="text-dim">${state.devices.length} device(s)</div>
      </div>
      <div class="panel">
        <div class="table-wrap">
          ${renderTable()}
        </div>
      </div>
    `;
    wireTableActions();
    document.getElementById('btn-add-device').addEventListener('click', () => openForm(null));
    document.getElementById('btn-import-devices').addEventListener('click', () => openImportDialog());
  }

  function renderTable() {
    if (state.devices.length === 0) {
      return `<div class="empty-state">No devices yet. Add one or import from Excel.</div>`;
    }
    const rows = state.devices.map(d => `
      <tr data-id="${escapeHtml(d.id)}">
        <td class="mono">${escapeHtml(d.IP)}</td>
        <td>${escapeHtml(d.Device)}</td>
        <td>${regionBadge(d)}</td>
        <td>${escapeHtml(d['Config Type'])}</td>
        <td>${escapeHtml(d['Device Class'])}</td>
        <td>${escapeHtml(d['Device Category'])}</td>
        <td>${escapeHtml(d['Device Type'])}</td>
        <td>${escapeHtml(d.Region)}</td>
        <td>${escapeHtml(d.Center)}</td>
        <td>${escapeHtml(d['Operating Region'])}</td>
        <td>${escapeHtml(d.geolocation)}</td>
        <td>${(d.customTags || []).map(t => `<span class="badge badge-neutral">${escapeHtml(t)}</span>`).join(' ')}</td>
        <td>${credBadge(d)}</td>
        <td>
          <button class="btn btn-sm" data-act="edit">Edit</button>
          <button class="btn btn-sm btn-danger" data-act="delete">Delete</button>
        </td>
      </tr>
    `).join('');

    return `
      <table>
        <thead><tr>
          <th>IP</th><th>Device</th><th>Collector Region</th><th>Config Type</th>
          <th>Device Class</th><th>Device Category</th><th>Device Type</th>
          <th>Region</th><th>Center</th><th>Operating Region</th><th>Geolocation</th>
          <th>Tags</th><th>Status</th><th></th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function wireTableActions() {
    document.querySelectorAll('#content tbody tr').forEach(tr => {
      const id = tr.dataset.id;
      const device = state.devices.find(d => String(d.id) === String(id));
      const editBtn = tr.querySelector('[data-act="edit"]');
      const delBtn = tr.querySelector('[data-act="delete"]');
      if (editBtn) editBtn.addEventListener('click', () => openForm(device));
      if (delBtn) delBtn.addEventListener('click', () => handleDelete(device));
    });
  }

  async function handleDelete(device) {
    const ok = await confirmDialog(`Delete device ${device.Device || device.IP}? This cannot be undone.`);
    if (!ok) return;
    try {
      await Api.deleteDevice(device.id);
      state.devices = state.devices.filter(d => d.id !== device.id);
      toast('Device deleted', 'success');
      render();
      refreshCounts();
    } catch (e) {
      reportError(e, 'Delete failed');
    }
  }

  function listOptions(listKey, currentValue) {
    const items = (state.lists[listKey] || []);
    const opts = items.map(v => `<option value="${escapeHtml(v)}"${v === currentValue ? ' selected' : ''}>${escapeHtml(v)}</option>`);
    return `<option value="">— none —</option>${opts.join('')}`;
  }

  function openForm(device) {
    const isEdit = !!device;
    const d = device || {};

    const overlay = openModal(`
      <div class="modal-header">
        <h3>${isEdit ? 'Edit Device' : 'Add Device'}</h3>
        <button class="modal-close" data-act="close">&times;</button>
      </div>
      <div class="modal-body">
        <form id="device-form">
          <div class="form-grid mb-16">
            ${FREE_TEXT_FIELDS.map(f => `
              <div class="field">
                <label>${escapeHtml(f.label)}${f.required ? '<span class="req">*</span>' : ''}</label>
                <input type="text" name="${f.key}" value="${escapeHtml(d[f.key] || '')}" ${f.required ? 'required' : ''}>
              </div>
            `).join('')}
          </div>

          <div class="form-grid mb-16">
            ${DROPDOWN_FIELDS.map(f => `
              <div class="field">
                <label>${escapeHtml(f.label)}${f.flagged ? '<span class="req">*</span>' : ''}</label>
                <select name="${f.key}">
                  ${listOptions(f.listKey, d[f.key] || '')}
                </select>
                ${f.flagged ? `<span class="field-hint">Needed for this device to appear in generated YAML — devices without it are saved but excluded at generate time.</span>` : ''}
              </div>
            `).join('')}
            <div class="field">
              <label>Config Type</label>
              <select name="Config Type">
                <option value="">— none —</option>
                ${['SNMP', 'ICMP', 'SNMP Trap'].map(v => `<option value="${v}"${(d['Config Type'] || '') === v ? ' selected' : ''}>${v}</option>`).join('')}
              </select>
              <span class="field-hint">ICMP / SNMP Trap force ping-only regardless of credentials.</span>
            </div>
            <div class="field">
              <label>Custom Tags</label>
              <input type="text" name="customTags" value="${escapeHtml((d.customTags || []).join(', '))}" placeholder="env:prod, site:hq">
              <span class="field-hint">Comma-separated.</span>
            </div>
          </div>

          <div class="panel-header" style="padding:0 0 10px 0;border-bottom:1px solid var(--border-soft);margin-bottom:14px;">
            <h2 style="font-size:13px;color:var(--text-dim);">SNMPv3 Credentials</h2>
          </div>
          <div class="form-grid">
            <div class="field">
              <label>SNMP User</label>
              <input type="text" name="snmpUser" value="${escapeHtml(d.snmpUser || '')}">
            </div>
            <div class="field">
              <label>Auth Protocol</label>
              <select name="authProtocol">
                ${['SHA', 'MD5'].map(v => `<option value="${v}"${(d.authProtocol || 'SHA') === v ? ' selected' : ''}>${v}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label>Auth Key</label>
              <div class="password-field">
                <input type="password" name="authKey" value="${escapeHtml(d.authKey || '')}">
                <button type="button" class="password-toggle" data-toggle="authKey">show</button>
              </div>
            </div>
            <div class="field">
              <label>Priv Protocol</label>
              <select name="privProtocol">
                ${['AES', 'DES'].map(v => `<option value="${v}"${(d.privProtocol || 'AES') === v ? ' selected' : ''}>${v}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label>Priv Key</label>
              <div class="password-field">
                <input type="password" name="privKey" value="${escapeHtml(d.privKey || '')}">
                <button type="button" class="password-toggle" data-toggle="privKey">show</button>
              </div>
            </div>
          </div>
        </form>
      </div>
      <div class="modal-footer">
        ${isEdit ? `<button class="btn btn-danger" data-act="delete" style="margin-right:auto;">Delete</button>` : ''}
        <button class="btn" data-act="close">Cancel</button>
        <button class="btn btn-primary" data-act="save">${isEdit ? 'Save Changes' : 'Add Device'}</button>
      </div>
    `, { large: true });

    overlay.querySelectorAll('[data-act="close"]').forEach(b => b.addEventListener('click', () => closeModal(overlay)));
    overlay.querySelectorAll('.password-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const input = overlay.querySelector(`input[name="${btn.dataset.toggle}"]`);
        const showing = input.type === 'text';
        input.type = showing ? 'password' : 'text';
        btn.textContent = showing ? 'show' : 'hide';
      });
    });
    if (isEdit) {
      overlay.querySelector('[data-act="delete"]').addEventListener('click', async () => {
        closeModal(overlay);
        await handleDelete(d);
      });
    }
    overlay.querySelector('[data-act="save"]').addEventListener('click', async () => {
      const form = overlay.querySelector('#device-form');
      if (!form.reportValidity()) return;
      const fd = new FormData(form);
      const payload = isEdit ? { id: d.id } : {};
      for (const [k, v] of fd.entries()) {
        if (k === 'customTags') {
          payload[k] = v.split(',').map(s => s.trim()).filter(Boolean);
        } else {
          payload[k] = v;
        }
      }
      if (!payload.customTags) payload.customTags = [];
      try {
        const saved = await Api.saveDevice(payload);
        const newDevice = saved.device || saved;
        if (isEdit) {
          state.devices = state.devices.map(dev => dev.id === d.id ? newDevice : dev);
        } else {
          state.devices.push(newDevice);
        }
        toast(isEdit ? 'Device updated' : 'Device added', 'success');
        closeModal(overlay);
        render();
        refreshCounts();
      } catch (e) {
        reportError(e, 'Save failed');
      }
    });
  }

  // -------------------------------------------------------------------------
  // Excel import
  // -------------------------------------------------------------------------
  const CRED_ALIASES = {
    snmpUser: ['snmpUser', 'SNMP User', 'User', 'Username'],
    authProtocol: ['authProtocol', 'Auth Protocol', 'AuthProtocol'],
    authKey: ['authKey', 'Auth Key', 'AuthKey'],
    privProtocol: ['privProtocol', 'Priv Protocol', 'PrivProtocol'],
    privKey: ['privKey', 'Priv Key', 'PrivKey'],
  };
  const FIELD_ALIASES = {
    'Collector Region': ['Collector Region', 'CollectorRegion', 'Collector_Region'],
    'Operating Region': ['Operating Region', 'OperatingRegion'],
    'Config Type': ['Config Type', 'ConfigType'],
    'geolocation': ['geolocation', 'Geolocation'],
    'Region': ['Region'],
    'Center': ['Center'],
    'Device Class': ['Device Class', 'DeviceClass'],
    'Device Category': ['Device Category', 'DeviceCategory'],
    'Device Type': ['Device Type', 'DeviceType'],
    'Device': ['Device'],
    'IP': ['IP'],
    'Remarks': ['Remarks'],
  };

  function readAliased(row, aliases) {
    for (const a of aliases) {
      if (row[a] !== undefined && row[a] !== '') return String(row[a]);
    }
    return '';
  }

  function openImportDialog() {
    const overlay = openModal(`
      <div class="modal-header">
        <h3>Import Devices from Excel</h3>
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
      const preferred = names.find(n => n.toLowerCase() === 'devices') || names[0];
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
        if (!String(r['IP'] || '').trim()) continue;
        const rec = {};
        for (const [field, aliases] of Object.entries(FIELD_ALIASES)) {
          rec[field] = readAliased(r, aliases);
        }
        rec.snmpUser = readAliased(r, CRED_ALIASES.snmpUser);
        rec.authProtocol = readAliased(r, CRED_ALIASES.authProtocol) || 'SHA';
        rec.authKey = readAliased(r, CRED_ALIASES.authKey);
        rec.privProtocol = readAliased(r, CRED_ALIASES.privProtocol) || 'AES';
        rec.privKey = readAliased(r, CRED_ALIASES.privKey);
        rec.customTags = [];
        records.push(rec);
      }

      try {
        importBtn.disabled = true;
        importBtn.textContent = 'Importing…';
        const result = await Api.importDevices(records, mode);
        toast(`Imported ${records.length} device(s) (${mode})`, 'success');
        closeModal(overlay);
        const fresh = await Api.getDevices();
        state.devices = fresh.devices || [];
        const freshLists = await Api.getLists();
        state.lists = Object.assign(state.lists, freshLists.lists || freshLists || {});
        render();
        refreshCounts();
      } catch (e) {
        reportError(e, 'Import failed');
        importBtn.disabled = false;
        importBtn.textContent = 'Import';
      }
    });
  }

  return { render, missingCreds, isIcmpForced };
})();
