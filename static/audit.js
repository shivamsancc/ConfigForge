// ============================================================================
// AUDIT LOG VIEW
// ============================================================================

const Audit = (() => {
  let searchQuery = '';
  let cachedEntries = [];

  async function render() {
    const content = document.getElementById('content');
    content.innerHTML = `<div class="loading-row"><div class="spinner"></div> Loading audit log&hellip;</div>`;
    try {
      const res = await Api.getAudit(200);
      cachedEntries = res.entries || [];
    } catch (e) {
      reportError(e, 'Failed to load audit log');
      content.innerHTML = emptyState({ title: 'Could not load audit log' });
      return;
    }
    if (cachedEntries.length === 0) {
      content.innerHTML = emptyState({ title: 'No audit entries yet' });
      return;
    }
    content.innerHTML = `
      <div class="flex justify-between items-center mb-16">
        ${renderSearchBox('audit-search', 'Search audit log\u2026')}
        <div class="text-dim" id="audit-count-label"></div>
      </div>
      <div id="audit-body"></div>
    `;
    const searchBox = document.getElementById('audit-search');
    searchBox.value = searchQuery;
    searchBox.addEventListener('input', (e) => { searchQuery = e.target.value; renderBody(); });
    renderBody();
  }

  function renderBody() {
    const body = document.getElementById('audit-body');
    const entries = searchQuery ? cachedEntries.filter(e => rowMatchesSearch(e, searchQuery)) : cachedEntries;
    document.getElementById('audit-count-label').textContent =
      searchQuery ? `${entries.length} of ${cachedEntries.length} entries` : `${cachedEntries.length} entries`;

    if (entries.length === 0) {
      body.innerHTML = emptyState({ title: 'No entries match your search', sub: `No results for "${searchQuery}".` });
      return;
    }
    body.innerHTML = `
      <div class="panel"><div class="table-wrap">
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
      </div></div>
    `;
  }

  function formatDetails(details) {
    if (details === null || details === undefined) return '';
    if (typeof details === 'string') return details;
    try { return JSON.stringify(details, null, 2); } catch (e) { return String(details); }
  }

  return { render };
})();
