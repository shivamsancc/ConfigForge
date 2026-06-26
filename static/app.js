// ============================================================================
// APP SHELL — state, routing, topbar.
// Individual views (devices.js, bandwidth.js, lists.js, generate.js,
// history.js, audit.js) each expose a render function that this shell calls.
// ============================================================================

const state = {
  devices: [],
  bandwidth: [],
  lists: { collectorRegions: [], deviceClasses: [], deviceCategories: [], deviceTypes: [] },
  meta: { deviceCount: 0, bandwidthCount: 0, lastSavedAt: null, lastSavedBy: null },
  currentView: 'devices',
  lastGenerateResult: null, // kept in memory so switching views doesn't lose the preview
};

const VIEWS = [
  { group: 'Data', items: [
    { id: 'devices', label: 'Devices', icon: '▢' },
    { id: 'bandwidth', label: 'Bandwidth Capping', icon: '↕' },
    { id: 'lists', label: 'Manage Lists', icon: '☰' },
  ] },
  { group: 'Output', items: [
    { id: 'generate', label: 'Generate YAML', icon: '▶' },
    { id: 'history', label: 'YAML History', icon: '🕘' },
    { id: 'audit', label: 'Audit Log', icon: '🗒' },
  ] },
];

const VIEW_RENDERERS = {
  devices: () => Devices.render(),
  bandwidth: () => Bandwidth.render(),
  lists: () => Lists.render(),
  generate: () => Generate.render(),
  history: () => History.render(),
  audit: () => Audit.render(),
};

const VIEW_TITLES = {
  devices: 'Devices',
  bandwidth: 'Bandwidth Capping',
  lists: 'Manage Lists',
  generate: 'Generate YAML',
  history: 'YAML History',
  audit: 'Audit Log',
};

function renderSidebar() {
  const nav = document.getElementById('sidebar-nav');
  nav.innerHTML = VIEWS.map(group => `
    <div class="nav-group-label">${escapeHtml(group.group)}</div>
    ${group.items.map(item => `
      <div class="nav-item${state.currentView === item.id ? ' active' : ''}" data-view="${item.id}">
        <span class="icon">${item.icon}</span>
        <span>${escapeHtml(item.label)}</span>
      </div>
    `).join('')}
  `).join('');

  nav.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', () => navigateTo(el.dataset.view));
  });
}

function renderTopbar() {
  document.getElementById('topbar-title').textContent = VIEW_TITLES[state.currentView] || '';
  document.getElementById('topbar-stats').innerHTML = `
    <span><b>${state.devices.length}</b> devices</span>
    <span><b>${state.bandwidth.length}</b> bandwidth rows</span>
    ${state.meta.lastSavedAt ? `<span class="text-faint">last generated ${escapeHtml(state.meta.lastSavedAt)}${state.meta.lastSavedBy ? ' by ' + escapeHtml(state.meta.lastSavedBy) : ''}</span>` : ''}
  `;
}

function navigateTo(viewId) {
  if (!VIEW_RENDERERS[viewId]) return;
  state.currentView = viewId;
  renderSidebar();
  renderTopbar();
  const content = document.getElementById('content');
  content.innerHTML = '<div class="loading-row"><div class="spinner"></div> Loading…</div>';
  Promise.resolve(VIEW_RENDERERS[viewId]()).catch(err => reportError(err, 'Failed to load view'));
}

async function refreshCounts() {
  try {
    const meta = await Api.getMeta();
    state.meta = meta;
  } catch (e) {
    // Non-fatal — topbar just won't show last-saved info.
  }
  renderTopbar();
}

async function boot() {
  renderSidebar();
  renderTopbar();
  try {
    const [devicesRes, bwRes, listsRes] = await Promise.all([
      Api.getDevices(), Api.getBandwidth(), Api.getLists(),
    ]);
    state.devices = devicesRes.devices || [];
    state.bandwidth = bwRes.bandwidth || bwRes.devices || [];
    state.lists = Object.assign({ collectorRegions: [], deviceClasses: [], deviceCategories: [], deviceTypes: [] }, listsRes.lists || listsRes || {});
  } catch (e) {
    reportError(e, 'Failed to load initial data');
  }
  refreshCounts();
  navigateTo(state.currentView);
}

document.addEventListener('DOMContentLoaded', boot);
