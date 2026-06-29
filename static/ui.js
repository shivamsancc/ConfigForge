// ============================================================================
// UI primitives shared across views.
// ============================================================================

function getEditorName() {
  let name = localStorage.getItem('editorName');
  while (!name) {
    const entered = (window.prompt('Your name (required \u2014 used for audit-log attribution on changes you make):') || '').trim();
    if (entered) {
      name = entered;
      localStorage.setItem('editorName', name);
    }
    // If the person cancels or submits blank, the loop re-prompts rather
    // than silently falling back to "unknown" -- a name is required
    // before any write can proceed.
  }
  return name;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Toasts
// ---------------------------------------------------------------------------
function toast(message, type = 'info', timeoutMs = 5000) {
  const stack = document.getElementById('toast-stack');
  const el = document.createElement('div');
  el.className = 'toast' + (type !== 'info' ? ` toast-${type}` : '');
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => { el.remove(); }, timeoutMs);
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------
function openModal(innerHtml, { large = false } = {}) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `<div class="modal${large ? ' modal-lg' : ''}">${innerHtml}</div>`;
  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(overlay); });
  document.addEventListener('keydown', escHandler(overlay));
  document.body.appendChild(overlay);
  return overlay;
}

function escHandler(overlay) {
  function handler(e) {
    if (e.key === 'Escape') {
      closeModal(overlay);
      document.removeEventListener('keydown', handler);
    }
  }
  return handler;
}

function closeModal(overlay) {
  if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
}

// ---------------------------------------------------------------------------
// Confirm dialog
// ---------------------------------------------------------------------------
function confirmDialog(message, { danger = true, confirmLabel = 'Delete' } = {}) {
  return new Promise((resolve) => {
    const overlay = openModal(`
      <div class="modal-header">
        <h3>Please confirm</h3>
        <button class="modal-close" data-act="cancel">&times;</button>
      </div>
      <div class="modal-body">
        <p style="margin:0;color:var(--text);">${escapeHtml(message)}</p>
      </div>
      <div class="modal-footer">
        <button class="btn" data-act="cancel">Cancel</button>
        <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-act="confirm">${escapeHtml(confirmLabel)}</button>
      </div>
    `);
    overlay.querySelectorAll('[data-act="cancel"]').forEach(b => b.addEventListener('click', () => { closeModal(overlay); resolve(false); }));
    overlay.querySelector('[data-act="confirm"]').addEventListener('click', () => { closeModal(overlay); resolve(true); });
  });
}

// ---------------------------------------------------------------------------
// Dependency-aware delete confirmation.
// Checks usage first; if in use, warns with the count and requires a
// second, explicit confirmation before allowing the (forced) delete.
// Returns true if the caller should proceed with the delete.
// ---------------------------------------------------------------------------
async function confirmDependentDelete({ itemLabel, checkUsage, zeroUsageMessage }) {
  let count = 0;
  try {
    count = await checkUsage();
  } catch (e) {
    // If the usage check itself fails, fall back to a plain confirm
    // rather than silently skipping the warning entirely.
    return confirmDialog(`Delete ${itemLabel}? (Could not verify usage -- proceed with caution.)`);
  }

  if (count > 0) {
    const proceed = await confirmDialog(
      `${itemLabel} is currently used by ${count} record(s). Deleting it will not remove those records, but they will lose this value. Delete anyway?`,
      { confirmLabel: 'Delete anyway' }
    );
    return proceed;
  }
  return confirmDialog(zeroUsageMessage || `Delete ${itemLabel}? This cannot be undone.`);
}

// ---------------------------------------------------------------------------
// Error helper
// ---------------------------------------------------------------------------
function reportError(err, context) {
  console.error(context, err);
  toast(`${context}: ${err.message || err}`, 'danger', 7000);
}

// ---------------------------------------------------------------------------
// Download a text/binary blob as a file
// ---------------------------------------------------------------------------
function downloadTextFile(filename, text) {
  const blob = new Blob([text], { type: 'text/yaml' });
  triggerDownload(blob, filename);
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function downloadUrl(url, filename) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  triggerDownload(blob, filename);
}

