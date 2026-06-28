// ============================================================================
// GENERATE YAML VIEW
// ============================================================================

const Generate = (() => {
  async function render() {
    const content = document.getElementById('content');
    const result = state.lastGenerateResult;

    content.innerHTML = `
      <div class="flex justify-between items-center mb-16">
        <button class="btn btn-primary" id="btn-generate">${icon('generate', { size: 14 })} Generate YAML</button>
        ${result ? `<div class="text-dim">${escapeHtml(result.summary || '')}</div>` : ''}
      </div>
      <div id="generate-banners"></div>
      <div id="generate-result"></div>
    `;

    document.getElementById('btn-generate').addEventListener('click', handleGenerate);

    if (result) {
      renderBanners(result);
      renderResult(result);
    } else {
      document.getElementById('generate-result').innerHTML = emptyState({
        title: 'Nothing generated yet',
        sub: 'Click "Generate YAML" to produce config files from the current devices, bandwidth caps, subnets, and tags.',
      });
    }
  }

  async function handleGenerate() {
    const btn = document.getElementById('btn-generate');
    btn.disabled = true;
    btn.textContent = 'Generating\u2026';
    try {
      const result = await Api.generate();
      state.lastGenerateResult = result;
      renderBanners(result);
      renderResult(result);
      toast(`Generated ${Object.keys(result.files || {}).length} file(s) \u2014 ${result.snmpTotal || 0} SNMP, ${result.icmpTotal || 0} ICMP`, 'success', 7000);
      if (result.missingCredsDevices && result.missingCredsDevices.length > 0) {
        showMissingCredsModal(result.missingCredsDevices);
      }
      refreshCounts();
    } catch (e) {
      reportError(e, 'Generate failed');
    } finally {
      btn.disabled = false;
      btn.innerHTML = `${icon('generate', { size: 14 })} Generate YAML`;
    }
  }

  function renderBanners(result) {
    const el = document.getElementById('generate-banners');
    const parts = [];

    if (result.missingCredsDevices && result.missingCredsDevices.length > 0) {
      parts.push(`
        <div class="banner banner-warn">
          <span>${icon('warning', { size: 16 })}</span>
          <div class="banner-content">
            <b>${result.missingCredsDevices.length} device(s)</b> are missing SNMPv3 credentials and were still included.
            <button class="link" id="btn-view-missing-creds">View list</button>
          </div>
        </div>
      `);
    }
    if (result.missingRegionDevices && result.missingRegionDevices.length > 0) {
      parts.push(`
        <div class="banner banner-danger">
          <span>${icon('warning', { size: 16 })}</span>
          <div class="banner-content">
            <b>${result.missingRegionDevices.length} device(s)</b> have no Collector Region and were excluded from every output file.
            <button class="link" id="btn-view-missing-region">View list</button>
          </div>
        </div>
      `);
    }
    const lowPriorityBits = [];
    if (result.skippedDevices) lowPriorityBits.push(`${result.skippedDevices} device(s) skipped (no IP)`);
    if (result.orphanedBwIps && result.orphanedBwIps.length) lowPriorityBits.push(`${result.orphanedBwIps.length} bandwidth row(s) orphaned (no matching device)`);
    if (lowPriorityBits.length) parts.push(`<div class="stats-row">${lowPriorityBits.map(b => `<span>${escapeHtml(b)}</span>`).join('')}</div>`);

    el.innerHTML = parts.join('');
    const mc = document.getElementById('btn-view-missing-creds');
    if (mc) mc.addEventListener('click', () => showMissingCredsModal(result.missingCredsDevices));
    const mr = document.getElementById('btn-view-missing-region');
    if (mr) mr.addEventListener('click', () => showMissingRegionModal(result.missingRegionDevices));
  }

  function renderResult(result) {
    const el = document.getElementById('generate-result');
    const files = result.files || {};
    const filenames = Object.keys(files);
    if (filenames.length === 0) {
      el.innerHTML = emptyState({ title: 'No files were generated', sub: 'Check that devices have a Collector Region set.' });
      return;
    }
    const stats = result.groupStats || {};

    el.innerHTML = `
      <div class="panel">
        <div class="yaml-tabs" id="yaml-tabs">
          ${filenames.map((f, i) => `<div class="yaml-tab${i === 0 ? ' active' : ''}" data-file="${escapeHtml(f)}">${escapeHtml(f)}</div>`).join('')}
        </div>
        <div class="panel-body" style="padding-top:12px;">
          <div id="yaml-group-stats" class="stats-row"></div>
          <div class="flex justify-between items-center mb-12">
            <div></div>
            <div class="flex gap-8">
              <button class="btn btn-sm" id="btn-download-current">Download this file</button>
              <button class="btn btn-sm" id="btn-download-all">Download all</button>
            </div>
          </div>
          <div class="yaml-preview" id="yaml-preview-text"></div>
        </div>
      </div>
    `;

    let activeFile = filenames[0];
    function showFile(filename) {
      activeFile = filename;
      document.querySelectorAll('#yaml-tabs .yaml-tab').forEach(t => t.classList.toggle('active', t.dataset.file === filename));
      document.getElementById('yaml-preview-text').textContent = files[filename] || '';
      const groupKey = filename.replace(/\.ya?ml$/i, '');
      const gs = stats[groupKey];
      document.getElementById('yaml-group-stats').innerHTML = gs ? `
        <span><b>${gs.snmp_count || 0}</b> SNMP</span>
        <span><b>${gs.icmp_only_count || 0}</b> ICMP-only</span>
        <span><b>${gs.missing_creds_count || 0}</b> missing creds</span>
        <span><b>${gs.bw_devices || 0}</b> bandwidth devices</span>
        <span><b>${gs.bw_interfaces || 0}</b> bandwidth interfaces</span>
      ` : '';
    }
    document.querySelectorAll('#yaml-tabs .yaml-tab').forEach(tab => tab.addEventListener('click', () => showFile(tab.dataset.file)));
    document.getElementById('btn-download-current').addEventListener('click', () => downloadTextFile(activeFile, files[activeFile] || ''));
    document.getElementById('btn-download-all').addEventListener('click', () => {
      filenames.forEach((f, i) => setTimeout(() => downloadTextFile(f, files[f] || ''), i * 150));
    });
    showFile(activeFile);
  }

  function showMissingCredsModal(devices) {
    const overlay = openModal(`
      <div class="modal-header"><h3>${icon('warning', { size: 16 })} Missing SNMPv3 Credentials</h3><button class="modal-close" data-act="close">&times;</button></div>
      <div class="modal-body">
        <p class="text-dim mb-12">These devices were generated without complete SNMPv3 credentials. They were still included, but won't poll over SNMP until credentials are added.</p>
        <table>
          <thead><tr><th>IP</th><th>Device</th><th>Region</th></tr></thead>
          <tbody>${devices.map(d => `<tr><td class="mono">${escapeHtml(d.ip)}</td><td>${escapeHtml(d.device)}</td><td>${escapeHtml(d.region)}</td></tr>`).join('')}</tbody>
        </table>
      </div>
      <div class="modal-footer"><button class="btn btn-primary" data-act="close">Got it</button></div>
    `, { large: true });
    overlay.querySelectorAll('[data-act="close"]').forEach(b => b.addEventListener('click', () => closeModal(overlay)));
  }

  function showMissingRegionModal(devices) {
    const overlay = openModal(`
      <div class="modal-header"><h3>${icon('warning', { size: 16 })} Devices Missing Collector Region</h3><button class="modal-close" data-act="close">&times;</button></div>
      <div class="modal-body">
        <p class="text-dim mb-12">These devices have no Collector Region set, so they were excluded from every generated YAML file.</p>
        <table>
          <thead><tr><th>IP</th><th>Device</th></tr></thead>
          <tbody>${devices.map(d => `<tr><td class="mono">${escapeHtml(d.ip)}</td><td>${escapeHtml(d.device)}</td></tr>`).join('')}</tbody>
        </table>
      </div>
      <div class="modal-footer"><button class="btn btn-primary" data-act="close">Got it</button></div>
    `, { large: true });
    overlay.querySelectorAll('[data-act="close"]').forEach(b => b.addEventListener('click', () => closeModal(overlay)));
  }

  return { render };
})();
