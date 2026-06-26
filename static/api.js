// ============================================================================
// API — thin wrapper around the backend REST endpoints.
// Every function returns parsed JSON or throws an Error with a readable message.
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
      const msg = (data && (data.error || data.message)) || res.statusText || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  function withActor(body) {
    return Object.assign({}, body, { _actor: getEditorName() });
  }

  return {
    // Devices
    getDevices: () => request('GET', '/api/devices'),
    saveDevice: (device) => request('POST', '/api/devices', withActor(device)),
    deleteDevice: (id) => request('DELETE', `/api/devices/${encodeURIComponent(id)}?_actor=${encodeURIComponent(getEditorName())}`),
    importDevices: (devices, mode) => request('POST', '/api/devices/import', withActor({ devices, mode })),

    // Bandwidth
    getBandwidth: () => request('GET', '/api/bandwidth'),
    saveBandwidth: (row) => request('POST', '/api/bandwidth', withActor(row)),
    deleteBandwidth: (id) => request('DELETE', `/api/bandwidth/${encodeURIComponent(id)}?_actor=${encodeURIComponent(getEditorName())}`),
    importBandwidth: (rows, mode) => request('POST', '/api/bandwidth/import', withActor({ devices: rows, mode })),

    // Lists
    getLists: () => request('GET', '/api/lists'),
    setList: (listName, items) => request('POST', `/api/lists/${encodeURIComponent(listName)}`, withActor({ items })),
    getListUsage: (listName, value) => request('GET', `/api/lists/${encodeURIComponent(listName)}/usage?value=${encodeURIComponent(value)}`),

    // Audit
    getAudit: (limit = 100) => request('GET', `/api/audit?limit=${limit}`),

    // History
    getHistory: (limit = 50) => request('GET', `/api/history?limit=${limit}`),
    getHistoryEntry: (id) => request('GET', `/api/history/${encodeURIComponent(id)}`),

    // Generate
    generate: () => request('POST', '/api/generate', withActor({})),

    // Meta
    getMeta: () => request('GET', '/api/meta'),
  };
})();
