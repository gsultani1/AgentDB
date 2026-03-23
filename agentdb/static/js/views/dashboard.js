(function() {
  const V = AgentDB.views.dashboard = {};
  const el = () => document.getElementById('view-dashboard');

  V.load = async function() {
    el().innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <h2>Dashboard</h2>
        <div style="display:flex;gap:8px;align-items:center">
          <label style="font-size:12px;color:var(--text2)">Agent:</label>
          <select id="agent-selector" onchange="AgentDB.views.dashboard.load()" style="width:160px"></select>
        </div>
      </div>
      <div class="stats-grid" id="stats-grid"></div>
      <div class="card">
        <h3>System Info</h3>
        <div id="system-info"></div>
      </div>`;

    // Load agents
    const ar = await AgentDB.api('GET', '/api/agents');
    const sel = document.getElementById('agent-selector');
    if (sel) {
      sel.innerHTML = '<option value="">All Agents</option>';
      if (ar.status === 'ok' && ar.data) {
        ar.data.forEach(a => { sel.innerHTML += `<option value="${a.id}">${AgentDB.esc(a.name)}</option>`; });
      }
    }

    // Load stats
    const r = await AgentDB.api('GET', '/api/stats');
    if (r.status !== 'ok') return;
    const d = r.data;
    const items = [
      ['Short-Term', d.short_term_memories, 'stm'],
      ['Midterm', d.midterm_memories, 'mtm'],
      ['Long-Term', d.long_term_memories, 'ltm'],
      ['Entities', d.entities, ''],
      ['Skills', d.skills, ''],
      ['Active Goals', d.active_goals, ''],
      ['Contradictions', d.unresolved_contradictions, 'warn'],
      ['Pending Feedback', d.pending_feedback, 'warn'],
      ['Sessions', d.sessions, ''],
      ['Relations', d.relations, ''],
    ];
    document.getElementById('stats-grid').innerHTML = items.map(([label, value, cls]) =>
      `<div class="stat-card"><div class="value" style="${cls==='warn'&&value>0?'color:var(--yellow)':''}">${value}</div><div class="label">${label}</div></div>`
    ).join('');
    document.getElementById('system-info').innerHTML = `
      <div style="font-size:13px;line-height:2">
        <b>LLM Provider:</b> ${d.llm_provider || 'Not configured'}<br>
        <b>Embedding Model:</b> ${d.embedding_model || 'N/A'}<br>
        <b>File Watcher:</b> ${d.markdown_watch_enabled === 'true' ? '<span class="status ok">Enabled</span>' : '<span class="status closed">Disabled</span>'}
      </div>`;
  };
})();
