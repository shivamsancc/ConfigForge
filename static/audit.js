// ============================================================================
// AUDIT LOG VIEW
// ============================================================================

const Audit = (() => {
  async function render() {
    const content = document.getElementById('content');
    content.innerHTML = `<div class="loading-row"><div class="spinner"></div> Loading audit log…</div>`;
    let entries = [];
    try {
      const res = await Api.getAudit(200);
      entries = res.entries || [];
    } catch (e) {
      reportError(e, 'Failed to load audit log');
      content.innerHTML = `<div class="empty-state">Could not load audit log.</div>`;
      return;
    }

    if (entries.length === 0) {
      content.innerHTML = `<div class="empty-state">No audit entries yet.</div>`;
      return;
    }

    content.innerHTML = `
      <div class="panel">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th><th>Details</th></tr></thead>
            <tbody>
              ${entries.map(e => `
                <tr>
                  <td class="mono">${escapeHtml(e.ts)}</td>
                  <td>${escapeHtml(e.actor || 'unknown')}</td>
                  <td><span class="badge badge-neutral">${escapeHtml(e.action)}</span></td>
                  <td class="mono text-dim" style="white-space:pre-wrap;max-width:480px;">${escapeHtml(formatDetails(e.details))}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  function formatDetails(details) {
    if (details === null || details === undefined) return '';
    if (typeof details === 'string') return details;
    try {
      return JSON.stringify(details, null, 2);
    } catch (e) {
      return String(details);
    }
  }

  return { render };
})();
