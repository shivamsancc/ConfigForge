// ============================================================================
// TAG FIELDS -- shared rendering/reading logic for the dynamic tag system,
// used identically by Devices, Bandwidth, and Subnets forms. A tag def
// scoped to multiple sections (e.g. "Country" on both devices and subnets)
// renders as a dropdown in every one of those sections, sharing one
// underlying value list.
// ============================================================================

const TagFields = (() => {
  function defsForScope(scope) {
    return state.tagDefs.filter(td => (td.scopes || []).includes(scope));
  }

  // Render the dropdown <div class="field"> blocks for every tag def that
  // applies to this scope. currentTags is the record's own {tagId: value} map.
  function renderFormFields(scope, currentTags) {
    const defs = defsForScope(scope);
    if (defs.length === 0) {
      return `<div class="field-hint">No tags defined for this section yet. Add one from "Manage Tags".</div>`;
    }
    return defs.map(td => `
      <div class="field">
        <label>${escapeHtml(td.name)}</label>
        <select name="tag__${td.id}">
          <option value="">&mdash; none &mdash;</option>
          ${(td.values || []).map(v => `<option value="${escapeHtml(v)}"${(currentTags || {})[td.id] === v ? ' selected' : ''}>${escapeHtml(v)}</option>`).join('')}
        </select>
      </div>
    `).join('');
  }

  // Read tag__<id> fields back out of a submitted FormData into a clean
  // {tagId: value} object, omitting empty selections entirely (per the
  // "empty tags don't get written anywhere" rule).
  function readFormFields(formData) {
    const tags = {};
    for (const [key, value] of formData.entries()) {
      if (key.startsWith('tag__') && value) {
        tags[key.slice(5)] = value;
      }
    }
    return tags;
  }

  // Render small read-only badges for a record's resolved tags (used in
  // table/card views). Pass resolvedTags as {tagName: value} (already
  // resolved server-side at generate time) OR rawTags as {tagId: value}
  // plus the defs list to map id->name client-side for display purposes.
  function renderBadges(scope, rawTags) {
    const defs = defsForScope(scope);
    const entries = defs
      .map(td => [td.name, (rawTags || {})[td.id]])
      .filter(([, v]) => !!v);
    if (entries.length === 0) return '';
    return entries.map(([name, value]) => `<span class="badge badge-violet">${escapeHtml(name)}: ${escapeHtml(value)}</span>`).join(' ');
  }

  // During import, a spreadsheet may contain tag values that don't exist
  // yet in the tag definition's value list (e.g. someone typed a new
  // country directly into the sheet). Without registering those values
  // back into the tag def, the value is stored on the record but won't
  // appear as a selectable option in the edit form's dropdown -- it's
  // there, just invisible/unselectable until someone adds it manually.
  // This call collects every new value actually used during an import
  // batch and persists them onto the relevant tag defs in one pass per
  // tag (not one API call per row).
  async function registerNewValuesFromImport(scope, records) {
    const defs = defsForScope(scope);
    if (defs.length === 0) return;
    const additions = new Map(); // tagId -> Set of new values
    for (const rec of records) {
      for (const td of defs) {
        const v = (rec.tags || {})[td.id];
        if (v && !(td.values || []).includes(v)) {
          if (!additions.has(td.id)) additions.set(td.id, new Set());
          additions.get(td.id).add(v);
        }
      }
    }
    for (const [tagId, newValues] of additions.entries()) {
      const td = defs.find(t => t.id === tagId);
      const updated = Object.assign({}, td, { values: [...(td.values || []), ...newValues] });
      try {
        const saved = await Api.saveTag(updated);
        const fresh = saved.tagDef || saved;
        const idx = state.tagDefs.findIndex(t => t.id === fresh.id);
        if (idx >= 0) state.tagDefs[idx] = fresh;
      } catch (e) {
        // Non-fatal: the value is still correctly stored on the imported
        // records even if registering it into the dropdown list fails.
        console.error('Failed to register new tag value(s) from import', e);
      }
    }
  }

  return { defsForScope, renderFormFields, readFormFields, renderBadges, registerNewValuesFromImport };
})();
