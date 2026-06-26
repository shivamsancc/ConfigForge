// ============================================================================
// APP SHELL
// ============================================================================

const state = {
  devices: [],
  bandwidth: [],
  subnets: [],
  lists: { collectorRegions: [], deviceClasses: [], deviceCategories: [], deviceTypes: [] },
  tagDefs: [],
  meta: { deviceCount: 0, bandwidthCount: 0, subnetCount: 0, lastSavedAt: null, lastSavedBy: null },
  currentView: 'dashboard',
  lastGenerateResult: null,
  viewMode: { devices: 'table', bandwidth: 'table', subnets: 'table' }, // 'table' | 'card'
};

const VIEWS = [
  { group: 'Overview', items: [
    { id: 'dashboard', label: 'Dashboard', icon: '&#9670;' },
  ] },
  { group: 'Inventory', items: [
    { id: 'devices', label: 'Devices', icon: '&#9634;', countKey: 'deviceCount' },
    { id: 'bandwidth', label: 'Bandwidth Capping', icon: '&#8645;', countKey: 'bandwidthCount' },
    { id: 'subnets', label: 'Subnets', icon: '&#9737;', countKey: 'subnetCount' },
  ] },
  { group: 'Configuration', items: [
    { id: 'tags', label: 'Manage Tags', icon: '&#9873;' },
    { id: 'lists', label: 'Manage Lists', icon: '&#9776;' },
  ] },
  { group: 'Output', items: [
    { id: 'generate', label: 'Generate YAML', icon: '&#9656;' },
    { id: 'history', label: 'YAML History', icon: '&#128340;' },
    { id: 'audit', label: 'Audit Log', icon: '&#128221;' },
  ] },
];

const VIEW_RENDERERS = {
  dashboard: () => Dashboard.render(),
  devices: () => Devices.render(),
  bandwidth: () => Bandwidth.render(),
  subnets: () => Subnets.render(),
  tags: () => Tags.render(),
  lists: () => Lists.render(),
  generate: () => Generate.render(),
  history: () => History.render(),
  audit: () => Audit.render(),
};

const VIEW_TITLES = {
  dashboard: 'Dashboard',
  devices: 'Devices',
  bandwidth: 'Bandwidth Capping',
  subnets: 'Subnets',
  tags: 'Manage Tags',
  lists: 'Manage Lists',
  generate: 'Generate YAML',
  history: 'YAML History',
  audit: 'Audit Log',
};

function renderBrand() {
  document.getElementById('brand-mark').innerHTML = networkMotifSvg({ size: 26 });
}

function renderSidebar() {
  const nav = document.getElementById('sidebar-nav');
  nav.innerHTML = VIEWS.map(group => `
    <div class="nav-group-label">${escapeHtml(group.group)}</div>
    ${group.items.map(item => `
      <div class="nav-item${state.currentView === item.id ? ' active' : ''}" data-view="${item.id}">
        <span class="icon">${item.icon}</span>
        <span>${escapeHtml(item.label)}</span>
        ${item.countKey ? `<span class="count">${state.meta[item.countKey] ?? 0}</span>` : ''}
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
    <span><b>${state.subnets.length}</b> subnets</span>
    ${state.meta.lastSavedAt ? `<span class="text-faint">last generated ${escapeHtml(state.meta.lastSavedAt)}${state.meta.lastSavedBy ? ' by ' + escapeHtml(state.meta.lastSavedBy) : ''}</span>` : ''}
  `;
}

function navigateTo(viewId) {
  if (!VIEW_RENDERERS[viewId]) return;
  state.currentView = viewId;
  renderSidebar();
  renderTopbar();
  const content = document.getElementById('content');
  content.innerHTML = '<div class="loading-row"><div class="spinner"></div> Loading&hellip;</div>';
  Promise.resolve(VIEW_RENDERERS[viewId]()).catch(err => reportError(err, 'Failed to load view'));
}

async function refreshCounts() {
  try {
    state.meta = await Api.getMeta();
  } catch (e) { /* topbar just won't show last-saved info */ }
  renderSidebar();
  renderTopbar();
}

async function reloadAllData() {
  const [devicesRes, bwRes, subnetsRes, listsRes, tagsRes] = await Promise.all([
    Api.getDevices(), Api.getBandwidth(), Api.getSubnets(), Api.getLists(), Api.getTags(),
  ]);
  state.devices = devicesRes.devices || [];
  state.bandwidth = bwRes.rows || [];
  state.subnets = subnetsRes.subnets || [];
  state.lists = Object.assign({ collectorRegions: [], deviceClasses: [], deviceCategories: [], deviceTypes: [] }, listsRes.lists || {});
  state.tagDefs = tagsRes.tagDefs || [];
}

async function boot() {
  renderBrand();
  renderSidebar();
  renderTopbar();
  try {
    await reloadAllData();
  } catch (e) {
    reportError(e, 'Failed to load initial data');
  }
  await refreshCounts();
  navigateTo(state.currentView);
}

document.addEventListener('DOMContentLoaded', boot);
