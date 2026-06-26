// ============================================================================
// UI primitives shared across views.
// ============================================================================

function getEditorName() {
  let name = sessionStorage.getItem('editorName');
  if (!name) {
    name = (window.prompt('Your name (used for audit-log attribution on changes you make):') || '').trim();
    if (!name) name = 'unknown';
    sessionStorage.setItem('editorName', name);
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