// ---------------------------------------------------------------------------
// Network-motif SVG: small node-graph mark used as the brand icon and in
// empty states. Kept as a function so size/opacity can vary by context.
// ---------------------------------------------------------------------------
function networkMotifSvg({ size = 26, animated = false } = {}) {
  const pulse = animated ? `
    <style>
      .nm-pulse { animation: nm-pulse 2.4s ease-in-out infinite; }
      @keyframes nm-pulse { 0%,100% { opacity: 0.5; } 50% { opacity: 1; } }
    </style>` : '';
  return `
  <svg width="${size}" height="${size}" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    ${pulse}
    <defs>
      <linearGradient id="nm-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="#9DBFE8"/>
        <stop offset="1" stop-color="#A88FD6"/>
      </linearGradient>
    </defs>
    <line x1="7" y1="8" x2="16" y2="16" stroke="url(#nm-grad)" stroke-width="1.4" opacity="0.7"/>
    <line x1="25" y1="9" x2="16" y2="16" stroke="url(#nm-grad)" stroke-width="1.4" opacity="0.7"/>
    <line x1="9" y1="24" x2="16" y2="16" stroke="url(#nm-grad)" stroke-width="1.4" opacity="0.7"/>
    <line x1="23" y1="23" x2="16" y2="16" stroke="url(#nm-grad)" stroke-width="1.4" opacity="0.7"/>
    <circle cx="16" cy="16" r="4" fill="url(#nm-grad)" class="${animated ? 'nm-pulse' : ''}"/>
    <circle cx="7" cy="8" r="2.4" fill="#7AA2D6"/>
    <circle cx="25" cy="9" r="2.4" fill="#7AA2D6"/>
    <circle cx="9" cy="24" r="2.4" fill="#A88FD6"/>
    <circle cx="23" cy="23" r="2.4" fill="#A88FD6"/>
  </svg>`;
}

function emptyState({ title, sub, icon } = {}) {
  return `
    <div class="empty-state">
      ${icon || networkMotifSvg({ size: 48 })}
      <div class="empty-state-title">${escapeHtml(title || 'Nothing here yet')}</div>
      ${sub ? `<div class="empty-state-sub">${escapeHtml(sub)}</div>` : ''}
    </div>
  `;
}

// ---------------------------------------------------------------------------
// IP address validation -- mirrors logic.py's is_valid_ip so the frontend
// catches obviously-malformed input before it ever reaches the server.
// Not a full RFC validator (full validation happens server-side via
// Python's ipaddress module) -- this just catches the common mistakes:
// wrong octet count, octets out of 0-255 range, non-numeric junk.
// ---------------------------------------------------------------------------
function isValidIp(value) {
  if (!value) return false;
  const v = value.trim();

  const ipv4Match = v.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (ipv4Match) {
    return ipv4Match.slice(1, 5).every(octet => {
      const n = Number(octet);
      return n >= 0 && n <= 255;
    });
  }

  // Lightweight IPv6 sanity check.
  if (v.includes(':') && /^[0-9a-fA-F:]+$/.test(v)) {
    const segments = v.split(':');
    return segments.length >= 3 && segments.length <= 8;
  }

  return false;
}

// ---------------------------------------------------------------------------
// Client-side search filtering -- runs entirely in the browser (no server
// round-trip) so it's instant. Matches if the query is a case-insensitive
// substring of any value in the row, across every visible field.
// ---------------------------------------------------------------------------
function rowMatchesSearch(row, query) {
  if (!query) return true;
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = JSON.stringify(row).toLowerCase();
  return haystack.includes(q);
}

function renderSearchBox(id, placeholder) {
  return `<input type="text" id="${id}" class="search-box" placeholder="${escapeHtml(placeholder || 'Search\u2026')}" autocomplete="off">`;
}

