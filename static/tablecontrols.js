// ============================================================================
// TABLE CONTROLS -- shared client-side sorting + pagination, reused
// identically by Devices, Bandwidth, and Subnets table views. Everything
// here runs on data already in memory (state.devices etc.) -- no network
// round-trip, so it works exactly the same with the server unreachable.
//
// Usage pattern per view:
//   const tc = TableControls.create('devices'); // namespace key, persists page size per view
//   ... in render(): const { pageRows, controlsHtml } = tc.apply(filteredRows);
//   ... build <thead> headers with tc.sortableHeader('IP', 'IP') per column
//   ... append controlsHtml after the table for the pager
//   ... wire tc.wireHeaders(rerenderFn) and tc.wirePager(rerenderFn) after innerHTML is set
// ============================================================================

const TableControls = (() => {
  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100, 'All'];
  const DEFAULT_PAGE_SIZE = 25;

  function loadPrefs(namespace) {
    try {
      const saved = JSON.parse(localStorage.getItem('tableControls') || '{}');
      return saved[namespace] || {};
    } catch (e) {
      return {};
    }
  }

  function savePrefs(namespace, prefs) {
    try {
      const all = JSON.parse(localStorage.getItem('tableControls') || '{}');
      all[namespace] = prefs;
      localStorage.setItem('tableControls', JSON.stringify(all));
    } catch (e) { /* ignore */ }
  }

  function create(namespace) {
    const saved = loadPrefs(namespace);
    const state = {
      sortKey: saved.sortKey || null,
      sortDir: saved.sortDir || 'asc', // 'asc' | 'desc'
      pageSize: saved.pageSize || DEFAULT_PAGE_SIZE,
      page: 1, // not persisted -- always start at page 1 on a fresh render() call
    };

    function persist() {
      savePrefs(namespace, { sortKey: state.sortKey, sortDir: state.sortDir, pageSize: state.pageSize });
    }

    // Generates a clickable <th> with a sort-direction indicator. `key` is
    // the field name to sort by (supports dot-free top-level keys and a
    // resolver function for computed/nested values like tag cells).
    function sortableHeader(label, key) {
      const active = state.sortKey === key;
      const arrow = active ? (state.sortDir === 'asc' ? ' &#9650;' : ' &#9660;') : '';
      return `<th class="sortable-th" data-sort-key="${escapeHtml(key)}">${escapeHtml(label)}${arrow}</th>`;
    }

    // Applies current sort + pagination to a filtered/searched array and
    // returns the slice to render plus the controls markup. `resolvers`
    // is an optional {key: (row) => value} map for columns whose sort
    // value isn't a plain top-level field (e.g. a tag id, a computed
    // status). Falls back to row[key] when no resolver is given.
    function apply(rows, resolvers = {}) {
      let sorted = rows;
      if (state.sortKey) {
        const resolve = resolvers[state.sortKey] || (r => r[state.sortKey]);
        sorted = [...rows].sort((a, b) => {
          let av = resolve(a), bv = resolve(b);
          av = av === undefined || av === null ? '' : av;
          bv = bv === undefined || bv === null ? '' : bv;
          // Numeric-aware compare (handles plain numbers and numeric strings
          // like IP octets reasonably -- not full IP-aware sort, but better
          // than lexicographic for things like Allocated BW figures).
          const an = Number(av), bn = Number(bv);
          let cmp;
          if (av !== '' && bv !== '' && !Number.isNaN(an) && !Number.isNaN(bn)) {
            cmp = an - bn;
          } else {
            cmp = String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' });
          }
          return state.sortDir === 'asc' ? cmp : -cmp;
        });
      }

      const total = sorted.length;
      const pageSize = state.pageSize === 'All' ? total || 1 : state.pageSize;
      const totalPages = Math.max(1, Math.ceil(total / pageSize));
      if (state.page > totalPages) state.page = totalPages;
      const start = (state.page - 1) * pageSize;
      const pageRows = state.pageSize === 'All' ? sorted : sorted.slice(start, start + pageSize);

      const rangeStart = total === 0 ? 0 : start + 1;
      const rangeEnd = total === 0 ? 0 : Math.min(start + pageRows.length, total);

      const controlsHtml = `
        <div class="table-pagination">
          <div class="pagination-info">
            ${total === 0 ? 'No rows' : `Showing <b>${rangeStart}&ndash;${rangeEnd}</b> of <b>${total}</b>`}
          </div>
          <div class="pagination-controls">
            <label class="page-size-label">
              Rows per page
              <select class="page-size-select">
                ${PAGE_SIZE_OPTIONS.map(opt => `<option value="${opt}"${state.pageSize === opt ? ' selected' : ''}>${opt}</option>`).join('')}
              </select>
            </label>
            <div class="pager-buttons">
              <button class="btn btn-sm btn-ghost" data-page-act="first" ${state.page <= 1 ? 'disabled' : ''}>&laquo;</button>
              <button class="btn btn-sm btn-ghost" data-page-act="prev" ${state.page <= 1 ? 'disabled' : ''}>&lsaquo;</button>
              <span class="page-indicator">Page ${state.page} of ${totalPages}</span>
              <button class="btn btn-sm btn-ghost" data-page-act="next" ${state.page >= totalPages ? 'disabled' : ''}>&rsaquo;</button>
              <button class="btn btn-sm btn-ghost" data-page-act="last" ${state.page >= totalPages ? 'disabled' : ''}>&raquo;</button>
            </div>
          </div>
        </div>
      `;

      return { pageRows, controlsHtml, total, totalPages };
    }

    // Wires up click handlers on every [data-sort-key] header within
    // `container`. Clicking the active column flips direction; clicking a
    // new column sorts ascending. Resets to page 1 on any sort change.
    function wireHeaders(container, onChange) {
      container.querySelectorAll('[data-sort-key]').forEach(th => {
        th.addEventListener('click', () => {
          const key = th.dataset.sortKey;
          if (state.sortKey === key) {
            state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
          } else {
            state.sortKey = key;
            state.sortDir = 'asc';
          }
          state.page = 1;
          persist();
          onChange();
        });
      });
    }

    // Wires up the page-size select and prev/next/first/last buttons
    // within `container`.
    function wirePager(container, onChange) {
      const select = container.querySelector('.page-size-select');
      if (select) {
        select.addEventListener('change', () => {
          const v = select.value;
          state.pageSize = v === 'All' ? 'All' : parseInt(v, 10);
          state.page = 1;
          persist();
          onChange();
        });
      }
      container.querySelectorAll('[data-page-act]').forEach(btn => {
        btn.addEventListener('click', () => {
          const totalPages = parseInt(container.querySelector('.page-indicator')?.textContent.match(/of (\d+)/)?.[1] || '1', 10);
          if (btn.dataset.pageAct === 'first') state.page = 1;
          else if (btn.dataset.pageAct === 'prev') state.page = Math.max(1, state.page - 1);
          else if (btn.dataset.pageAct === 'next') state.page = Math.min(totalPages, state.page + 1);
          else if (btn.dataset.pageAct === 'last') state.page = totalPages;
          onChange();
        });
      });
    }

    // Reset to page 1 -- call this whenever the underlying filtered set
    // changes for a reason other than sort/page-size (e.g. a new search
    // query), so the person doesn't land on an empty page 4 of a
    // 1-row search result.
    function resetPage() {
      state.page = 1;
    }

    return { sortableHeader, apply, wireHeaders, wirePager, resetPage, state };
  }

  return { create };
})();
