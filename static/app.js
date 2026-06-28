// ============================================================================
// APP SHELL
// ============================================================================

function loadViewModePrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem('viewModePrefs') || '{}');
    return Object.assign({ devices: 'table', bandwidth: 'table', subnets: 'table' }, saved);
  } catch (e) {
    return { devices: 'table', bandwidth: 'table', subnets: 'table' };
  }
}

function saveViewModePrefs() {
  try { localStorage.setItem('viewModePrefs', JSON.stringify(state.viewMode)); } catch (e) { /* ignore */ }
}

const state = {
  devices: [],
  bandwidth: [],
  subnets: [],
  lists: { collectorRegions: [] },
  tagDefs: [],
  meta: { deviceCount: 0, bandwidthCount: 0, subnetCount: 0, lastSavedAt: null, lastSavedBy: null },
  currentView: 'dashboard',
  lastGenerateResult: null,
  viewMode: loadViewModePrefs(), // 'table' | 'card', persisted per-section
};

const VIEWS = [
  { group: 'Overview', items: [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'tree', label: 'Network Tree', icon: 'subnet' },
  ] },
  { group: 'Inventory', items: [
    { id: 'devices', label: 'Devices', icon: 'router', countKey: 'deviceCount' },
    { id: 'bandwidth', label: 'Bandwidth Capping', icon: 'bandwidth', countKey: 'bandwidthCount' },
    { id: 'subnets', label: 'Subnets', icon: 'subnet', countKey: 'subnetCount' },
  ] },
  { group: 'Configuration', items: [
    { id: 'tags', label: 'Manage Tags', icon: 'tag' },
    { id: 'lists', label: 'Manage Lists', icon: 'list' },
  ] },
  { group: 'Output', items: [
    { id: 'generate', label: 'Generate YAML', icon: 'generate' },
    { id: 'history', label: 'YAML History', icon: 'history' },
    { id: 'audit', label: 'Audit Log', icon: 'audit' },
  ] },
];

const VIEW_RENDERERS = {
  dashboard: () => Dashboard.render(),
  tree: () => NetworkTree.render(),
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
  tree: 'Network Tree',
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

function getCurrentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem('theme', theme); } catch (e) { /* ignore */ }
  renderThemeToggle();
}

function renderThemeToggle() {
  const btn = document.getElementById('btn-theme-toggle');
  if (!btn) return;
  const current = getCurrentTheme();
  // Button shows the icon for the mode you'd switch TO.
  btn.innerHTML = current === 'dark' ? icon('sun', { size: 16 }) : icon('moon', { size: 16 });
  btn.title = current === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
}

function renderSidebar() {
  const nav = document.getElementById('sidebar-nav');
  nav.innerHTML = VIEWS.map(group => `
    <div class="nav-group-label">${escapeHtml(group.group)}</div>
    ${group.items.map(item => `
      <div class="nav-item${state.currentView === item.id ? ' active' : ''}" data-view="${item.id}">
        <span class="icon">${icon(item.icon, { size: 16 })}</span>
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
  state.lists = Object.assign({ collectorRegions: [] }, listsRes.lists || {});
  state.tagDefs = tagsRes.tagDefs || [];
}

async function boot() {
  renderBrand();
  renderSidebar();
  renderTopbar();
  renderThemeToggle();
  document.getElementById('btn-theme-toggle').addEventListener('click', () => {
    setTheme(getCurrentTheme() === 'dark' ? 'light' : 'dark');
  });
  try {
    await reloadAllData();
  } catch (e) {
    reportError(e, 'Failed to load initial data');
  }
  await refreshCounts();
  navigateTo(state.currentView);
}

document.addEventListener('DOMContentLoaded', boot);
