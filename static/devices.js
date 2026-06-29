// ============================================================================
// DEVICES VIEW
//
// Collector Region is the one field that stays permanently built-in --
// mandatory, drives YAML generation grouping. Everything else that used
// to be a hardcoded field (Device Class, Device Category, Device Type,
// Operating Region, Geolocation, Region, Center) only appears as a form
// field once someone creates the matching tag through the Tags module.
// Existing data from before this change gets migrated into tags
// automatically (see migrations.py) so nothing is lost on upgrade.
// ============================================================================

const Devices = (() => {
  let searchQuery = '';
  const tc = TableControls.create('devices');

  function missingCreds(d) {
    return !d.snmpUser || !d.authProtocol || !d.authKey || !d.privProtocol || !d.privKey;
  }

  // Device Class is now tag-driven (no longer a guaranteed fixed field),
  // so ICMP-forcing is checked by resolved tag name, same as the backend.
  function resolvedDeviceClass(d) {
    const deviceClassDef = state.tagDefs.find(td => td.name === 'Device Class' && (td.scopes || []).includes('devices'));
    if (!deviceClassDef) return '';
    return (d.tags || {})[deviceClassDef.id] || '';
  }

  function isIcmpForced(d) {
    const cls = resolvedDeviceClass(d).trim().toLowerCase();
    const cfg = (d['Config Type'] || '').trim().toLowerCase();
    return cls === 'storage' || cfg === 'icmp' || cfg === 'snmp trap';
  }

  function credBadge(d) {
    if (isIcmpForced(d)) return `<span class="badge badge-neutral">ICMP-only</span>`;
    if (missingCreds(d)) return `<span class="badge badge-warn">SNMP ${icon('warning', { size: 12 })}</span>`;
    return `<span class="badge badge-ok">SNMP</span>`;
  }

  function regionBadge(d) {
    if (!d['Collector Region']) return `<span class="badge badge-danger">missing *</span>`;
    return escapeHtml(d['Collector Region']);
  }

  function filteredDevices() {
    if (!searchQuery) return state.devices;
    return state.devices.filter(d => rowMatchesSearch(d, searchQuery));
  }

  async function render() {
    const content = document.getElementById('content');
    const mode = state.viewMode.devices;
    content.innerHTML = `
      <div class="flex justify-between items-center mb-16 wrap gap-12">
        <div class="flex gap-8 wrap items-center">
          <button class="btn btn-primary" id="btn-add-device">${icon('plus', { size: 14 })} Add Device</button>
          <button class="btn" id="btn-import-devices">${icon('import', { size: 14 })} Import from Excel</button>
          <button class="btn" id="btn-export-devices">${icon('export', { size: 14 })} Export to Excel</button>
          ${renderSearchBox('device-search', 'Search devices\u2026')}
        </div>
        <div class="flex gap-12 items-center">
          <div class="text-dim" id="device-count-label">${state.devices.length} device(s)</div>
          <div class="view-toggle">
            <button class="${mode === 'table' ? 'active' : ''}" data-mode="table">${icon('table', { size: 14 })} Table</button>
            <button class="${mode === 'card' ? 'active' : ''}" data-mode="card">${icon('grid', { size: 14 })} Cards</button>
          </div>
        </div>
      </div>
      <div id="devices-body"></div>
    `;
    renderBody();

    document.getElementById('btn-add-device').addEventListener('click', () => openForm(null));
    document.getElementById('btn-import-devices').addEventListener('click', () => openImportDialog());
    document.getElementById('btn-export-devices').addEventListener('click', handleExport);
    content.querySelectorAll('.view-toggle button').forEach(btn => {
      btn.addEventListener('click', () => { state.viewMode.devices = btn.dataset.mode; saveViewModePrefs(); render(); });
    });
    const searchBox = document.getElementById('device-search');
    searchBox.value = searchQuery;
    searchBox.addEventListener('input', (e) => { searchQuery = e.target.value; tc.resetPage(); renderBody(); });
  }

  const SORT_RESOLVERS = {
    'Collector Region': (d) => d['Collector Region'] || '',
    status: (d) => isIcmpForced(d) ? 'icmp' : (missingCreds(d) ? 'warn' : 'ok'),
  };

  function renderBody() {
    const body = document.getElementById('devices-body');
    const devices = filteredDevices();
    document.getElementById('device-count-label').textContent =
      searchQuery ? `${devices.length} of ${state.devices.length} device(s)` : `${state.devices.length} device(s)`;

    if (state.devices.length === 0) {
      body.innerHTML = emptyState({ title: 'No devices yet', sub: 'Add one manually or import a spreadsheet to get started.' });
      return;
    }
    if (devices.length === 0) {
      body.innerHTML = emptyState({ title: 'No devices match your search', sub: `No results for "${searchQuery}".` });
      return;
    }

    if (state.viewMode.devices === 'card') {
      const { pageRows, controlsHtml } = tc.apply(devices, { ...SORT_RESOLVERS, ...TagFields.tagSortResolvers('devices') });
      body.innerHTML = `${renderCards(pageRows)}<div class="panel" style="margin-top:12px;">${controlsHtml}</div>`;
      wireRowActions();
      tc.wirePager(body, renderBody);
      return;
    }

    const { pageRows, controlsHtml } = tc.apply(devices, { ...SORT_RESOLVERS, ...TagFields.tagSortResolvers('devices') });
    body.innerHTML = `<div class="panel"><div class="table-wrap">${renderTable(pageRows)}</div>${controlsHtml}</div>`;
    wireRowActions();
    tc.wireHeaders(body, renderBody);
    tc.wirePager(body, renderBody);
  }

  function renderTable(devices) {
    const rows = devices.map(d => `
      <tr data-id="${escapeHtml(d.id)}">
        <td class="mono">${escapeHtml(d.IP)}</td>
        <td>${escapeHtml(d.Device)}</td>
        <td>${regionBadge(d)}</td>
        <td>${escapeHtml(d['Config Type'])}</td>
        ${TagFields.renderTableCells('devices', d.tags)}
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
          ${tc.sortableHeader('IP', 'IP')}${tc.sortableHeader('Device', 'Device')}${tc.sortableHeader('Collector Region', 'Collector Region')}${tc.sortableHeader('Config Type', 'Config Type')}
          ${TagFields.renderTableHeaders('devices', tc)}
          ${tc.sortableHeader('Status', 'status')}<th></th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function renderCards(devices) {
    const cards = devices.map(d => `
      <div class="data-card" data-id="${escapeHtml(d.id)}" data-open-detail="1">
        <div class="data-card-header">
          <div>
            <div class="data-card-title">${escapeHtml(d.Device || '(unnamed)')}</div>
            <div class="data-card-sub">${escapeHtml(d.IP)}</div>
          </div>
          ${credBadge(d)}
        </div>
        <div class="data-card-meta">
          ${regionBadge(d)}
          ${TagFields.renderBadges('devices', d.tags)}
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
    document.querySelectorAll('#devices-body [data-id]').forEach(el => {
      const id = el.dataset.id;
      const device = state.devices.find(d => String(d.id) === String(id));
      el.querySelectorAll('[data-act="edit"]').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); openForm(device); }));
      el.querySelectorAll('[data-act="delete"]').forEach(b => b.addEventListener('click', (e) => { e.stopPropagation(); handleDelete(device); }));
      // Clicking the card itself (outside the action buttons) opens the
      // same edit form -- previously this did nothing, which made the
      // card view feel broken.
      if (el.dataset.openDetail) {
        el.addEventListener('click', () => openForm(device));
      }
    });
  }

  async function handleDelete(device) {
    const ok = await confirmDialog(`Delete device ${device.Device || device.IP}? This cannot be undone.`);
    if (!ok) return;
    try {
      await Api.deleteDevice(device.id);
      state.devices = state.devices.filter(d => d.id !== device.id);
      toast('Device deleted', 'success');
      if (state.currentView === 'devices') render();
      refreshCounts();
    } catch (e) {
      reportError(e, 'Delete failed');
    }
  }

  function listOptions(listKey, currentValue) {
    const items = (state.lists[listKey] || []);
    const opts = items.map(v => `<option value="${escapeHtml(v)}"${v === currentValue ? ' selected' : ''}>${escapeHtml(v)}</option>`);
    return `<option value="">&mdash; none &mdash;</option>${opts.join('')}`;
  }

  function openForm(device) {
    const isEdit = !!device;
    const d = device || {};
    const initialCfg = (d['Config Type'] || '').toLowerCase();
    const initialIcmpForced = initialCfg === 'icmp' || initialCfg === 'snmp trap';

    const overlay = openModal(`
      <div class="modal-header">
        <h3>${isEdit ? 'Edit Device' : 'Add Device'}</h3>
        <button class="modal-close" data-act="close">&times;</button>
      </div>
      <div class="modal-body">
        <form id="device-form">
          <div class="form-grid mb-16">
            <div class="field">
              <label>IP<span class="req">*</span></label>
              <input type="text" name="IP" value="${escapeHtml(d.IP || '')}" required placeholder="e.g. 10.1.1.1">
              <span class="field-hint" id="ip-validation-hint"></span>
            </div>
            <div class="field">
              <label>Device</label>
              <input type="text" name="Device" value="${escapeHtml(d.Device || '')}">
            </div>
            <div class="field">
              <label>Collector Region<span class="req">*</span></label>
              <select name="Collector Region">${listOptions('collectorRegions', d['Collector Region'] || '')}</select>
              <span class="field-hint">Needed for this device to appear in generated YAML. Devices without it are saved but excluded at generate time.</span>
            </div>
            <div class="field">
              <label>Config Type</label>
              <select name="Config Type" id="config-type-select">
                <option value="">&mdash; none &mdash;</option>
                ${['SNMP', 'ICMP', 'SNMP Trap'].map(v => `<option value="${v}"${(d['Config Type'] || '') === v ? ' selected' : ''}>${v}</option>`).join('')}
              </select>
              <span class="field-hint">ICMP / SNMP Trap force ping-only and hide the credential fields below.</span>
            </div>
            <div class="field span-2">
              <label>Remarks</label>
              <input type="text" name="Remarks" value="${escapeHtml(d.Remarks || '')}">
            </div>
          </div>

          ${TagFields.defsForScope('devices').length > 0 ? `
            <div class="panel-header" style="padding:0 0 10px 0;border-bottom:1px solid var(--border-soft);margin-bottom:14px;">
              <h2 style="font-size:13px;color:var(--text-dim);">Tags</h2>
            </div>
            <div class="form-grid mb-16">
              ${TagFields.renderFormFields('devices', d.tags)}
            </div>
          ` : ''}

          <div id="creds-section" style="display:${initialIcmpForced ? 'none' : 'block'};">
            <div class="panel-header" style="padding:0 0 10px 0;border-bottom:1px solid var(--border-soft);margin-bottom:14px;">
              <h2 style="font-size:13px;color:var(--text-dim);">SNMPv3 Credentials <span class="req">*</span></h2>
            </div>
            <div class="field-hint mb-12">Required for SNMP polling. Devices missing any of these are still included at generate time, flagged as needing attention.</div>
            <div class="form-grid">
              <div class="field">
                <label>SNMP User</label>
                <input type="text" name="snmpUser" value="${escapeHtml(d.snmpUser || '')}">
              </div>
              <div class="field">
                <label>Auth Protocol</label>
                <select name="authProtocol">${['SHA', 'MD5'].map(v => `<option value="${v}"${(d.authProtocol || 'SHA') === v ? ' selected' : ''}>${v}</option>`).join('')}</select>
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
                <select name="privProtocol">${['AES', 'DES'].map(v => `<option value="${v}"${(d.privProtocol || 'AES') === v ? ' selected' : ''}>${v}</option>`).join('')}</select>
              </div>
              <div class="field">
                <label>Priv Key</label>
                <div class="password-field">
                  <input type="password" name="privKey" value="${escapeHtml(d.privKey || '')}">
                  <button type="button" class="password-toggle" data-toggle="privKey">show</button>
                </div>
              </div>
            </div>
          </div>
          <div id="creds-hidden-note" class="field-hint" style="display:${initialIcmpForced ? 'block' : 'none'};">
            SNMPv3 credentials are hidden because this device is configured for ICMP / SNMP Trap (ping-only, no SNMP polling).
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

    // Toggle the credentials block live as Config Type changes, so the
    // person doesn't fill in SNMP creds for a device that's about to be
    // ICMP-only (or vice versa) without realizing it'll be hidden/ignored.
    const configSelect = overlay.querySelector('#config-type-select');
    const credsSection = overlay.querySelector('#creds-section');
    const credsHiddenNote = overlay.querySelector('#creds-hidden-note');
    configSelect.addEventListener('change', () => {
      const cfg = configSelect.value.toLowerCase();
      const forced = cfg === 'icmp' || cfg === 'snmp trap';
      credsSection.style.display = forced ? 'none' : 'block';
      credsHiddenNote.style.display = forced ? 'block' : 'none';
    });

    // Live IP format feedback as the person types, rather than only at save time.
    const ipInput = overlay.querySelector('input[name="IP"]');
    const ipHint = overlay.querySelector('#ip-validation-hint');
    ipInput.addEventListener('input', () => {
      if (!ipInput.value.trim()) { ipHint.textContent = ''; return; }
      ipHint.textContent = isValidIp(ipInput.value) ? '' : 'Doesn\u2019t look like a valid IP address.';
      ipHint.style.color = isValidIp(ipInput.value) ? '' : 'var(--red)';
    });

    if (isEdit) {
      overlay.querySelector('[data-act="delete"]').addEventListener('click', async () => { closeModal(overlay); await handleDelete(d); });
    }
    overlay.querySelector('[data-act="save"]').addEventListener('click', async () => {
      const form = overlay.querySelector('#device-form');
      if (!form.reportValidity()) return;
      const ipValue = ipInput.value.trim();
      if (!isValidIp(ipValue)) {
        toast('Please enter a valid IP address', 'warn');
        ipInput.focus();
        return;
      }
      const fd = new FormData(form);
      const payload = isEdit ? { id: d.id } : {};
      const cfg = (fd.get('Config Type') || '').toLowerCase();
      const forced = cfg === 'icmp' || cfg === 'snmp trap';
      for (const [k, v] of fd.entries()) {
        if (k.startsWith('tag__')) continue;
        // Don't send credential fields at all when they're hidden/forced
        // ICMP -- avoids saving stale or irrelevant creds for a device
        // that won't use them.
        if (forced && ['snmpUser', 'authProtocol', 'authKey', 'privProtocol', 'privKey'].includes(k)) continue;
        payload[k] = v;
      }
      payload.tags = TagFields.readFormFields(fd);
      try {
        const saved = await Api.saveDevice(payload);
        const newDevice = saved.device || saved;
        if (isEdit) state.devices = state.devices.map(dev => dev.id === d.id ? newDevice : dev);
        else state.devices.push(newDevice);
        toast(isEdit ? 'Device updated' : 'Device added', 'success');
        closeModal(overlay);
        if (state.currentView === 'devices') render();
        refreshCounts();
      } catch (e) {
        reportError(e, 'Save failed');
      }
    });
  }

  // -------------------------------------------------------------------------
  // Excel import / export
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
    'Config Type': ['Config Type', 'ConfigType'],
    'Device': ['Device'], 'IP': ['IP'], 'Remarks': ['Remarks'],
  };

  function readAliased(row, aliases) {
    for (const a of aliases) if (row[a] !== undefined && row[a] !== '') return String(row[a]);
    return '';
  }

  function handleExport() {
    downloadUrl(Api.exportDevicesUrl(), 'devices_export.xlsx')
      .then(() => toast('Devices exported', 'success'))
      .catch(e => reportError(e, 'Export failed'));
  }

  // Collector Region is the one fixed list left (everything else is a
  // dynamic tag, handled by TagFields.registerNewValuesFromImport).
  // Import writes whatever's in the spreadsheet's Collector Region column
  // straight onto each device -- correct, since import needs to allow a
  // brand-new region -- but without this, that new value would be saved
  // on the device yet invisible in the Manage Lists dropdown, since the
  // dropdown only shows what's actually in lists.collectorRegions.
  async function registerNewCollectorRegionsFromImport(records) {
    const existing = new Set(state.lists.collectorRegions || []);
    const newValues = new Set();
    for (const rec of records) {
      const region = (rec['Collector Region'] || '').trim();
      if (region && !existing.has(region)) newValues.add(region);
    }
    if (newValues.size === 0) return;
    const updated = [...existing, ...newValues];
    try {
      await Api.setList('collectorRegions', updated);
      state.lists.collectorRegions = updated;
    } catch (e) {
      console.error('Failed to register new Collector Region value(s) from import', e);
    }
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
      const deviceTagDefs = TagFields.defsForScope('devices');

      const records = [];
      let skippedInvalidIp = 0;
      for (const r of rows) {
        const ip = String(r['IP'] || '').trim();
        if (!ip) continue;
        if (!isValidIp(ip)) { skippedInvalidIp++; continue; }
        const rec = {};
        for (const [field, aliases] of Object.entries(FIELD_ALIASES)) rec[field] = readAliased(r, aliases);
        rec.snmpUser = readAliased(r, CRED_ALIASES.snmpUser);
        rec.authProtocol = readAliased(r, CRED_ALIASES.authProtocol) || 'SHA';
        rec.authKey = readAliased(r, CRED_ALIASES.authKey);
        rec.privProtocol = readAliased(r, CRED_ALIASES.privProtocol) || 'AES';
        rec.privKey = readAliased(r, CRED_ALIASES.privKey);
        rec.tags = {};
        for (const td of deviceTagDefs) {
          const v = r[td.name];
          if (v !== undefined && v !== '') rec.tags[td.id] = String(v);
        }
        records.push(rec);
      }

      // Validate before writing.  If the server returns findings, show the
      // modal and let the user decide.  On confirm (or if no findings),
      // proceed directly to the write.
      importBtn.disabled = true;
      importBtn.textContent = 'Validating\u2026';
      let findings = [], diff = null;
      try {
        const result = await Api.validateImportDevices(records, mode);
        findings = result.findings || [];
        diff = result.diff || null;
      } catch (e) {
        reportError(e, 'Validation failed');
        importBtn.disabled = false;
        importBtn.textContent = 'Import';
        return;
      }

      async function doImport() {
        importBtn.disabled = true;
        importBtn.textContent = 'Importing\u2026';
        try {
          await Api.importDevices(records, mode);
          await TagFields.registerNewValuesFromImport('devices', records);
          await registerNewCollectorRegionsFromImport(records);
          const msg = skippedInvalidIp > 0
            ? `Imported ${records.length} device(s) (${mode}) \u2014 skipped ${skippedInvalidIp} row(s) with an invalid IP`
            : `Imported ${records.length} device(s) (${mode})`;
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
      }

      showImportPreviewModal(findings, diff, state.tagDefs, 'Devices', doImport);
      importBtn.disabled = false;
      importBtn.textContent = 'Import';
    });
  }

  return { render, missingCreds, isIcmpForced, _openFormExternal: openForm };
})();
