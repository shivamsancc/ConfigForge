// ============================================================================
// DASHBOARD VIEW
// ============================================================================

const Dashboard = (() => {
  async function render() {
    const content = document.getElementById('content');

    const deviceMissingRegion = state.devices.filter(d => !d['Collector Region']).length;
    const deviceMissingCreds = state.devices.filter(d => !Devices.isIcmpForced(d) && Devices.missingCreds(d)).length;
    const icmpDevices = state.devices.filter(d => Devices.isIcmpForced(d)).length;
    const snmpDevices = state.devices.length - icmpDevices;

    content.innerHTML = `
      <div class="stat-grid">
        ${statCard('Devices', state.devices.length, `${snmpDevices} SNMP &middot; ${icmpDevices} ICMP-only`)}
        ${statCard('Bandwidth Rows', state.bandwidth.length, `${countDistinctIps(state.bandwidth)} unique IP(s)`)}
        ${statCard('Subnets', state.subnets.length, `${state.subnets.filter(s => Object.keys(s.tags || {}).length > 0).length} tagged`)}
        ${statCard('Tags Defined', state.tagDefs.length, `${state.tagDefs.reduce((acc, t) => acc + (t.values || []).length, 0)} total values`)}
      </div>

      ${(deviceMissingRegion > 0 || deviceMissingCreds > 0) ? `
        <div class="banner banner-warn mb-16">
          <span>&#9888;</span>
          <div class="banner-content">
            ${deviceMissingRegion > 0 ? `<b>${deviceMissingRegion}</b> device(s) missing Collector Region. ` : ''}
            ${deviceMissingCreds > 0 ? `<b>${deviceMissingCreds}</b> device(s) missing SNMPv3 credentials. ` : ''}
            <button class="link" data-nav="devices">Review devices</button>
          </div>
        </div>
      ` : ''}

      <div class="dash-section">
        <div class="dash-section-title">Devices by Collector Region</div>
        <div class="panel panel-body">${breakdownBars(groupCount(state.devices, 'Collector Region'))}</div>
      </div>

      ${state.tagDefs.length > 0 ? renderTagBreakdowns() : ''}

      <div class="dash-section">
        <div class="dash-section-title">Recent Activity</div>
        <div class="panel" id="dash-recent-audit"><div class="loading-row"><div class="spinner"></div> Loading&hellip;</div></div>
      </div>
    `;

    content.querySelectorAll('[data-nav]').forEach(el => el.addEventListener('click', () => navigateTo(el.dataset.nav)));

    try {
      const audit = await Api.getAudit(8);
      renderRecentAudit(audit.entries || []);
    } catch (e) {
      document.getElementById('dash-recent-audit').innerHTML = `<div class="panel-body text-faint">Could not load recent activity.</div>`;
    }
  }

  function statCard(label, value, sub) {
    return `
      <div class="stat-card">
        <div class="stat-card-label">${escapeHtml(label)}</div>
        <div class="stat-card-value">${value}</div>
        <div class="stat-card-sub">${escapeHtml(sub)}</div>
      </div>
    `;
  }

  function countDistinctIps(rows) {
    return new Set(rows.map(r => r.IP).filter(Boolean)).size;
  }

  function groupCount(records, field) {
    const counts = {};
    for (const r of records) {
      const v = (r[field] || '').trim() || '(none)';
      counts[v] = (counts[v] || 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }

  function breakdownBars(entries) {
    if (entries.length === 0) return `<div class="text-faint" style="font-size:12.5px;">No data yet.</div>`;
    const max = Math.max(...entries.map(([, c]) => c));
    return entries.map(([label, count]) => `
      <div class="bar-row">
        <div class="bar-label" title="${escapeHtml(label)}">${escapeHtml(label)}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.max(4, (count / max) * 100)}%"></div></div>
        <div class="bar-value">${count}</div>
      </div>
    `).join('');
  }

  // Mirrors logic.py's resolve_tags_for_record: a device/bandwidth-row's
  // own tag value wins if set; otherwise, for tags scoped to subnets, fall
  // back to the value from the most specific containing subnet. Without
  // this, dashboard counts would undercount inherited tags (a device that
  // shows up correctly in generated YAML via inheritance would silently
  // read as untagged here).
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

  function resolvedTagValue(record, td, scope) {
    const own = (record.tags || {})[td.id];
    if (own) return own;
    if (scope === 'devices' && td.scopes.includes('subnets') && record.IP) {
      const subnet = findContainingSubnet(record.IP);
      if (subnet) return (subnet.tags || {})[td.id];
    }
    return undefined;
  }

  function renderTagBreakdowns() {
    const scopeLabels = { devices: 'Devices', bandwidth: 'Bandwidth Rows', subnets: 'Subnets' };
    return state.tagDefs.map(td => {
      const sections = td.scopes.map(scope => {
        const records = scope === 'devices' ? state.devices : scope === 'bandwidth' ? state.bandwidth : state.subnets;
        const counts = {};
        for (const r of records) {
          const v = resolvedTagValue(r, td, scope);
          if (v) counts[v] = (counts[v] || 0) + 1;
        }
        const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
        return `
          <div class="dash-section">
            <div class="dash-section-title">${escapeHtml(td.name)} &mdash; ${escapeHtml(scopeLabels[scope] || scope)}</div>
            <div class="panel panel-body">${breakdownBars(entries)}</div>
          </div>
        `;
      });
      return sections.join('');
    }).join('');
  }

  function renderRecentAudit(entries) {
    const el = document.getElementById('dash-recent-audit');
    if (entries.length === 0) {
      el.innerHTML = `<div class="panel-body text-faint">No activity yet.</div>`;
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th></tr></thead>
      <tbody>
        ${entries.map(e => `
          <tr><td class="mono">${escapeHtml(e.ts)}</td><td>${escapeHtml(e.actor || 'unknown')}</td><td><span class="badge badge-neutral">${escapeHtml(e.action)}</span></td></tr>
        `).join('')}
      </tbody>
    </table></div>`;
  }

  return { render };
})();
