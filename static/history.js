// ============================================================================
// YAML HISTORY VIEW
// ============================================================================

const History = (() => {
  async function render() {
    const content = document.getElementById('content');
    content.innerHTML = `<div class="loading-row"><div class="spinner"></div> Loading history…</div>`;
    let entries = [];
    try {
      const res = await Api.getHistory(100);
      entries = res.entries || [];
    } catch (e) {
      reportError(e, 'Failed to load history');
      content.innerHTML = `<div class="empty-state">Could not load history.</div>`;
      return;
    }

    if (entries.length === 0) {
      content.innerHTML = `<div class="empty-state">No generations yet. Run "Generate YAML" to create the first entry.</div>`;
      return;
    }

    content.innerHTML = `
      <div class="panel">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Timestamp</th><th>Actor</th><th>Summary</th><th></th></tr></thead>
            <tbody>
              ${entries.map(e => `
                <tr data-id="${escapeHtml(e.id)}">
                  <td class="mono">${escapeHtml(e.ts)}</td>
                  <td>${escapeHtml(e.actor || 'unknown')}</td>
                  <td>${escapeHtml(e.summary || '')}</td>
                  <td><button class="btn btn-sm" data-act="view">View</button></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;

    document.querySelectorAll('#content tbody tr').forEach(tr => {
      tr.querySelector('[data-act="view"]').addEventListener('click', () => openEntry(tr.dataset.id));
    });
  }

  async function openEntry(id) {
    let entry;
    try {
      entry = await Api.getHistoryEntry(id);
    } catch (e) {
      reportError(e, 'Failed to load history entry');
      return;
    }

    const files = entry.files || {};
    const filenames = Object.keys(files);

    const overlay = openModal(`
      <div class="modal-header">
        <h3>History — ${escapeHtml(entry.ts)} by ${escapeHtml(entry.actor || 'unknown')}</h3>
        <button class="modal-close" data-act="close">&times;</button>
      </div>
      <div class="modal-body">
        <p class="text-dim mb-12">${escapeHtml(entry.summary || '')}</p>
        ${filenames.length ? `
          <div class="yaml-tabs" id="hist-yaml-tabs">
            ${filenames.map((f, i) => `<div class="yaml-tab${i === 0 ? ' active' : ''}" data-file="${escapeHtml(f)}">${escapeHtml(f)}</div>`).join('')}
          </div>
          <div class="flex justify-between items-center" style="margin:10px 0;">
            <div></div>
            <button class="btn btn-sm" id="btn-download-hist-file">Download this file</button>
          </div>
          <div class="yaml-preview" id="hist-yaml-preview"></div>
        ` : `<div class="empty-state">No files in this snapshot.</div>`}
      </div>
      <div class="modal-footer">
        <button class="btn" data-act="close">Close</button>
      </div>
    `, { large: true });

    overlay.querySelectorAll('[data-act="close"]').forEach(b => b.addEventListener('click', () => closeModal(overlay)));

    if (filenames.length) {
      let activeFile = filenames[0];
      function showFile(f) {
        activeFile = f;
        overlay.querySelectorAll('#hist-yaml-tabs .yaml-tab').forEach(t => t.classList.toggle('active', t.dataset.file === f));
        overlay.querySelector('#hist-yaml-preview').textContent = files[f] || '';
      }
      overlay.querySelectorAll('#hist-yaml-tabs .yaml-tab').forEach(tab => {
        tab.addEventListener('click', () => showFile(tab.dataset.file));
      });
      overlay.querySelector('#btn-download-hist-file').addEventListener('click', () => {
        downloadTextFile(activeFile, files[activeFile] || '');
      });
      showFile(activeFile);
    }
  }

  return { render };
})();