// ---------------------------------------------------------------------------
// Bandwidth string -> bits/sec, mirroring logic.py's _parse_bw_to_bps, so
// sorting the Allocated BW column compares actual magnitude ("500 Mbps" <
// "1 Gbps") instead of lexicographic string order.
// ---------------------------------------------------------------------------
function parseBwToBps(value) {
  if (!value) return null;
  const m = String(value).trim().match(/^([\d.]+)\s*([a-zA-Z]+)$/);
  if (!m) return null;
  const num = parseFloat(m[1]);
  const unit = m[2].toLowerCase();
  const multipliers = { bps: 1, kbps: 1e3, mbps: 1e6, gbps: 1e9, kb: 1e3, mb: 1e6, gb: 1e9 };
  const mult = multipliers[unit];
  return mult === undefined ? null : num * mult;
}

// ---------------------------------------------------------------------------
// Icon library -- small inline stroke-style SVGs (24x24 viewBox, currentColor
// stroke) so every icon inherits whatever text color it's placed in and
// needs no external icon font or image requests. Sized via CSS on .icon-svg.
// ---------------------------------------------------------------------------
const ICONS = {
  dashboard: '<path d="M3 13h8V3H3zM13 21h8V11h-8zM13 3v6h8V3zM3 21h8v-6H3z"/>',
  bandwidth: '<rect x="2.5" y="9" width="6" height="6" rx="1"/><rect x="15.5" y="9" width="6" height="6" rx="1"/><line x1="8.5" y1="12" x2="15.5" y2="12"/>',
  router: '<rect x="2" y="9" width="20" height="7" rx="1.5"/><path d="M6 9V7a2 2 0 0 1 2-2M12 16v3M8 19h8"/><circle cx="7" cy="12.5" r=".6" fill="currentColor" stroke="none"/><circle cx="10" cy="12.5" r=".6" fill="currentColor" stroke="none"/>',
  subnet: '<circle cx="12" cy="5" r="2.4"/><circle cx="5" cy="19" r="2.4"/><circle cx="19" cy="19" r="2.4"/><path d="M12 7.4V12M12 12L6.6 17M12 12l5.4 5"/>',
  tag: '<path d="M20.6 11.6 12.4 3.4A2 2 0 0 0 11 3H4a1 1 0 0 0-1 1v7a2 2 0 0 0 .6 1.4l8.2 8.2a2 2 0 0 0 2.8 0l6-6a2 2 0 0 0 0-2.8Z"/><circle cx="7.5" cy="7.5" r="1.3" fill="currentColor" stroke="none"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  generate: '<path d="M5 3l14 9-14 9V3z"/>',
  history: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
  audit: '<path d="M9 2h6l5 5v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h3z"/><path d="M9 2v5H4M9 13h6M9 17h6"/>',
  import: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 19h16"/>',
  export: '<path d="M12 15V3M7 8l5-5 5 5"/><path d="M4 19h16"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  table: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 3v18"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  sun: '<circle cx="12" cy="12" r="4.5"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  moon: '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z"/>',
  warning: '<path d="M12 9v4M12 17h.01"/><path d="m10.3 3.9-8 14A1.5 1.5 0 0 0 3.6 20h16.8a1.5 1.5 0 0 0 1.3-2.3l-8-14a1.5 1.5 0 0 0-2.6 0Z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5h1"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  reset: '<path d="M3 12a9 9 0 1 0 2.6-6.4L3 8"/><path d="M3 4v4h4"/>',
  trash: '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0-1 14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1L5 6"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
};

