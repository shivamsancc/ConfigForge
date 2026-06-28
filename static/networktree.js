// ============================================================================
// NETWORK TREE VIEW
//
// Fixed shape: Subnet -> Device -> Bandwidth Capping, with "Unassigned"
// buckets for devices with no matching subnet and bandwidth rows with no
// matching device (same CIDR-containment logic used elsewhere). A query
// bar supports "key:value" syntax against any fixed field or tag name
// (e.g. "collector_region:india", "country:india"); a dropdown offers
// the same filtering for people who'd rather pick than type. Filtering
// narrows which branches show -- it never changes the tree's shape.
//
// Interaction: click a node -> a details panel opens first (read-only),
// with an Edit button inside it that opens the real edit form. Hovering
// a subnet or device highlights the connector lines down to its
// descendants, animated.
// ============================================================================

const NetworkTree = (() => {
  let query = '';
  let expanded = new Set(); // node ids currently expanded
  let detailsNode = null;   // {type, record} currently shown in the details panel

  // ---------------------------------------------------------------------
  // IP / CIDR helpers (mirrors logic.py / dashboard.js)
  // ---------------------------------------------------------------------
  function ipToInt(ip) {
    const parts = (ip || '').split('.').map(Number);
    if (parts.length !== 4 || parts.some(n => Number.isNaN(n))) return null;
    return ((parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]) >>> 0;
  }

  function findContainingSubnet(ip) {
    const ipInt = ipToInt(ip);
    if (ipInt === null) return null;
    let best = null, bestPrefix = -1;
    for (const s of state.subnets) {
      const m = (s.CIDR || '').match(/^(\d+\.\d+\.\d+\.\d+)\/(\d+)$/);
      if (!m) continue;
      const baseInt = ipToInt(m[1]);
      const prefix = parseInt(m[2], 10);
      if (baseInt === null) continue;
      const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0;
      if ((ipInt & mask) === (baseInt & mask) && prefix > bestPrefix) {
        best = s; bestPrefix = prefix;
      }
    }
    return best;
  }

  // ---------------------------------------------------------------------
  // Build the fixed-shape tree: subnets -> devices -> bandwidth rows,
  // plus Unassigned buckets. Built fresh on every render from state, so
  // it always reflects current data.
  // ---------------------------------------------------------------------
  function buildTree() {
    const subnetToDevices = new Map(state.subnets.map(s => [s.id, []]));
    const unassignedDevices = [];

    for (const d of state.devices) {
      const subnet = d.IP ? findContainingSubnet(d.IP) : null;
      if (subnet) subnetToDevices.get(subnet.id).push(d);
      else unassignedDevices.push(d);
    }

    const deviceIpToDevice = new Map(state.devices.filter(d => d.IP).map(d => [d.IP, d]));
    const deviceToBandwidth = new Map(state.devices.map(d => [d.id, []]));
    const unassignedBandwidth = [];

    for (const b of state.bandwidth) {
      const device = b.IP ? deviceIpToDevice.get(b.IP) : null;
      if (device) deviceToBandwidth.get(device.id).push(b);
      else unassignedBandwidth.push(b);
    }

    return { subnetToDevices, deviceToBandwidth, unassignedDevices, unassignedBandwidth };
  }

  // ---------------------------------------------------------------------
  // Query parsing: "key:value" tokens (space-separated, AND semantics).
  // key resolves against fixed fields (case-insensitive, spaces/under-
  // scores interchangeable, e.g. "collector_region" matches "Collector
  // Region") or any tag name. value is a case-insensitive substring match.
  // ---------------------------------------------------------------------
  function normalizeKey(k) {
    return k.toLowerCase().replace(/[\s_]+/g, '');
  }

  function fieldValueForKey(record, key) {
    const norm = normalizeKey(key);
    for (const fieldName of Object.keys(record)) {
      if (normalizeKey(fieldName) === norm && typeof record[fieldName] === 'string') {
        return record[fieldName];
      }
    }
    for (const td of state.tagDefs) {
      if (normalizeKey(td.name) === norm) {
        const v = (record.tags || {})[td.id];
        if (v) return v;
      }
    }
    return undefined;
  }

  // Tokenizes on whitespace EXCEPT inside double quotes, so a value with
  // spaces (e.g. collector_region:"AWS US") survives as one token instead
  // of being split into "collector_region:AWS" + a stray "US" free-text
  // token (which silently turned into an unintended AND condition).
  function tokenizeQuery(q) {
    const tokens = [];
    const re = /"([^"]*)"|(\S+)/g;
    let m;
    let pending = '';
    let i = 0;
    const raw = q.trim();
    // Walk the string manually so a quoted segment immediately following
    // "key:" glues onto that key rather than becoming its own token.
    while (i < raw.length) {
      // Skip leading whitespace
      while (i < raw.length && /\s/.test(raw[i])) i++;
      if (i >= raw.length) break;
      let token = '';
      while (i < raw.length && !/\s/.test(raw[i])) {
        if (raw[i] === '"') {
          // Consume through the matching closing quote, spaces included.
          let j = i + 1;
          while (j < raw.length && raw[j] !== '"') j++;
          token += raw.slice(i + 1, j);
          i = j + 1;
        } else {
          token += raw[i];
          i++;
        }
      }
      if (token) tokens.push(token);
    }
    return tokens;
  }

  function parseQuery(q) {
    return tokenizeQuery(q).map(token => {
      const idx = token.indexOf(':');
      if (idx === -1) return { freeText: token.toLowerCase() };
      return { key: token.slice(0, idx), value: token.slice(idx + 1).toLowerCase() };
    });
  }

  function recordMatchesQuery(record, tokens) {
    if (tokens.length === 0) return true;
    return tokens.every(t => {
      if (t.freeText) return rowMatchesSearch(record, t.freeText);
      const v = fieldValueForKey(record, t.key);
      return v !== undefined && v.toLowerCase().includes(t.value);
    });
  }

  function subnetBranchMatches(subnet, devices, deviceToBandwidth, tokens) {
    if (tokens.length === 0) return true;
    if (recordMatchesQuery(subnet, tokens)) return true;
    return devices.some(d => deviceBranchMatches(d, deviceToBandwidth.get(d.id) || [], tokens));
  }

  function deviceBranchMatches(device, bwRows, tokens) {
    if (tokens.length === 0) return true;
    if (recordMatchesQuery(device, tokens)) return true;
    return bwRows.some(b => recordMatchesQuery(b, tokens));
  }

  function dropdownFilterOptions() {
    const opts = [{ key: 'collector_region', label: 'Collector Region', values: state.lists.collectorRegions || [] }];
    for (const td of state.tagDefs) {
      const values = td.values || [];
      if (values.length) opts.push({ key: normalizeKey(td.name), label: td.name, values });
    }
    return opts;
  }

  // ---------------------------------------------------------------------
  // Diagram state: which subnet/device is currently "selected" (drilled
  // into), as opposed to merely hovered. Selecting a column-1 card
  // populates column 2 with its devices; selecting a column-2 card
  // populates column 3 with its bandwidth rows. This is what keeps
  // hundreds-of-devices data readable -- only one branch's worth of
  // cards exist in columns 2/3 at a time, never all of them at once.
  // ---------------------------------------------------------------------
  let selectedSubnetId = null;   // 'subnet-<id>' | 'unassigned-devices' | null
  let selectedDeviceId = null;   // 'device-<id>' | null

  const CARD_W = { subnet: 226, device: 240, bandwidth: 196 };
  const CARD_H = 56;
  const CARD_GAP = 10;
  const COL_X = { subnet: 40, device: 320, bandwidth: 620 };
  const COL_TOP = 20;
  const MAX_CARDS_PER_COLUMN = 12; // beyond this, a column scrolls instead of growing the whole SVG

  // ---------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------
  async function render() {
    const content = document.getElementById('content');
    const dropdownOpts = dropdownFilterOptions();

    content.innerHTML = `
      <div class="tree-toolbar mb-16">
        <div class="tree-search-row">
          ${icon('search', { size: 15, className: 'tree-search-icon' })}
          <input type="text" id="tree-query" class="search-box tree-query-input" placeholder='e.g. collector_region:india  or  collector_region:"AWS US"' value="${escapeHtml(query)}" autocomplete="off">
        </div>
        <div class="flex gap-8 wrap items-center">
          ${dropdownOpts.map(opt => `
            <select class="tree-filter-dropdown" data-filter-key="${escapeHtml(opt.key)}">
              <option value="">${escapeHtml(opt.label)}&hellip;</option>
              ${opt.values.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('')}
            </select>
          `).join('')}
          ${query ? `<button class="btn btn-sm btn-ghost" id="tree-clear-query">Clear filter</button>` : ''}
        </div>
      </div>
      <div class="banner banner-info mb-16">
        <span>${icon('info', { size: 16 })}</span>
        <div class="banner-content">Click a subnet to reveal its devices, then click a device to reveal its bandwidth rows. Hover any card to trace its connections.${isMobileLayout() ? '' : ' Scroll/pinch to zoom, drag the background to pan.'}</div>
      </div>
      <div class="tree-diagram-wrap" id="tree-viewport">
        <div class="tree-zoom-layer" id="tree-zoom-layer">
          <div id="tree-diagram"></div>
        </div>
        <div class="tree-zoom-controls" id="tree-zoom-controls" style="${isMobileLayout() ? 'display:none;' : ''}">
          <button class="btn btn-icon btn-ghost" id="tree-zoom-out" title="Zoom out">${icon('minus', { size: 16 })}</button>
          <span class="tree-zoom-level" id="tree-zoom-level">100%</span>
          <button class="btn btn-icon btn-ghost" id="tree-zoom-in" title="Zoom in">${icon('plus', { size: 16 })}</button>
          <button class="btn btn-icon btn-ghost" id="tree-zoom-reset" title="Reset zoom">${icon('reset', { size: 16 })}</button>
        </div>
      </div>
      <div id="tree-details-overlay"></div>
    `;

    wireToolbar();
    wireZoomPan();
    renderDiagram();
  }

  // -----------------------------------------------------------------------
  // Pan + zoom viewport, Google-Maps style: scroll/pinch to zoom (anchored
  // to the cursor position so the thing under your pointer stays put),
  // click-drag the empty background to pan, buttons + keyboard for
  // accessibility. Card-internal interactions (click/hover) stop
  // propagation so they don't also trigger a pan-drag.
  // -----------------------------------------------------------------------
  let zoomState = { x: 0, y: 0, scale: 1 };
  const ZOOM_MIN = 0.4, ZOOM_MAX = 2.5;

  function applyZoomTransform() {
    const layer = document.getElementById('tree-zoom-layer');
    if (!layer) return;
    layer.style.transform = `translate(${zoomState.x}px, ${zoomState.y}px) scale(${zoomState.scale})`;
    const label = document.getElementById('tree-zoom-level');
    if (label) label.textContent = `${Math.round(zoomState.scale * 100)}%`;
  }

  // Keeps column 1 (which always starts at the content's top-left
  // origin) substantially visible after any zoom/pan, so a button zoom
  // -- which anchors at the viewport's center rather than the cursor --
  // can never push the diagram fully out of view with no way back
  // except the reset button. Clamps panning so the origin can drift at
  // most one viewport's worth of distance in any direction.
  function clampZoomToContent() {
    const viewport = document.getElementById('tree-viewport');
    if (!viewport) return;
    const vw = viewport.clientWidth, vh = viewport.clientHeight;

    // The translate is applied before scale in the transform, so the
    // on-screen position of the content origin (0,0) is exactly
    // (zoomState.x, zoomState.y) regardless of scale. Keep that point
    // from drifting more than one viewport dimension off in any
    // direction, so there's always a fast drag back into view.
    const minX = -vw * 0.9;
    const maxX = vw * 0.9;
    const minY = -vh * 0.9;
    const maxY = vh * 0.9;

    zoomState.x = Math.min(maxX, Math.max(minX, zoomState.x));
    zoomState.y = Math.min(maxY, Math.max(minY, zoomState.y));
  }

  function zoomBy(factor, anchorClientX, anchorClientY) {
    const viewport = document.getElementById('tree-viewport');
    if (!viewport) return;
    const rect = viewport.getBoundingClientRect();
    const ax = anchorClientX !== undefined ? anchorClientX - rect.left : rect.width / 2;
    const ay = anchorClientY !== undefined ? anchorClientY - rect.top : rect.height / 2;

    const newScale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoomState.scale * factor));
    const actualFactor = newScale / zoomState.scale;
    // Keep the point under the cursor fixed in place while scaling.
    zoomState.x = ax - (ax - zoomState.x) * actualFactor;
    zoomState.y = ay - (ay - zoomState.y) * actualFactor;
    zoomState.scale = newScale;
    clampZoomToContent();
    applyZoomTransform();
  }

  function resetZoom() {
    zoomState = { x: 0, y: 0, scale: 1 };
    applyZoomTransform();
  }

  function isMobileLayout() {
    return window.innerWidth <= 900;
  }

  function wireZoomPan() {
    if (isMobileLayout()) return; // pan/zoom doesn't apply once columns stack vertically
    const viewport = document.getElementById('tree-viewport');
    const layer = document.getElementById('tree-zoom-layer');
    resetZoom();

    document.getElementById('tree-zoom-in').addEventListener('click', () => {
      const r = viewport.getBoundingClientRect();
      zoomBy(1.25, r.left + 140, r.top + 100);
    });
    document.getElementById('tree-zoom-out').addEventListener('click', () => {
      const r = viewport.getBoundingClientRect();
      zoomBy(0.8, r.left + 140, r.top + 100);
    });
    document.getElementById('tree-zoom-reset').addEventListener('click', resetZoom);

    // Wheel-to-zoom, anchored at the cursor. Plain scroll (no modifier)
    // zooms rather than scrolling the page, matching the map-like feel
    // that was asked for; per-column card lists still scroll normally
    // via their own internal overflow when the wheel event happens
    // directly over a card list rather than empty canvas -- handled by
    // letting the column's native scroll take it when not over empty bg.
    viewport.addEventListener('wheel', (e) => {
      const overColumn = e.target.closest('.tree-col');
      if (overColumn) {
        // Inside a card column: let normal vertical scroll happen unless
        // the person is holding Ctrl/Cmd (the conventional zoom modifier
        // when over scrollable content).
        if (!(e.ctrlKey || e.metaKey)) return;
      }
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.08 : 0.93;
      zoomBy(factor, e.clientX, e.clientY);
    }, { passive: false });

    // Click-drag to pan, but only starting from empty canvas background
    // (not from a card or a column's own scrollbar), so dragging a card
    // list still works as a normal scroll, not a pan.
    let panActive = false, panStart = { x: 0, y: 0 }, originStart = { x: 0, y: 0 };
    viewport.addEventListener('mousedown', (e) => {
      if (e.target.closest('.tree-card') || e.target.closest('.tree-col')) return;
      panActive = true;
      panStart = { x: e.clientX, y: e.clientY };
      originStart = { x: zoomState.x, y: zoomState.y };
      viewport.classList.add('panning');
    });
    window.addEventListener('mousemove', (e) => {
      if (!panActive) return;
      zoomState.x = originStart.x + (e.clientX - panStart.x);
      zoomState.y = originStart.y + (e.clientY - panStart.y);
      clampZoomToContent();
      applyZoomTransform();
    });
    window.addEventListener('mouseup', () => {
      panActive = false;
      viewport.classList.remove('panning');
    });

    // Basic pinch-to-zoom for touch devices.
    let pinchStartDist = null, pinchStartScale = 1;
    viewport.addEventListener('touchstart', (e) => {
      if (e.touches.length === 2) {
        pinchStartDist = touchDist(e.touches);
        pinchStartScale = zoomState.scale;
      }
    }, { passive: true });
    viewport.addEventListener('touchmove', (e) => {
      if (e.touches.length === 2 && pinchStartDist) {
        const dist = touchDist(e.touches);
        const factor = (dist / pinchStartDist) * pinchStartScale / zoomState.scale;
        const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
        const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        zoomBy(factor, midX, midY);
      }
    }, { passive: true });
  }

  function touchDist(touches) {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function wireToolbar() {
    const input = document.getElementById('tree-query');
    input.addEventListener('input', (e) => {
      query = e.target.value;
      renderDiagram();
      syncClearButton();
    });
    const clearBtn = document.getElementById('tree-clear-query');
    if (clearBtn) clearBtn.addEventListener('click', () => { query = ''; render(); });

    document.querySelectorAll('.tree-filter-dropdown').forEach(sel => {
      sel.addEventListener('change', () => {
        if (!sel.value) return;
        const key = sel.dataset.filterKey;
        const existingTokens = tokenizeQuery(query).filter(t => {
          const idx = t.indexOf(':');
          return idx === -1 || t.slice(0, idx).toLowerCase() !== key;
        });
        const valueNeedsQuotes = /\s/.test(sel.value);
        const newToken = `${key}:${valueNeedsQuotes ? `"${sel.value}"` : sel.value}`;
        query = [...existingTokens, newToken].join(' ');
        render();
      });
    });
  }

  function syncClearButton() {
    const existing = document.getElementById('tree-clear-query');
    const dropdownRow = document.querySelector('.tree-toolbar > .flex.gap-8');
    if (query && !existing && dropdownRow) {
      const btn = document.createElement('button');
      btn.className = 'btn btn-sm btn-ghost';
      btn.id = 'tree-clear-query';
      btn.textContent = 'Clear filter';
      btn.addEventListener('click', () => { query = ''; render(); });
      dropdownRow.appendChild(btn);
    } else if (!query && existing) {
      existing.remove();
    }
  }

  // -----------------------------------------------------------------------
  // Diagram data assembly: figure out what's visible in each column given
  // the current filter + selection state.
  // -----------------------------------------------------------------------
  function assembleColumns() {
    const { subnetToDevices, deviceToBandwidth, unassignedDevices, unassignedBandwidth } = buildTree();
    const tokens = parseQuery(query);

    const allSubnetEntries = state.subnets
      .map(s => ({ id: `subnet-${s.id}`, record: s, devices: subnetToDevices.get(s.id) || [] }))
      .filter(({ record, devices }) => subnetBranchMatches(record, devices, deviceToBandwidth, tokens));

    const matchedUnassignedDevices = unassignedDevices.filter(d => deviceBranchMatches(d, deviceToBandwidth.get(d.id) || [], tokens));
    const matchedUnassignedBandwidth = tokens.length === 0 ? unassignedBandwidth : unassignedBandwidth.filter(b => recordMatchesQuery(b, tokens));

    // Column 1: every matching subnet, plus the Unassigned Devices bucket
    // (always shown if it has matches) -- Unassigned Bandwidth is reached
    // via column 3 only after a device with orphaned bandwidth... actually
    // bandwidth orphans have no device, so they get their own column-1-style
    // entry too, feeding column 3 directly when selected.
    const col1 = [...allSubnetEntries];
    if (matchedUnassignedDevices.length > 0) {
      col1.push({ id: 'unassigned-devices', record: null, devices: matchedUnassignedDevices, isUnassignedDevices: true });
    }
    if (matchedUnassignedBandwidth.length > 0) {
      col1.push({ id: 'unassigned-bandwidth', record: null, devices: [], isUnassignedBandwidth: true, bwRows: matchedUnassignedBandwidth });
    }

    // Column 2: devices belonging to whichever column-1 card is selected.
    let col2 = [];
    const selectedCol1 = col1.find(c => c.id === selectedSubnetId);
    if (selectedCol1 && !selectedCol1.isUnassignedBandwidth) {
      col2 = selectedCol1.devices.map(d => ({ id: `device-${d.id}`, record: d, bwRows: deviceToBandwidth.get(d.id) || [] }));
    }

    // Column 3: bandwidth rows belonging to whichever column-2 card is
    // selected, OR the Unassigned Bandwidth bucket's rows if that's what's
    // selected in column 1 (it has no column-2 step, since it has no device).
    let col3 = [];
    if (selectedCol1 && selectedCol1.isUnassignedBandwidth) {
      col3 = selectedCol1.bwRows.map(b => ({ id: `bw-${b.id}`, record: b }));
    } else {
      const selectedCol2 = col2.find(c => c.id === selectedDeviceId);
      if (selectedCol2) {
        col3 = selectedCol2.bwRows.map(b => ({ id: `bw-${b.id}`, record: b }));
      }
    }

    return { col1, col2, col3 };
  }

  // -----------------------------------------------------------------------
  // SVG layout + rendering
  // -----------------------------------------------------------------------
  function renderDiagram() {
    const container = document.getElementById('tree-diagram');
    const { col1, col2, col3 } = assembleColumns();

    if (col1.length === 0) {
      container.innerHTML = emptyState({
        title: state.subnets.length === 0 && state.devices.length === 0 ? 'Nothing to show yet' : 'No matches for this filter',
        sub: state.subnets.length === 0 && state.devices.length === 0
          ? 'Add subnets and devices to see the network diagram.'
          : 'Try a different query, or clear the filter.',
      });
      return;
    }

    container.innerHTML = `
      <div class="tree-columns">
        <div class="tree-col" data-col="1">${col1.map(c => cardHtml(c, columnKindFor(c))).join('')}</div>
        <div class="tree-col" data-col="2">${col2.length ? col2.map(c => cardHtml(c, 'device')).join('') : emptyColumnHint(selectedSubnetId ? 'No devices in this subnet' : 'Select a subnet to see its devices')}</div>
        <div class="tree-col" data-col="3">${col3.length ? col3.map(c => cardHtml(c, 'bandwidth')).join('') : emptyColumnHint(selectedDeviceId || selectedSubnetId === 'unassigned-bandwidth' ? 'No bandwidth rows' : 'Select a device to see its bandwidth rows')}</div>
      </div>
      <svg class="tree-connector-svg"></svg>
    `;

    wireDiagramInteractions(container, { col1, col2, col3 });
    requestAnimationFrame(() => {
      drawConnectors(container);
      if (!isMobileLayout()) {
        clampZoomToContent();
        applyZoomTransform();
      }
    });

    const cols = container.querySelectorAll('.tree-col');
    cols.forEach(col => col.addEventListener('scroll', () => drawConnectors(container), { passive: true }));
  }

  function columnKindFor(c) {
    if (c.isUnassignedDevices || c.isUnassignedBandwidth) return 'unassigned';
    return 'subnet';
  }

  function emptyColumnHint(text) {
    return `<div class="tree-col-hint">${escapeHtml(text)}</div>`;
  }

  function cardHtml(c, kind) {
    const isSelected = c.id === selectedSubnetId || c.id === selectedDeviceId;
    let iconName, title, sub, badge = '';

    if (kind === 'unassigned') {
      iconName = 'warning';
      title = c.isUnassignedDevices ? 'Unassigned Devices' : 'Unassigned Bandwidth';
      sub = c.isUnassignedDevices ? `${c.devices.length} device${c.devices.length === 1 ? '' : 's'}` : `${c.bwRows.length} row${c.bwRows.length === 1 ? '' : 's'}`;
    } else if (kind === 'subnet') {
      iconName = 'subnet';
      title = c.record.CIDR;
      sub = `${c.devices.length} device${c.devices.length === 1 ? '' : 's'}`;
    } else if (kind === 'device') {
      iconName = 'router';
      title = c.record.Device || '(unnamed)';
      sub = c.record.IP;
      const statusBadge = Devices.isIcmpForced(c.record)
        ? '<span class="badge badge-neutral">ICMP</span>'
        : (Devices.missingCreds(c.record) ? '<span class="badge badge-warn">!</span>' : '<span class="badge badge-ok">SNMP</span>');
      const bwCount = (c.bwRows || []).length;
      const bwBadge = bwCount > 0
        ? `<span class="badge tree-bw-badge tree-bw-badge-has" title="${bwCount} bandwidth row${bwCount === 1 ? '' : 's'}">${icon('bandwidth', { size: 10 })} ${bwCount}</span>`
        : `<span class="badge tree-bw-badge tree-bw-badge-none" title="No bandwidth capping configured">${icon('bandwidth', { size: 10 })} &mdash;</span>`;
      badge = `<div class="tree-card-badges">${statusBadge}${bwBadge}</div>`;
    } else {
      iconName = 'bandwidth';
      title = c.record.Interface;
      sub = c.record['Allocated BW'] || c.record.IP;
    }

    const colorClass = kind === 'unassigned' ? 'tree-card-unassigned' : `tree-card-${kind}`;
    return `
      <div class="tree-card ${colorClass}${isSelected ? ' selected' : ''}" data-card-id="${escapeHtml(c.id)}">
        <div class="tree-card-icon">${icon(iconName, { size: 16 })}</div>
        <div class="tree-card-text">
          <div class="tree-card-title" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
          <div class="tree-card-sub" title="${escapeHtml(sub)}">${escapeHtml(sub)}</div>
        </div>
        ${badge}
      </div>
    `;
  }

  // Draws connector lines as an SVG overlay sized to the container, using
  // each card's ACTUAL rendered position (getBoundingClientRect), so
  // scrolling any column keeps the lines correctly anchored without
  // needing to track scroll offsets manually.
  function drawConnectors(container) {
    const svg = container.querySelector('.tree-connector-svg');
    if (!svg) return;
    const wrapRect = container.querySelector('.tree-columns').getBoundingClientRect();
    svg.setAttribute('width', wrapRect.width);
    svg.setAttribute('height', wrapRect.height);
    svg.setAttribute('viewBox', `0 0 ${wrapRect.width} ${wrapRect.height}`);

    const pairs = [];
    if (selectedSubnetId) {
      const srcEl = container.querySelector(`.tree-card[data-card-id="${cssEscape(selectedSubnetId)}"]`);
      if (srcEl && container.querySelector('[data-col="1"]').contains(srcEl)) {
        container.querySelectorAll('[data-col="2"] .tree-card').forEach(el => pairs.push([srcEl, el, selectedSubnetId, el.dataset.cardId]));
      }
    }
    if (selectedDeviceId) {
      const srcEl = container.querySelector(`[data-col="2"] .tree-card[data-card-id="${cssEscape(selectedDeviceId)}"]`);
      if (srcEl) {
        container.querySelectorAll('[data-col="3"] .tree-card').forEach(el => pairs.push([srcEl, el, selectedDeviceId, el.dataset.cardId]));
      }
    }
    if (selectedSubnetId === 'unassigned-bandwidth') {
      const srcEl = container.querySelector(`[data-col="1"] .tree-card[data-card-id="unassigned-bandwidth"]`);
      if (srcEl) {
        container.querySelectorAll('[data-col="3"] .tree-card').forEach(el => pairs.push([srcEl, el, 'unassigned-bandwidth', el.dataset.cardId]));
      }
    }

    const paths = pairs.map(([srcEl, dstEl, fromId, toId]) => {
      const sr = srcEl.getBoundingClientRect(), dr = dstEl.getBoundingClientRect();
      // Skip drawing (but keep hoverable mapping) when either endpoint is
      // scrolled out of view, to avoid stray lines shooting off-canvas.
      const colSrc = srcEl.closest('.tree-col'), colDst = dstEl.closest('.tree-col');
      const srcVisible = rectWithin(sr, colSrc.getBoundingClientRect());
      const dstVisible = rectWithin(dr, colDst.getBoundingClientRect());
      if (!srcVisible || !dstVisible) return '';
      const x1 = sr.right - wrapRect.left, y1 = sr.top + sr.height / 2 - wrapRect.top;
      const x2 = dr.left - wrapRect.left, y2 = dr.top + dr.height / 2 - wrapRect.top;
      const midX = (x1 + x2) / 2;
      return `<path d="M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}" class="tree-connector" fill="none" data-from="${escapeHtml(fromId)}" data-to="${escapeHtml(toId)}"/>`;
    });
    svg.innerHTML = paths.join('');
  }

  function rectWithin(inner, outer) {
    return inner.bottom > outer.top && inner.top < outer.bottom;
  }

  // -----------------------------------------------------------------------
  // Interactions: click selects/drills, hover traces connector lines,
  // a second click on a details-opening icon opens the details popup.
  // -----------------------------------------------------------------------
  function wireDiagramInteractions(container, columns) {
    container.querySelectorAll('.tree-card').forEach(card => {
      const cardId = card.dataset.cardId;

      card.addEventListener('mouseenter', () => traceConnectors(container, cardId, true));
      card.addEventListener('mouseleave', () => traceConnectors(container, cardId, false));

      card.addEventListener('click', (e) => {
        e.stopPropagation();
        handleCardClick(cardId, columns);
      });
    });
  }

  function traceConnectors(container, cardId, on) {
    container.querySelectorAll(`path[data-from="${cssEscape(cardId)}"], path[data-to="${cssEscape(cardId)}"]`).forEach(p => {
      p.classList.toggle('active', on);
    });
    const card = container.querySelector(`.tree-card[data-card-id="${cssEscape(cardId)}"]`);
    if (card) card.classList.toggle('hovering', on);
  }

  function cssEscape(s) {
    return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  function handleCardClick(cardId, columns) {
    const inCol1 = columns.col1.some(c => c.id === cardId);
    const inCol2 = columns.col2.some(c => c.id === cardId);
    const inCol3 = columns.col3.some(c => c.id === cardId);

    if (inCol1) {
      // Clicking the already-selected subnet opens its details instead of
      // toggling selection off -- avoids a dead click once you're already
      // looking at its devices.
      if (selectedSubnetId === cardId) {
        openDetailsForCardId(cardId, columns);
        return;
      }
      selectedSubnetId = cardId;
      selectedDeviceId = null;
      renderDiagram();
      return;
    }
    if (inCol2) {
      if (selectedDeviceId === cardId) {
        openDetailsForCardId(cardId, columns);
        return;
      }
      selectedDeviceId = cardId;
      renderDiagram();
      return;
    }
    if (inCol3) {
      openDetailsForCardId(cardId, columns);
    }
  }

  function openDetailsForCardId(cardId, columns) {
    const all = [...columns.col1, ...columns.col2, ...columns.col3];
    const entry = all.find(c => c.id === cardId);
    if (!entry || !entry.record) return; // unassigned buckets have no single record to show
    const type = cardId.startsWith('subnet-') ? 'subnet' : cardId.startsWith('device-') ? 'device' : 'bandwidth';
    openDetails(type, entry.record);
  }

  // -----------------------------------------------------------------------
  // Details popup (click-for-details, then Edit) -- unchanged behavior
  // from the list version, just invoked from the diagram instead.
  // -----------------------------------------------------------------------
  function openDetails(type, record) {
    const overlay = document.getElementById('tree-details-overlay');
    overlay.innerHTML = renderDetailsPopup(type, record);
    requestAnimationFrame(() => {
      const backdrop = overlay.querySelector('.tree-details-backdrop');
      const card = overlay.querySelector('.tree-details-card');
      if (backdrop) backdrop.classList.add('open');
      if (card) card.classList.add('open');
    });

    overlay.querySelector('.tree-details-backdrop').addEventListener('click', closeDetails);
    overlay.querySelector('[data-act="close-details"]').addEventListener('click', closeDetails);

    const editDeviceBtn = overlay.querySelector('[data-act="edit-device"]');
    if (editDeviceBtn) editDeviceBtn.addEventListener('click', () => { closeDetails(); openDeviceEdit(record); });
    const editBwBtn = overlay.querySelector('[data-act="edit-bandwidth"]');
    if (editBwBtn) editBwBtn.addEventListener('click', () => { closeDetails(); openBandwidthEdit(editBwBtn.dataset.bwId); });
    const editSubnetBtn = overlay.querySelector('[data-act="edit-subnet"]');
    if (editSubnetBtn) editSubnetBtn.addEventListener('click', () => { closeDetails(); openSubnetEdit(record); });
  }

  function closeDetails() {
    const overlay = document.getElementById('tree-details-overlay');
    const backdrop = overlay.querySelector('.tree-details-backdrop');
    const card = overlay.querySelector('.tree-details-card');
    if (!backdrop || !card) { overlay.innerHTML = ''; return; }
    backdrop.classList.remove('open');
    card.classList.remove('open');
    setTimeout(() => { overlay.innerHTML = ''; }, 200);
  }

  function openDeviceEdit(device) {
    if (Devices._openFormExternal) {
      Devices._openFormExternal(device);
      watchForModalClose(renderDiagram);
    }
  }
  function openBandwidthEdit(bwId) {
    const row = state.bandwidth.find(b => b.id === bwId);
    if (row && Bandwidth._openFormExternal) {
      Bandwidth._openFormExternal(row);
      watchForModalClose(renderDiagram);
    }
  }
  function openSubnetEdit(subnet) {
    if (Subnets._openFormExternal) {
      Subnets._openFormExternal(subnet);
      watchForModalClose(renderDiagram);
    }
  }

  function watchForModalClose(callback) {
    const check = () => {
      if (document.querySelector('.modal-overlay')) {
        setTimeout(check, 150);
      } else {
        callback();
      }
    };
    setTimeout(check, 150);
  }

  function renderDetailsPopup(type, record) {
    if (type === 'subnet') return subnetDetailsHtml(record);
    if (type === 'device') return deviceDetailsHtml(record);
    if (type === 'bandwidth') return bandwidthDetailsHtml(record);
    return '';
  }

  function subnetDetailsHtml(subnet) {
    return `
      <div class="tree-details-backdrop"></div>
      <div class="tree-details-card">
        <div class="tree-details-header">
          <div class="tree-details-icon tree-pill-subnet">${icon('subnet', { size: 18 })}</div>
          <div>
            <div class="tree-details-title mono">${escapeHtml(subnet.CIDR)}</div>
            <div class="tree-details-sub">${escapeHtml(subnet.Description || 'Subnet')}</div>
          </div>
          <button class="modal-close" data-act="close-details">&times;</button>
        </div>
        <div class="tree-details-body">
          ${TagFields.renderBadges('subnets', subnet.tags) || '<span class="text-faint">No tags set.</span>'}
        </div>
        <div class="tree-details-footer">
          <button class="btn btn-primary" data-act="edit-subnet">${icon('edit', { size: 14 })} Edit Subnet</button>
        </div>
      </div>
    `;
  }

  function deviceDetailsHtml(device) {
    const bwRows = state.bandwidth.filter(b => b.IP === device.IP);
    return `
      <div class="tree-details-backdrop"></div>
      <div class="tree-details-card">
        <div class="tree-details-header">
          <div class="tree-details-icon tree-pill-device">${icon('router', { size: 18 })}</div>
          <div>
            <div class="tree-details-title">${escapeHtml(device.Device || '(unnamed)')}</div>
            <div class="tree-details-sub mono">${escapeHtml(device.IP)}</div>
          </div>
          <button class="modal-close" data-act="close-details">&times;</button>
        </div>
        <div class="tree-details-body">
          <div class="status-row"><span class="text-dim">Collector Region</span><span>${escapeHtml(device['Collector Region'] || '\u2014')}</span></div>
          <div class="status-row"><span class="text-dim">Config Type</span><span>${escapeHtml(device['Config Type'] || '\u2014')}</span></div>
          <div class="status-row"><span class="text-dim">Status</span><span>${Devices.isIcmpForced(device) ? 'ICMP-only' : (Devices.missingCreds(device) ? 'SNMP \u2014 missing creds' : 'SNMP')}</span></div>
          ${TagFields.renderBadges('devices', device.tags) ? `<div class="mt-12">${TagFields.renderBadges('devices', device.tags)}</div>` : ''}
        </div>
        <div class="tree-details-footer">
          <button class="btn btn-primary" data-act="edit-device">${icon('edit', { size: 14 })} Edit Device</button>
          ${bwRows.length > 0 ? `<button class="btn" data-act="edit-bandwidth" data-bw-id="${escapeHtml(bwRows[0].id)}">${icon('bandwidth', { size: 14 })} Edit Bandwidth Capping${bwRows.length > 1 ? ` (${bwRows.length})` : ''}</button>` : ''}
        </div>
      </div>
    `;
  }

  function bandwidthDetailsHtml(row) {
    return `
      <div class="tree-details-backdrop"></div>
      <div class="tree-details-card">
        <div class="tree-details-header">
          <div class="tree-details-icon tree-pill-bw">${icon('bandwidth', { size: 18 })}</div>
          <div>
            <div class="tree-details-title mono">${escapeHtml(row.Interface)}</div>
            <div class="tree-details-sub mono">${escapeHtml(row.IP)}</div>
          </div>
          <button class="modal-close" data-act="close-details">&times;</button>
        </div>
        <div class="tree-details-body">
          <div class="status-row"><span class="text-dim">Allocated BW</span><span>${escapeHtml(row['Allocated BW'] || '\u2014')}</span></div>
          <div class="status-row"><span class="text-dim">Link Type</span><span>${escapeHtml(row['Link Type'] || '\u2014')}</span></div>
          <div class="status-row"><span class="text-dim">Description</span><span>${escapeHtml(row.Interface_description || '\u2014')}</span></div>
          ${TagFields.renderBadges('bandwidth', row.tags) ? `<div class="mt-12">${TagFields.renderBadges('bandwidth', row.tags)}</div>` : ''}
        </div>
        <div class="tree-details-footer">
          <button class="btn btn-primary" data-act="edit-bandwidth" data-bw-id="${escapeHtml(row.id)}">${icon('edit', { size: 14 })} Edit Bandwidth Capping</button>
        </div>
      </div>
    `;
  }

  return { render };
})();