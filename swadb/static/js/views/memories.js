(function() {
  const V = AgentDB.views.memories = {};
  const el = () => document.getElementById('view-memories');
  let currentTier = 'short';

  const TIERS = [
    { key: 'short', label: 'Short-Term', badge: 'short_term' },
    { key: 'mid', label: 'Midterm', badge: 'midterm' },
    { key: 'long', label: 'Long-Term', badge: 'long_term' }
  ];

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

      <div id="mem-table-wrap"></div>`;

    wireEvents();
    await loadMemories();
  };

  function wireEvents() {
    // Tier tabs
    document.getElementById('mem-tier-tabs').addEventListener('click', function(e) {
      const btn = e.target.closest('[data-tier]');
      if (!btn) return;
      currentTier = btn.dataset.tier;
      document.querySelectorAll('#mem-tier-tabs .tab').forEach(t => t.classList.toggle('active', t.dataset.tier === currentTier));
      loadMemories();
    });

    // Toggle create form
    document.getElementById('mem-toggle-create').addEventListener('click', function() {
      const form = document.getElementById('mem-create-form');
      form.style.display = form.style.display === 'none' ? 'block' : 'none';
    });

    // Submit create
    document.getElementById('mem-submit-create').addEventListener('click', createMemory);

    // Search
    document.getElementById('mem-search-btn').addEventListener('click', doSearch);
    document.getElementById('mem-search-input').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') doSearch();
    });

    // Clear search
    document.getElementById('mem-clear-btn').addEventListener('click', function() {
      document.getElementById('mem-search-input').value = '';
      document.getElementById('mem-clear-btn').style.display = 'none';
      loadMemories();
    });

    // Delegated events on table
    document.getElementById('mem-table-wrap').addEventListener('click', function(e) {
      const delBtn = e.target.closest('.mem-delete-btn');
      if (delBtn) {
        deleteMemory(delBtn.dataset.tier, delBtn.dataset.id);
        return;
      }
      const row = e.target.closest('.mem-row');
      if (row) toggleExpand(row);
    });
  }

  async function loadMemories() {
    const r = await AgentDB.api('GET', `/api/memories/${currentTier}`);
    if (r.status !== 'ok') {
      document.getElementById('mem-table-wrap').innerHTML = '<p style="color:var(--text2)">Failed to load memories.</p>';
      return;
    }
    renderTable(r.data || []);
  }

  async function doSearch() {
    const query = document.getElementById('mem-search-input').value.trim();
    if (!query) return;
    document.getElementById('mem-clear-btn').style.display = 'inline-block';
    const r = await AgentDB.api('POST', '/api/memories/search', {
      query: query,
      tiers: [currentTier],
      limit: 20
    });
    if (r.status !== 'ok') {
      document.getElementById('mem-table-wrap').innerHTML = '<p style="color:var(--text2)">Search failed.</p>';
      return;
    }
    renderTable(r.data || []);
  }

  function renderTable(memories) {
    if (!memories.length) {
      document.getElementById('mem-table-wrap').innerHTML = '<p style="color:var(--text2)">No memories found.</p>';
      return;
    }

    const isSTM = currentTier === 'short';
    const headers = `
      <tr>
        <th style="width:90px">ID</th>
        <th>Content</th>
        ${isSTM ? '' : '<th style="width:90px">Confidence</th>'}
        <th style="width:110px">Category</th>
        <th style="width:130px">Created</th>
        <th style="width:60px"></th>
      </tr>`;

    const rows = memories.map(m => {
      const id = (m.id || '').substring(0, 8);
      const content = AgentDB.truncate(AgentDB.esc(m.content || ''), 100);
      const created = AgentDB.formatDate(m.created_at || '').substring(0, 16);
      const cat = m.category || '';
      const tier = m.tier || currentTier;

      return `
        <tr class="mem-row" data-id="${AgentDB.esc(m.id)}" data-tier="${tier}">
          <td><code style="font-size:11px">${AgentDB.esc(id)}</code></td>
          <td>${content}</td>
          ${isSTM ? '' : `<td>${m.confidence != null ? m.confidence : ''}</td>`}
          <td>${tierBadge(tier)} <span style="font-size:11px;color:var(--text2)">${AgentDB.esc(cat)}</span></td>
          <td style="font-size:12px;color:var(--text2)">${created}</td>
          <td><button class="btn mem-delete-btn" data-id="${AgentDB.esc(m.id)}" data-tier="${tier}" style="padding:2px 8px;font-size:11px;background:var(--red,#e74c3c);color:#fff">Del</button></td>
        </tr>
        <tr class="mem-expand" data-expand-for="${AgentDB.esc(m.id)}" style="display:none">
          <td colspan="${isSTM ? 5 : 6}" style="padding:12px;background:var(--bg2,#1a1a2e);font-size:12px;line-height:1.6">
            <b>Full ID:</b> <code>${AgentDB.esc(m.id || '')}</code><br>
            <b>Agent:</b> ${AgentDB.esc(m.agent_id || 'N/A')}<br>
            <b>Source:</b> ${AgentDB.esc(m.source || 'N/A')}<br>
            ${m.confidence != null ? `<b>Confidence:</b> ${m.confidence}<br>` : ''}
            <b>Content:</b><br>
            <div style="white-space:pre-wrap;margin-top:4px;padding:8px;background:var(--bg,#0f0f23);border-radius:4px">${AgentDB.esc(m.content || '')}</div>
          </td>
        </tr>`;
    }).join('');

    document.getElementById('mem-table-wrap').innerHTML = `
      <table>
        <thead>${headers}</thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function toggleExpand(row) {
    const id = row.dataset.id;
    const expand = document.querySelector(`[data-expand-for="${id}"]`);
    if (!expand) return;
    expand.style.display = expand.style.display === 'none' ? 'table-row' : 'none';
  }

  async function createMemory() {
    const content = document.getElementById('mem-content').value.trim();
    if (!content) { AgentDB.toast('Content is required'); return; }

    const body = {
      content: content,
      category: document.getElementById('mem-category').value,
      source: document.getElementById('mem-source').value,
      confidence: parseFloat(document.getElementById('mem-confidence').value) || 0.8
    };

    const r = await AgentDB.api('POST', `/api/memories/${currentTier}`, body);
    if (r.status === 'ok') {
      AgentDB.toast('Memory created');
      document.getElementById('mem-content').value = '';
      document.getElementById('mem-create-form').style.display = 'none';
      await loadMemories();
    } else {
      AgentDB.toast('Failed to create memory: ' + (r.message || 'Unknown error'));
    }
  }

  async function deleteMemory(tier, id) {
    if (!await AgentDB.confirm('Delete this memory? This cannot be undone.')) return;
    const r = await AgentDB.api('DELETE', `/api/memories/${tier}/${id}`);
    if (r.status === 'ok') {
      AgentDB.toast('Memory deleted');
      await loadMemories();
    } else {
      AgentDB.toast('Failed to delete memory');
    }
  }
})();
