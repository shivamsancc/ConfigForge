// ============================================================================
// API -- thin wrapper around the backend REST endpoints.
// ============================================================================

const Api = (() => {
  async function request(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(path, opts);
    } catch (e) {
      throw new Error(`Network error calling ${method} ${path}: ${e.message}`);
    }
    let data = null;
    const text = await res.text();
    if (text) {
      try { data = JSON.parse(text); } catch (e) { /* non-JSON response */ }
    }
    if (!res.ok) {
      const err = new Error((data && (data.error || data.message)) || res.statusText || `HTTP ${res.status}`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function withActor(body) {
    return Object.assign({}, body, { _actor: getEditorName() });
  }

  return {
    // Devices
    getDevices: () => request('GET', '/api/devices'),
    saveDevice: (device) => request('POST', '/api/devices', withActor({ device })),
    deleteDevice: (id) => request('DELETE', `/api/devices/${encodeURIComponent(id)}?_actor=${encodeURIComponent(getEditorName())}`),
    importDevices: (devices, mode) => request('POST', '/api/devices/import', withActor({ devices, mode })),
    validateImportDevices: (devices, mode) => request('POST', '/api/devices/validate-import', { devices, mode }),

    // Bandwidth
    getBandwidth: () => request('GET', '/api/bandwidth'),
    saveBandwidth: (row) => request('POST', '/api/bandwidth', withActor({ row })),
    deleteBandwidth: (id) => request('DELETE', `/api/bandwidth/${encodeURIComponent(id)}?_actor=${encodeURIComponent(getEditorName())}`),
    importBandwidth: (rows, mode) => request('POST', '/api/bandwidth/import', withActor({ rows, mode })),
    validateImportBandwidth: (rows, mode) => request('POST', '/api/bandwidth/validate-import', { rows, mode }),

    // Subnets
    getSubnets: () => request('GET', '/api/subnets'),
    saveSubnet: (subnet) => request('POST', '/api/subnets', withActor({ subnet })),
    deleteSubnet: (id) => request('DELETE', `/api/subnets/${encodeURIComponent(id)}?_actor=${encodeURIComponent(getEditorName())}`),
    importSubnets: (subnets, mode) => request('POST', '/api/subnets/import', withActor({ subnets, mode })),
    validateImportSubnets: (subnets, mode) => request('POST', '/api/subnets/validate-import', { subnets, mode }),

    // Fixed lists
    getLists: () => request('GET', '/api/lists'),
    setList: (listName, items) => request('POST', `/api/lists/${encodeURIComponent(listName)}`, withActor({ items })),
    getListUsage: (listName, value) => request('GET', `/api/lists/${encodeURIComponent(listName)}/usage?value=${encodeURIComponent(value)}`),

    // Dynamic tags
    getTags: () => request('GET', '/api/tags'),
    saveTag: (tagDef) => request('POST', '/api/tags', withActor({ tagDef })),
    deleteTag: (id, force = false) => request('DELETE', `/api/tags/${encodeURIComponent(id)}?_actor=${encodeURIComponent(getEditorName())}${force ? '&force=true' : ''}`),
    getTagUsage: (id, value) => request('GET', `/api/tags/${encodeURIComponent(id)}/usage${value !== undefined ? `?value=${encodeURIComponent(value)}` : ''}`),

    // Audit / history
    getAudit: (limit = 100) => request('GET', `/api/audit?limit=${limit}`),
    getHistory: (limit = 50) => request('GET', `/api/history?limit=${limit}`),
    getHistoryEntry: (id) => request('GET', `/api/history/${encodeURIComponent(id)}`),

    // Generate
    generate: () => request('POST', '/api/generate', withActor({})),

    // Meta
    getMeta: () => request('GET', '/api/meta'),

    // Export (these are downloaded directly via downloadUrl, not fetched as JSON)
    exportDevicesUrl: () => '/api/export/devices.xlsx',
    exportBandwidthUrl: () => '/api/export/bandwidth.xlsx',
    exportSubnetsUrl: () => '/api/export/subnets.xlsx',
  };
})();