function icon(name, { size = 16, className = '' } = {}) {
  const body = ICONS[name];
  if (!body) return '';
  return `<svg class="icon-svg ${className}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
}

// ---------------------------------------------------------------------------
// Import validation utilities
// ---------------------------------------------------------------------------

/**
 * Append finding banners (banner-danger for errors, banner-warn for warnings)
 * to a container element.  Optionally filters out codes in `skipCodes`.
 *
 * @param {HTMLElement} container  - DOM element to append banners into.
 * @param {Array}       findings   - Finding objects from the validation engine.
 * @param {Set}         [skipCodes] - Optional set of code strings to suppress.
 */
function renderFindingsBanners(container, findings, skipCodes = new Set()) {
  findings
    .filter(f => !skipCodes.has(f.code))
    .forEach(f => {
      const cls = f.severity === 'error' ? 'banner-danger' : 'banner-warn';
      const div = document.createElement('div');
      div.className = `banner ${cls}`;
      div.innerHTML = `
        <span>${icon('warning', { size: 16 })}</span>
        <div class="banner-content">${escapeHtml(f.message)}</div>
      `;
      container.appendChild(div);
    });
}

/**
 * Show a modal summarising import validation findings, then call onProceed()
 * if the user confirms.
 *
 * Behaviour:
 *  - No findings            → modal is skipped entirely; onProceed() called immediately.
 *  - Warnings only          → yellow header; "Proceed" button available.
 *  - Any errors present     → red header; "Proceed anyway" button available (errors
 *                             require explicit acknowledgement but do not hard-block).
 *
 * @param {Array}    findings   - Finding objects (may be empty).
 * @param {string}   scopeLabel - Short label for the modal title, e.g. "Devices".
 * @param {Function} onProceed  - Async-safe callback invoked if the user confirms.
 */
function showImportValidationModal(findings, scopeLabel, onProceed) {
  if (!findings || findings.length === 0) {
    onProceed();
    return;
  }

  const hasErrors   = findings.some(f => f.severity === 'error');
  const errorCount  = findings.filter(f => f.severity === 'error').length;
  const warnCount   = findings.filter(f => f.severity === 'warning').length;

  const headerClass = hasErrors ? 'banner-danger' : 'banner-warn';
  const proceedLabel = hasErrors ? 'Proceed anyway' : 'Proceed';

  const summaryParts = [];
  if (errorCount) summaryParts.push(`${errorCount} error${errorCount !== 1 ? 's' : ''}`);
  if (warnCount)  summaryParts.push(`${warnCount} warning${warnCount !== 1 ? 's' : ''}`);

  const rows = findings.map(f => {
    const badgeCls = f.severity === 'error' ? 'badge-danger' : 'badge-warn';
    return `
      <tr>
        <td><span class="badge ${badgeCls}">${escapeHtml(f.severity)}</span></td>
        <td class="mono" style="font-size:0.78rem;">${escapeHtml(f.code)}</td>
        <td>${escapeHtml(f.message)}</td>
      </tr>`;
  }).join('');

  const overlay = openModal(`
    <div class="modal-header">
      <h3>${icon('warning', { size: 16 })} ${escapeHtml(scopeLabel)} Import — ${summaryParts.join(', ')}</h3>
      <button class="modal-close" data-act="cancel">&times;</button>
    </div>
    <div class="modal-body">
      <p class="text-dim mb-12">
        ${hasErrors
          ? 'The following issues were found. You may still proceed, but errors may cause records to be skipped during generation.'
          : 'The following warnings were found. Review them before proceeding.'}
      </p>
      <table>
        <thead>
          <tr><th style="width:80px;">Severity</th><th style="width:190px;">Code</th><th>Message</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="modal-footer">
      <button class="btn" data-act="cancel">Cancel</button>
      <button class="btn ${hasErrors ? 'btn-danger' : 'btn-primary'}" data-act="proceed">${escapeHtml(proceedLabel)}</button>
    </div>
  `, { large: true });

  overlay.querySelectorAll('[data-act="cancel"]').forEach(b =>
    b.addEventListener('click', () => closeModal(overlay))
  );
  overlay.querySelector('[data-act="proceed"]').addEventListener('click', () => {
    closeModal(overlay);
    onProceed();
  });
}

/**
 * Show a combined Import Preview modal containing:
 *   1. Validation findings (if any) — same banners as renderFindingsBanners.
 *   2. Change summary — counts of new / modified / unchanged / removed records.
 *   3. Modified detail — expandable per-record list with field-level diffs.
 *
 * If there are no findings AND no changes (nothing new, modified, or removed)
 * the modal still appears so the operator can see the "all unchanged" state
 * before committing.
 *
 * @param {Array}    findings   - Validation findings from the server.
 * @param {Object}   diff       - Diff object: {new, modified, unchanged, removed}.
 * @param {Object}   tagDefs    - Tag definitions array (state.tagDefs) for name lookup.
 * @param {string}   scopeLabel - Human label, e.g. "Devices".
 * @param {Function} onProceed  - Called when user confirms.
 */
function showImportPreviewModal(findings, diff, tagDefs, scopeLabel, onProceed) {
  findings = findings || [];
  diff = diff || { new: [], modified: [], unchanged: 0, removed: [] };
  tagDefs = tagDefs || [];

  const hasErrors  = findings.some(f => f.severity === 'error');
  const hasWarnings = findings.some(f => f.severity === 'warning');

  // ── Findings section ────────────────────────────────────────────────────
  const findingsHtml = findings.length === 0 ? '' : `
    <div style="margin-bottom:16px;">
      <div style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text-dim);margin-bottom:8px;">Validation</div>
      ${findings.map(f => {
        const cls = f.severity === 'error' ? 'banner-danger' : 'banner-warn';
        return `<div class="banner ${cls}" style="margin-bottom:4px;">
          <span>${icon('warning', { size: 14 })}</span>
          <div class="banner-content" style="font-size:0.82rem;">${escapeHtml(f.message)}</div>
        </div>`;
      }).join('')}
    </div>`;

  // ── Summary badges ───────────────────────────────────────────────────────
  const { new: newItems, modified, unchanged, removed } = diff;
  const newCount  = newItems.length;
  const modCount  = modified.length;
  const remCount  = removed.length;

  const summaryCells = [
    newCount  > 0 ? `<span style="color:var(--green,#4caf50);font-weight:600;">+${newCount} new</span>` : '',
    modCount  > 0 ? `<span style="color:var(--blue,#5b9bd5);font-weight:600;">~${modCount} modified</span>` : '',
    `<span style="color:var(--text-dim);">=${unchanged} unchanged</span>`,
    remCount  > 0 ? `<span style="color:var(--red,#e05252);font-weight:600;">&#x2212;${remCount} removed</span>` : '',
  ].filter(Boolean).join('<span style="color:var(--text-dim);padding:0 6px;">·</span>');

  const summaryHtml = `
    <div style="display:flex;align-items:center;gap:0;flex-wrap:wrap;padding:10px 0 14px 0;border-bottom:1px solid var(--border-soft);margin-bottom:14px;font-size:0.9rem;">
      ${summaryCells}
    </div>`;

  // ── Modified detail list ─────────────────────────────────────────────────
  const modifiedHtml = modified.length === 0 ? '' : (() => {
    const items = modified.map((item, idx) => {
      const changeRows = item.changes.map(ch => {
        if (ch.credential) {
          return `<div style="display:flex;gap:8px;align-items:baseline;padding:2px 0 2px 16px;font-size:0.82rem;">
            <span style="color:var(--text-dim);min-width:140px;flex-shrink:0;">${escapeHtml(ch.field)}</span>
            <span style="color:var(--text-dim);font-style:italic;">credential updated</span>
          </div>`;
        }
        const oldDisplay = ch.old === '' ? '<em style="color:var(--text-dim);">(empty)</em>' : `<span>${escapeHtml(ch.old)}</span>`;
        const newDisplay = ch.new === '' ? '<em style="color:var(--text-dim);">(empty)</em>' : `<span style="color:var(--green,#4caf50);">${escapeHtml(ch.new)}</span>`;
        return `<div style="display:flex;gap:8px;align-items:baseline;padding:2px 0 2px 16px;font-size:0.82rem;">
          <span style="color:var(--text-dim);min-width:140px;flex-shrink:0;">${escapeHtml(ch.field)}</span>
          <span style="text-decoration:line-through;color:var(--text-dim);">${oldDisplay instanceof Object ? '' : escapeHtml(ch.old) || '<em>(empty)</em>'}</span>
          <span style="color:var(--text-dim);">→</span>
          <span style="color:var(--green,#4caf50);">${escapeHtml(ch.new) || '<em style="color:var(--text-dim);">(empty)</em>'}</span>
        </div>`;
      }).join('');

      return `<div style="border-bottom:1px solid var(--border-soft);">
        <button class="diff-toggle-btn" data-idx="${idx}" style="width:100%;text-align:left;padding:7px 4px;background:none;border:none;cursor:pointer;color:var(--text);font-size:0.85rem;display:flex;gap:6px;align-items:center;">
          <span class="diff-arrow" style="color:var(--text-dim);font-size:0.7rem;transition:transform .15s;">▶</span>
          <span>${escapeHtml(item.label)}</span>
          <span style="margin-left:auto;color:var(--text-dim);font-size:0.78rem;">${item.changes.length} field${item.changes.length !== 1 ? 's' : ''} changed</span>
        </button>
        <div class="diff-detail-panel" data-idx="${idx}" style="display:none;padding-bottom:6px;">${changeRows}</div>
      </div>`;
    }).join('');

    return `
      <div style="margin-bottom:12px;">
        <div style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text-dim);margin-bottom:6px;">Modified (${modified.length})</div>
        <div id="diff-modified-list" style="border:1px solid var(--border-soft);border-radius:6px;overflow:hidden;max-height:280px;overflow-y:auto;">
          ${items}
        </div>
      </div>`;
  })();

  // ── Removed list (replace mode) ──────────────────────────────────────────
  const removedHtml = removed.length === 0 ? '' : (() => {
    const MAX_SHOWN = 8;
    const shown = removed.slice(0, MAX_SHOWN);
    const extra = removed.length - MAX_SHOWN;
    const labels = shown.map(r => `<li style="font-size:0.83rem;padding:1px 0;">${escapeHtml(r.label)}</li>`).join('');
    const more = extra > 0 ? `<li style="font-size:0.83rem;color:var(--text-dim);">…and ${extra} more</li>` : '';
    return `
      <div style="margin-bottom:12px;">
        <div style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--red,#e05252);margin-bottom:6px;">Removed (${removed.length}) — replace mode</div>
        <ul style="margin:0;padding-left:18px;list-style:disc;">${labels}${more}</ul>
      </div>`;
  })();

  // ── Footer button label ──────────────────────────────────────────────────
  const proceedLabel = hasErrors ? 'Proceed anyway' : 'Proceed with Import';
  const proceedClass = hasErrors ? 'btn-danger' : 'btn-primary';

  const overlay = openModal(`
    <div class="modal-header">
      <h3>${icon('import', { size: 16 })} Import Preview — ${escapeHtml(scopeLabel)}</h3>
      <button class="modal-close" data-act="cancel">&times;</button>
    </div>
    <div class="modal-body">
      ${findingsHtml}
      ${summaryHtml}
      ${modifiedHtml}
      ${removedHtml}
      ${newCount === 0 && modCount === 0 && remCount === 0
        ? `<p class="text-dim" style="margin:0;">All ${unchanged} record(s) are identical to what is already in the database. No changes will be made.</p>`
        : ''}
    </div>
    <div class="modal-footer">
      <button class="btn" data-act="cancel">Cancel</button>
      <button class="btn ${proceedClass}" data-act="proceed">${escapeHtml(proceedLabel)}</button>
    </div>
  `, { large: true });

  // Expand/collapse modified items.
  overlay.querySelectorAll('.diff-toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = btn.dataset.idx;
      const panel = overlay.querySelector(`.diff-detail-panel[data-idx="${idx}"]`);
      const arrow = btn.querySelector('.diff-arrow');
      const open = panel.style.display === 'none';
      panel.style.display = open ? 'block' : 'none';
      arrow.style.transform = open ? 'rotate(90deg)' : '';
    });
  });

  overlay.querySelectorAll('[data-act="cancel"]').forEach(b =>
    b.addEventListener('click', () => closeModal(overlay))
  );
  overlay.querySelector('[data-act="proceed"]').addEventListener('click', () => {
    closeModal(overlay);
    onProceed();
  });
}