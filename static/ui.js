// ============================================================================
// UI primitives shared across views: toasts, modals, confirm dialogs,
// the once-per-session editor name prompt used for audit attribution.
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
// Renders a modal overlay with the given inner HTML. Returns the overlay
// element so callers can wire up their own event handlers and call
// closeModal(overlay) when done.
function openModal(innerHtml, { large = false } = {}) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `<div class="modal${large ? ' modal-lg' : ''}">${innerHtml}</div>`;
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeModal(overlay);
  });
  document.body.appendChild(overlay);
  return overlay;
}

function closeModal(overlay) {
  if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
}

// ---------------------------------------------------------------------------
// Confirm dialog (returns a Promise<boolean>)
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
    overlay.querySelectorAll('[data-act="cancel"]').forEach(b => b.addEventListener('click', () => {
      closeModal(overlay); resolve(false);
    }));
    overlay.querySelector('[data-act="confirm"]').addEventListener('click', () => {
      closeModal(overlay); resolve(true);
    });
  });
}

// ---------------------------------------------------------------------------
// Error helper — surfaces API errors as a toast consistently
// ---------------------------------------------------------------------------
function reportError(err, context) {
  console.error(context, err);
  toast(`${context}: ${err.message || err}`, 'danger', 7000);
}

// ---------------------------------------------------------------------------
// Download a text blob as a file
// ---------------------------------------------------------------------------
function downloadTextFile(filename, text) {
  const blob = new Blob([text], { type: 'text/yaml' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
