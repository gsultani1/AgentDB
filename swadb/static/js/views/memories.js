(function() {
  const V = swadb.views.memories = {};
  const el = () => document.getElementById('view-memories');
  let currentTier = 'short';

  // Selection state — Set of memory IDs. Survives re-renders so switching
  // search/filter doesn't drop the user's pick. Cleared on tier change
  // (different tier = different table = different IDs).
  V._selected = new Set();
  V._lastMemories = [];

  const TIERS = [
    { key: 'short', label: 'Short-Term', badge: 'short_term', table: 'short_term_memory' },
    { key: 'mid',   label: 'Midterm',   badge: 'midterm',     table: 'midterm_memory' },
    { key: 'long',  label: 'Long-Term', badge: 'long_term',   table: 'long_term_memory' }
  ];

  function tierForKey(k) { return TIERS.find(t => t.key === k); }

  const CATEGORIES = [
    'fact', 'relationship', 'preference', 'procedure',
    'identity', 'directive', 'observation', 'pattern'
  ];

  const SOURCES = ['conversation', 'tool_output', 'markdown_authored'];

  function tierBadge(tier) {
    const map = { short_term: 'stm', midterm: 'mtm', long_term: 'ltm', short: 'stm', mid: 'mtm', long: 'ltm' };
    return `<span class="tier ${map[tier] || ''}">${tier.replace('_', ' ')}</span>`;
  }

  V.load = async function() {
    el().innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2>Memories</h2>
        <button class="btn" id="mem-toggle-create">+ New Memory</button>
      </div>

      <div class="tabs" id="mem-tier-tabs" style="margin-bottom:16px">
        ${TIERS.map(t => `<button class="tab${t.key === currentTier ? ' active' : ''}" data-tier="${t.key}">${t.label}</button>`).join('')}
      </div>

      <div id="mem-create-form" style="display:none;margin-bottom:16px" class="card">
        <h3>Create Memory</h3>
        <div style="display:flex;flex-direction:column;gap:10px;margin-top:10px">
          <textarea id="mem-content" rows="3" placeholder="Memory content..." style="width:100%;resize:vertical"></textarea>
          <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
            <select id="mem-category">
              ${CATEGORIES.map(c => `<option value="${c}">${c}</option>`).join('')}
            </select>
            <select id="mem-source">
              ${SOURCES.map(s => `<option value="${s}">${s.replace('_', ' ')}</option>`).join('')}
            </select>
            <label style="font-size:12px;color:var(--text2)">Confidence:</label>
            <input type="number" id="mem-confidence" min="0" max="1" step="0.1" value="0.8" style="width:70px">
            <button class="btn" id="mem-submit-create">Create</button>
          </div>
        </div>
      </div>

      <div style="margin-bottom:16px;display:flex;gap:8px">
        <input type="text" id="mem-search-input" placeholder="Semantic search..." style="flex:1">
        <button class="btn" id="mem-search-btn">Search</button>
        <button class="btn" id="mem-clear-btn" style="display:none">Clear</button>
      </div>

      <!-- Batch action bar — sticky to top once any row is selected -->
      <div id="mem-batch-bar" style="display:none;background:var(--accentLight);border:1px solid var(--accent);border-radius:6px;padding:10px 14px;margin-bottom:12px;align-items:center;gap:10px">
        <span id="mem-batch-count" style="font-weight:600">0 selected</span>
        <span style="flex:1"></span>
        <button class="btn btn-sm" id="mem-batch-pin">Pin</button>
        <button class="btn btn-sm" id="mem-batch-tag">Tag…</button>
        <button class="btn btn-sm" id="mem-batch-promote">Promote</button>
        <button class="btn btn-sm" id="mem-batch-export">Export JSON</button>
        <button class="btn btn-sm" id="mem-batch-delete" style="color:var(--red)">Delete</button>
        <button class="btn btn-sm" id="mem-batch-clear">Clear</button>
      </div>

      <div id="mem-table-wrap"></div>`;

    wireEvents();
    await loadMemories();
  };

  function wireEvents() {
    // Tier tabs — clearing selection when tier changes since rows belong to a different table
    document.getElementById('mem-tier-tabs').addEventListener('click', function(e) {
      const btn = e.target.closest('[data-tier]');
      if (!btn) return;
      currentTier = btn.dataset.tier;
      V._selected.clear();
      document.querySelectorAll('#mem-tier-tabs .tab').forEach(t => t.classList.toggle('active', t.dataset.tier === currentTier));
      loadMemories();
    });

    document.getElementById('mem-toggle-create').addEventListener('click', function() {
      const form = document.getElementById('mem-create-form');
      form.style.display = form.style.display === 'none' ? 'block' : 'none';
    });

    document.getElementById('mem-submit-create').addEventListener('click', createMemory);

    document.getElementById('mem-search-btn').addEventListener('click', doSearch);
    document.getElementById('mem-search-input').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') doSearch();
    });
    document.getElementById('mem-clear-btn').addEventListener('click', function() {
      document.getElementById('mem-search-input').value = '';
      document.getElementById('mem-clear-btn').style.display = 'none';
      loadMemories();
    });

    // Delegated table events: checkbox toggle, row expand, single-row delete
    document.getElementById('mem-table-wrap').addEventListener('click', function(e) {
      const cb = e.target.closest('input.mem-row-cb, input.mem-select-all');
      if (cb) {
        if (cb.classList.contains('mem-select-all')) {
          // toggle all
          document.querySelectorAll('input.mem-row-cb').forEach(function(b) {
            b.checked = cb.checked;
            if (cb.checked) V._selected.add(b.dataset.id);
            else V._selected.delete(b.dataset.id);
          });
        } else {
          if (cb.checked) V._selected.add(cb.dataset.id);
          else V._selected.delete(cb.dataset.id);
        }
        renderBatchBar();
        // Don't expand the row when clicking the checkbox
        e.stopPropagation();
        return;
      }
      const delBtn = e.target.closest('.mem-delete-btn');
      if (delBtn) {
        e.stopPropagation();
        deleteMemory(delBtn.dataset.tier, delBtn.dataset.id);
        return;
      }
      const row = e.target.closest('.mem-row');
      if (row) toggleExpand(row);
    });

    // Batch bar actions
    document.getElementById('mem-batch-pin').addEventListener('click', batchPin);
    document.getElementById('mem-batch-tag').addEventListener('click', batchTag);
    document.getElementById('mem-batch-promote').addEventListener('click', batchPromote);
    document.getElementById('mem-batch-export').addEventListener('click', batchExport);
    document.getElementById('mem-batch-delete').addEventListener('click', batchDelete);
    document.getElementById('mem-batch-clear').addEventListener('click', function() {
      V._selected.clear();
      document.querySelectorAll('input.mem-row-cb, input.mem-select-all').forEach(function(b) {
        b.checked = false;
      });
      renderBatchBar();
    });
  }

  async function loadMemories() {
    const r = await swadb.api('GET', `/api/memories/${currentTier}`);
    if (r.status !== 'ok') {
      document.getElementById('mem-table-wrap').innerHTML = '<p style="color:var(--text2)">Failed to load memories.</p>';
      return;
    }
    V._lastMemories = r.data || [];
    renderTable(V._lastMemories);
  }

  async function doSearch() {
    const query = document.getElementById('mem-search-input').value.trim();
    if (!query) return;
    document.getElementById('mem-clear-btn').style.display = 'inline-block';
    const r = await swadb.api('POST', '/api/memories/search', {
      query: query,
      tiers: [currentTier],
      limit: 20
    });
    if (r.status !== 'ok') {
      document.getElementById('mem-table-wrap').innerHTML = '<p style="color:var(--text2)">Search failed.</p>';
      return;
    }
    V._lastMemories = r.data || [];
    renderTable(V._lastMemories);
  }

  function renderTable(memories) {
    if (!memories.length) {
      document.getElementById('mem-table-wrap').innerHTML = '<p style="color:var(--text2)">No memories found.</p>';
      renderBatchBar();
      return;
    }

    const isSTM = currentTier === 'short';
    const allChecked = memories.length > 0 && memories.every(m => V._selected.has(m.id));
    const headers = `
      <tr>
        <th style="width:32px"><input type="checkbox" class="mem-select-all" ${allChecked ? 'checked' : ''} title="Select all"></th>
        <th style="width:90px">ID</th>
        <th>Content</th>
        ${isSTM ? '' : '<th style="width:90px">Confidence</th>'}
        <th style="width:110px">Category</th>
        <th style="width:130px">Created</th>
        <th style="width:60px"></th>
      </tr>`;

    const rows = memories.map(m => {
      const id = (m.id || '').substring(0, 8);
      const content = swadb.truncate(swadb.esc(m.content || ''), 100);
      const created = swadb.formatDate(m.created_at || '').substring(0, 16);
      const cat = m.category || '';
      const tier = m.tier || currentTier;
      const checked = V._selected.has(m.id) ? 'checked' : '';
      const cols = isSTM ? 6 : 7;

      return `
        <tr class="mem-row" data-id="${swadb.esc(m.id)}" data-tier="${tier}">
          <td><input type="checkbox" class="mem-row-cb" data-id="${swadb.esc(m.id)}" ${checked}></td>
          <td><code style="font-size:11px">${swadb.esc(id)}</code></td>
          <td>${content}</td>
          ${isSTM ? '' : `<td>${m.confidence != null ? m.confidence : ''}</td>`}
          <td>${tierBadge(tier)} <span style="font-size:11px;color:var(--text2)">${swadb.esc(cat)}</span></td>
          <td style="font-size:12px;color:var(--text2)">${created}</td>
          <td><button class="btn mem-delete-btn" data-id="${swadb.esc(m.id)}" data-tier="${tier}" style="padding:2px 8px;font-size:11px;background:var(--red,#e74c3c);color:#fff">Del</button></td>
        </tr>
        <tr class="mem-expand" data-expand-for="${swadb.esc(m.id)}" style="display:none">
          <td colspan="${cols}" style="padding:12px;background:var(--bg2,#1a1a2e);font-size:12px;line-height:1.6">
            <b>Full ID:</b> <code>${swadb.esc(m.id || '')}</code><br>
            <b>Agent:</b> ${swadb.esc(m.agent_id || 'N/A')}<br>
            <b>Source:</b> ${swadb.esc(m.source || 'N/A')}<br>
            ${m.confidence != null ? `<b>Confidence:</b> ${m.confidence}<br>` : ''}
            <b>Content:</b><br>
            <div style="white-space:pre-wrap;margin-top:4px;padding:8px;background:var(--bg,#0f0f23);border-radius:4px">${swadb.esc(m.content || '')}</div>
          </td>
        </tr>`;
    }).join('');

    document.getElementById('mem-table-wrap').innerHTML = `
      <table>
        <thead>${headers}</thead>
        <tbody>${rows}</tbody>
      </table>`;
    renderBatchBar();
  }

  function renderBatchBar() {
    const bar = document.getElementById('mem-batch-bar');
    const n = V._selected.size;
    bar.style.display = n > 0 ? 'flex' : 'none';
    if (n === 0) return;
    document.getElementById('mem-batch-count').textContent =
      n + ' selected' + (currentTier === 'long' ? '' : '');
    // Promote disabled on LTM (nowhere to promote to)
    const promoteBtn = document.getElementById('mem-batch-promote');
    if (currentTier === 'long') {
      promoteBtn.disabled = true;
      promoteBtn.title = 'Long-term memories cannot be promoted further';
      promoteBtn.style.opacity = '0.5';
    } else {
      promoteBtn.disabled = false;
      promoteBtn.title = 'Promote selected to ' + (currentTier === 'short' ? 'midterm' : 'long-term');
      promoteBtn.style.opacity = '1';
    }
  }

  function selectedIds() {
    return Array.from(V._selected);
  }

  function selectedTable() {
    return tierForKey(currentTier).table;
  }

  function selectedMemories() {
    return V._lastMemories.filter(m => V._selected.has(m.id));
  }

  // ── Batch actions ──────────────────────────────────────────────────
  async function batchPin() {
    const ids = selectedIds();
    if (!ids.length) return;
    const r = await swadb.api('POST', '/api/memories/batch/pin', {
      ids: ids, memory_table: selectedTable()
    });
    if (r.status === 'ok') {
      swadb.toast('Pinned ' + (r.data && r.data.pinned ? r.data.pinned : ids.length) + ' memories', 'success');
      V._selected.clear();
      renderBatchBar();
    } else {
      swadb.toast('Pin failed: ' + (r.error || 'unknown'), 'error');
    }
  }

  async function batchTag() {
    const ids = selectedIds();
    if (!ids.length) return;
    const tagName = prompt('Tag name to apply to ' + ids.length + ' memor' +
                            (ids.length === 1 ? 'y' : 'ies') + ':');
    if (!tagName || !tagName.trim()) return;
    const r = await swadb.api('POST', '/api/memories/batch/tag', {
      ids: ids, target_table: selectedTable(), tag_name: tagName.trim()
    });
    if (r.status === 'ok') {
      swadb.toast('Tagged ' + ids.length + ' memories with ' + tagName.trim(), 'success');
      V._selected.clear();
      await loadMemories();
    } else {
      swadb.toast('Tag failed: ' + (r.error || 'unknown'), 'error');
    }
  }

  async function batchPromote() {
    const ids = selectedIds();
    if (!ids.length) return;
    if (currentTier === 'long') {
      swadb.toast('Long-term memories cannot be promoted further', 'error');
      return;
    }
    const target = currentTier === 'short' ? 'midterm' : 'long-term';
    if (!confirm('Promote ' + ids.length + ' memor' + (ids.length === 1 ? 'y' : 'ies') +
                 ' to ' + target + '? They will be moved out of the current tier.')) return;
    const r = await swadb.api('POST', '/api/memories/batch/promote', {
      ids: ids, source_table: selectedTable()
    });
    if (r.status === 'ok') {
      const promoted = (r.data && r.data.promoted) || ids.length;
      swadb.toast('Promoted ' + promoted + ' memories to ' + target, 'success');
      V._selected.clear();
      await loadMemories();
    } else {
      swadb.toast('Promote failed: ' + (r.error || 'unknown'), 'error');
    }
  }

  function batchExport() {
    const memories = selectedMemories();
    if (!memories.length) return;
    const blob = new Blob([JSON.stringify(memories, null, 2)],
                          { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'memories-' + currentTier + '-' + new Date().toISOString().slice(0, 10) + '.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function() { URL.revokeObjectURL(url); }, 0);
    swadb.toast('Exported ' + memories.length + ' memories', 'success');
  }

  async function batchDelete() {
    const ids = selectedIds();
    if (!ids.length) return;
    if (!confirm('Delete ' + ids.length + ' memor' + (ids.length === 1 ? 'y' : 'ies') +
                 '? This cannot be undone.')) return;
    const r = await swadb.api('POST', '/api/memories/batch/delete', {
      ids: ids, memory_table: selectedTable()
    });
    if (r.status === 'ok') {
      const deleted = (r.data && r.data.deleted) || ids.length;
      swadb.toast('Deleted ' + deleted + ' memories', 'success');
      V._selected.clear();
      await loadMemories();
    } else {
      swadb.toast('Delete failed: ' + (r.error || 'unknown'), 'error');
    }
  }

  function toggleExpand(row) {
    const id = row.dataset.id;
    const expand = document.querySelector(`[data-expand-for="${id}"]`);
    if (!expand) return;
    expand.style.display = expand.style.display === 'none' ? 'table-row' : 'none';
  }

  async function createMemory() {
    const content = document.getElementById('mem-content').value.trim();
    if (!content) { swadb.toast('Content is required'); return; }

    const body = {
      content: content,
      category: document.getElementById('mem-category').value,
      source: document.getElementById('mem-source').value,
      confidence: parseFloat(document.getElementById('mem-confidence').value) || 0.8
    };

    const r = await swadb.api('POST', `/api/memories/${currentTier}`, body);
    if (r.status === 'ok') {
      swadb.toast('Memory created');
      document.getElementById('mem-content').value = '';
      document.getElementById('mem-create-form').style.display = 'none';
      await loadMemories();
    } else {
      swadb.toast('Failed to create memory: ' + (r.message || 'Unknown error'));
    }
  }

  async function deleteMemory(tier, id) {
    if (!confirm('Delete this memory? This cannot be undone.')) return;
    const r = await swadb.api('DELETE', `/api/memories/${tier}/${id}`);
    if (r.status === 'ok') {
      swadb.toast('Memory deleted');
      V._selected.delete(id);
      await loadMemories();
    } else {
      swadb.toast('Failed to delete memory');
    }
  }
})();
