(function() {
  const V = AgentDB.views.settings = {};
  const el = () => document.getElementById('view-settings');

  const SETTINGS_SCHEMA = {
    "Agent API": [
      { key: 'agent_api_key', label: 'Agent API Key', type: 'agent_key_gen', fullWidth: true, hint: 'External AI agents must include this in the X-API-Key header. Leave blank for open access.' },
    ],
    "Memory & Consolidation": [
      { key: 'consolidation_enabled', label: 'Enable Consolidation', type: 'toggle', hint: 'Automatically promote and consolidate memories' },
      { key: 'consolidation_interval_seconds', label: 'Consolidation Interval (s)', type: 'number', min: 30, hint: 'Seconds between consolidation cycles' },
      { key: 'decay_enabled', label: 'Enable Decay', type: 'toggle', hint: 'Apply decay to memory relevance over time' },
      { key: 'decay_rate_multiplier', label: 'Decay Rate Multiplier', type: 'number', min: 0, max: 10, step: 0.1, hint: 'Speed of memory decay (1.0 = normal)' },
      { key: 'stm_default_ttl_seconds', label: 'STM Default TTL (s)', type: 'number', min: 60, hint: 'Time-to-live for short-term memories before expiry' },
      { key: 'promotion_confidence_threshold', label: 'Promotion Confidence', type: 'number', min: 0, max: 1, step: 0.05, hint: 'Minimum confidence score to promote STM to midterm' },
      { key: 'staleness_threshold_days', label: 'Staleness Threshold (days)', type: 'number', min: 1, hint: 'Days before a memory is considered stale' },
    ],
    "Search & Retrieval": [
      { key: 'clustering_similarity_threshold', label: 'Clustering Similarity', type: 'number', min: 0, max: 1, step: 0.05, hint: 'Cosine similarity threshold for memory clustering' },
      { key: 'goal_similarity_threshold', label: 'Goal Similarity', type: 'number', min: 0, max: 1, step: 0.05, hint: 'Minimum similarity to match goals' },
      { key: 'skill_similarity_threshold', label: 'Skill Similarity', type: 'number', min: 0, max: 1, step: 0.05, hint: 'Minimum similarity to match skills' },
      { key: 'context_results_per_tier', label: 'Results Per Tier', type: 'number', min: 1, max: 100, hint: 'Max results to return from each memory tier' },
      { key: 'bm25_enabled', label: 'BM25 Search', type: 'toggle', hint: 'Enable keyword-based BM25 search alongside semantic search' },
      { key: 'graph_traversal_enabled', label: 'Graph Traversal', type: 'toggle', hint: 'Enable knowledge graph traversal for context retrieval' },
      { key: 'temporal_boost_enabled', label: 'Temporal Boost', type: 'toggle', hint: 'Boost recent memories in search results' },
      { key: 'temporal_decay_curve', label: 'Temporal Decay Curve', type: 'number', min: 0, max: 1, step: 0.05, hint: 'How quickly temporal boost decreases (0=fast, 1=slow)' },
    ],
    "Embedding": [
      { key: 'embedding_model', label: 'Embedding Model', type: 'text', hint: 'Model used for generating embeddings' },
      { key: 'embedding_dimensions', label: 'Dimensions', type: 'number', hint: 'Dimensionality of embedding vectors' },
      { key: 'reranker_enabled', label: 'Enable Reranker', type: 'toggle', hint: 'Use a reranker model for improved result ordering' },
      { key: 'reranker_model', label: 'Reranker Model', type: 'text', hint: 'Model name for reranking search results' },
    ],
    "Markdown": [
      { key: 'markdown_inbox_path', label: 'Inbox Path', type: 'text', fullWidth: true, hint: 'Directory path for markdown inbox files' },
      { key: 'markdown_watch_enabled', label: 'Watch Enabled', type: 'toggle', hint: 'Automatically watch inbox for new markdown files' },
      { key: 'markdown_watch_interval_seconds', label: 'Watch Interval (s)', type: 'number', min: 1, hint: 'Seconds between inbox directory scans' },
    ],
    "Notifications": [
      { key: 'notification_webhook_url', label: 'Webhook URL', type: 'text', fullWidth: true, hint: 'URL to POST notification payloads to' },
      { key: 'notification_priority_threshold', label: 'Priority Threshold', type: 'select', options: ['low','medium','high','critical'], hint: 'Minimum priority level to trigger notifications' },
    ],
    "Sleep & Security": [
      { key: 'sleep_idle_threshold_seconds', label: 'Idle Threshold (s)', type: 'number', hint: 'Seconds of inactivity before entering sleep mode' },
      { key: 'sleep_reflection_enabled', label: 'Sleep Reflection', type: 'toggle', hint: 'Generate reflection summaries during sleep cycles' },
      { key: 'sleep_graph_pruning_threshold_days', label: 'Graph Pruning (days)', type: 'number', hint: 'Days before pruning unused graph edges during sleep' },
    ],
  };

  var configMap = {};

  V.load = async function() {
    var r = await AgentDB.api('GET', '/api/config');
    configMap = {};
    if (r.status === 'ok' && r.data) {
      r.data.forEach(function(c) { configMap[c.key] = c.value; });
    }

    var html = '<h2 style="margin-bottom:16px">Settings</h2>';

    // AI Providers section (dynamic from llm_providers table)
    html += '<div class="card" style="margin-bottom:16px"><h3>AI Providers</h3>';
    html += '<p style="font-size:12px;color:var(--text2);margin-bottom:12px">Configure multiple AI providers. The default provider is used for chat and consolidation.</p>';
    html += '<div id="providers-list"></div>';
    html += '<button class="btn" style="margin-top:12px" id="add-provider-btn">+ Add Provider</button>';
    html += '<div id="add-provider-form" style="display:none;margin-top:12px;padding:16px;background:var(--bg3);border-radius:var(--radius)">';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">';
    html += '<div><label style="font-size:12px;color:var(--text2)">Name</label><input type="text" id="prov-name" placeholder="My Claude" style="width:100%"></div>';
    html += '<div><label style="font-size:12px;color:var(--text2)">Type</label><select id="prov-type" style="width:100%"><option value="claude">Claude</option><option value="openai">OpenAI</option><option value="local">Local</option></select></div>';
    html += '<div><label style="font-size:12px;color:var(--text2)">Model</label><input type="text" id="prov-model" placeholder="claude-sonnet-4-20250514" style="width:100%"></div>';
    html += '<div><label style="font-size:12px;color:var(--text2)">API Key</label><input type="password" id="prov-key" placeholder="sk-..." style="width:100%"></div>';
    html += '<div style="grid-column:1/-1"><label style="font-size:12px;color:var(--text2)">Endpoint (optional)</label><input type="text" id="prov-endpoint" placeholder="Leave blank for default" style="width:100%"></div>';
    html += '</div>';
    html += '<div style="display:flex;gap:8px;margin-top:10px"><button class="btn btn-primary" id="save-provider-btn">Save Provider</button><button class="btn" id="cancel-provider-btn">Cancel</button></div>';
    html += '</div></div>';

    // Max context tokens (kept from old LLM section)
    html += '<div class="card" style="margin-bottom:16px"><h3>Context Settings</h3>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;margin-top:12px">';
    var mctVal = configMap['max_context_tokens'] || '4000';
    html += '<div><label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px">Max Context Tokens</label>';
    html += '<input type="number" id="cfg-max_context_tokens" value="' + AgentDB.esc(mctVal) + '" min="500" max="128000" style="width:100%" onchange="AgentDB.views.settings.saveConfig(\'max_context_tokens\')">';
    html += '<div style="font-size:11px;color:var(--text2);margin-top:2px">Maximum tokens for context window</div></div>';
    html += '</div></div>';

    Object.keys(SETTINGS_SCHEMA).forEach(function(section) {
      html += '<div class="card" style="margin-bottom:16px"><h3>' + AgentDB.esc(section) + '</h3>';
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;margin-top:12px">';

      SETTINGS_SCHEMA[section].forEach(function(f) {
        var val = configMap[f.key] || '';
        var fullW = f.fullWidth ? 'style="grid-column:1/-1"' : '';
        html += '<div ' + fullW + '>';
        html += '<label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px">' + AgentDB.esc(f.label) + '</label>';

        if (f.type === 'toggle') {
          var checked = val === 'true' || val === '1' ? ' checked' : '';
          html += '<label class="setting-toggle"><input type="checkbox" id="cfg-' + f.key + '"' + checked +
            ' onchange="AgentDB.views.settings.saveConfig(\'' + f.key + '\')"><span class="slider"></span></label>';
        } else if (f.type === 'select') {
          html += '<select id="cfg-' + f.key + '" onchange="AgentDB.views.settings.saveConfig(\'' + f.key + '\')" style="width:100%">';
          f.options.forEach(function(o) {
            html += '<option value="' + o + '"' + (val === o ? ' selected' : '') + '>' + o + '</option>';
          });
          html += '</select>';
        } else if (f.type === 'agent_key_gen') {
          html += '<div style="display:flex;gap:8px;align-items:center">';
          html += '<input type="text" id="cfg-' + f.key + '" value="' + AgentDB.esc(val) + '" style="flex:1;font-family:var(--mono);font-size:12px" readonly>';
          html += '<button class="btn btn-sm" onclick="AgentDB.views.settings.generateApiKey(\'' + f.key + '\')">Generate</button>';
          html += '<button class="btn btn-sm" onclick="AgentDB.copyToClipboard(document.getElementById(\'cfg-' + f.key + '\').value)">Copy</button>';
          html += '<button class="btn btn-sm" style="color:var(--red)" onclick="AgentDB.views.settings.clearApiKey(\'' + f.key + '\')">Clear</button>';
          html += '</div>';
        } else if (f.type === 'password') {
          html += '<input type="password" id="cfg-' + f.key + '" value="' + AgentDB.esc(val) + '" style="width:100%" ' +
            'onchange="AgentDB.views.settings.saveConfig(\'' + f.key + '\')">';
        } else if (f.type === 'number') {
          var attrs = '';
          if (f.min !== undefined) attrs += ' min="' + f.min + '"';
          if (f.max !== undefined) attrs += ' max="' + f.max + '"';
          if (f.step !== undefined) attrs += ' step="' + f.step + '"';
          html += '<input type="number" id="cfg-' + f.key + '" value="' + AgentDB.esc(val) + '" style="width:100%"' + attrs +
            ' onchange="AgentDB.views.settings.saveConfig(\'' + f.key + '\')">';
        } else {
          html += '<input type="text" id="cfg-' + f.key + '" value="' + AgentDB.esc(val) + '" style="width:100%" ' +
            'onchange="AgentDB.views.settings.saveConfig(\'' + f.key + '\')">';
        }

        if (f.hint) html += '<div style="font-size:11px;color:var(--text2);margin-top:2px">' + AgentDB.esc(f.hint) + '</div>';
        html += '</div>';
      });

      html += '</div></div>';
    });

    // Local System Access (loaded async after render)
    html += '<div class="card" style="margin-bottom:16px"><h3>Local System Access</h3>';
    html += '<p style="font-size:12px;color:var(--text2);margin-bottom:12px">Grant agents read or read/write access to specific directories. Optionally allow shell command execution.</p>';
    html += '<div id="lsa-panel"><div style="color:var(--text2);font-size:13px">Loading…</div></div>';
    html += '</div>';

    // Workspaces section (loaded async after render)
    html += '<div class="card" style="margin-bottom:16px"><h3>Workspaces</h3>';
    html += '<p style="font-size:12px;color:var(--text2);margin-bottom:12px">Register code or document directories to be scanned and indexed alongside agent memory.</p>';
    html += '<div id="workspaces-panel"><div style="color:var(--text2);font-size:13px">Loading…</div></div>';
    html += '<div id="add-workspace-form" style="display:none;margin-top:12px;padding:12px;background:var(--bg3);border-radius:6px">';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">';
    html += '<div><label style="font-size:12px;color:var(--text2)">Name</label><input type="text" id="ws-name" placeholder="My Project" style="width:100%"></div>';
    html += '<div><label style="font-size:12px;color:var(--text2)">Type</label><select id="ws-type" style="width:100%"><option value="codebase">Codebase</option><option value="project_folder" selected>Project Folder</option><option value="data_directory">Data Directory</option></select></div>';
    html += '<div style="grid-column:1/-1"><label style="font-size:12px;color:var(--text2)">Root Path (absolute)</label><input type="text" id="ws-path" placeholder="C:\\\\Users\\\\you\\\\projects\\\\foo" style="width:100%;font-family:var(--mono);font-size:12px"></div>';
    html += '</div>';
    html += '<div style="display:flex;gap:8px;margin-top:10px"><button class="btn btn-primary" id="save-workspace-btn">Add Workspace</button><button class="btn" id="cancel-workspace-btn">Cancel</button></div>';
    html += '</div>';
    html += '<button class="btn" style="margin-top:10px" id="show-add-workspace-btn">+ Add Workspace</button>';
    html += '<button class="btn" style="margin-top:10px;margin-left:6px" id="scan-all-workspaces-btn">Scan All</button>';
    html += '</div>';

    // Encryption section (loaded async after render)
    html += '<div class="card" style="margin-bottom:16px"><h3>Encryption</h3>';
    html += '<div id="encryption-panel"><div style="color:var(--text2);font-size:13px">Loading…</div></div>';
    html += '</div>';

    // Maintenance section
    html += '<div class="card" style="margin-bottom:16px"><h3>Maintenance</h3>';
    html += '<div style="display:flex;gap:12px;margin-top:12px">';
    html += '<button class="btn btn-primary" onclick="AgentDB.views.settings.runMaint(\'consolidation\')">Run Consolidation</button>';
    html += '<button class="btn" onclick="AgentDB.views.settings.runMaint(\'integrity_check\')">Integrity Check</button>';
    html += '<button class="btn" onclick="AgentDB.views.settings.runMaint(\'sleep\')">Sleep Cycle</button>';
    html += '</div></div>';

    el().innerHTML = html;

    // Wire provider buttons
    document.getElementById('add-provider-btn').onclick = function() {
      document.getElementById('add-provider-form').style.display = 'block';
    };
    document.getElementById('cancel-provider-btn').onclick = function() {
      document.getElementById('add-provider-form').style.display = 'none';
    };
    document.getElementById('save-provider-btn').onclick = V.createProvider;
    document.getElementById('providers-list').addEventListener('click', function(e) {
      var btn;
      if ((btn = e.target.closest('[data-set-default]'))) {
        V.setDefault(btn.dataset.setDefault);
      } else if ((btn = e.target.closest('[data-del-provider]'))) {
        V.deleteProvider(btn.dataset.delProvider);
      }
    });

    // Wire workspace buttons
    document.getElementById('show-add-workspace-btn').onclick = function() {
      document.getElementById('add-workspace-form').style.display = 'block';
    };
    document.getElementById('cancel-workspace-btn').onclick = function() {
      document.getElementById('add-workspace-form').style.display = 'none';
      document.getElementById('ws-name').value = '';
      document.getElementById('ws-path').value = '';
    };
    document.getElementById('save-workspace-btn').onclick = V.createWorkspace;
    document.getElementById('scan-all-workspaces-btn').onclick = V.scanAllWorkspaces;
    document.getElementById('workspaces-panel').addEventListener('click', function(e) {
      var btn;
      if ((btn = e.target.closest('[data-scan-workspace]'))) {
        V.scanWorkspace(btn.dataset.scanWorkspace);
      } else if ((btn = e.target.closest('[data-del-workspace]'))) {
        V.deleteWorkspace(btn.dataset.delWorkspace);
      }
    });

    // Load providers + workspaces + encryption status + local system access
    V.loadProviders();
    V.loadWorkspaces();
    V.loadEncryption();
    V.loadLocalSystemAccess();
  };

  V.loadProviders = async function() {
    var r = await AgentDB.api('GET', '/api/providers');
    var wrap = document.getElementById('providers-list');
    if (!wrap) return;
    if (r.status !== 'ok' || !r.data || !r.data.length) {
      wrap.innerHTML = '<p style="color:var(--text2);font-size:13px">No providers configured. Add one to get started.</p>';
      return;
    }
    wrap.innerHTML = '<table style="width:100%"><thead><tr><th>Name</th><th>Type</th><th>Model</th><th>API Key</th><th>Default</th><th></th></tr></thead><tbody>' +
      r.data.map(function(p) {
        return '<tr>' +
          '<td><b>' + AgentDB.esc(p.name) + '</b></td>' +
          '<td>' + AgentDB.esc(p.provider_type) + '</td>' +
          '<td style="font-family:var(--mono);font-size:12px">' + AgentDB.esc(p.model) + '</td>' +
          '<td style="font-size:12px;color:var(--text2)">' + AgentDB.esc(p.api_key || '') + '</td>' +
          '<td>' + (p.is_default ? '<span class="status ok">Default</span>' : '<button class="btn btn-sm" data-set-default="' + p.id + '">Set Default</button>') + '</td>' +
          '<td><button class="btn btn-sm" style="color:var(--red)" data-del-provider="' + p.id + '">Delete</button></td>' +
          '</tr>';
      }).join('') + '</tbody></table>';
  };

  V.createProvider = async function() {
    var name = document.getElementById('prov-name').value.trim();
    var model = document.getElementById('prov-model').value.trim();
    if (!name || !model) return AgentDB.toast('Name and model are required', 'error');
    var r = await AgentDB.api('POST', '/api/providers', {
      name: name,
      provider_type: document.getElementById('prov-type').value,
      model: model,
      api_key: document.getElementById('prov-key').value,
      endpoint: document.getElementById('prov-endpoint').value,
      is_default: false
    });
    if (r.status === 'ok' || r.data?.id) {
      AgentDB.toast('Provider added', 'success');
      document.getElementById('add-provider-form').style.display = 'none';
      document.getElementById('prov-name').value = '';
      document.getElementById('prov-model').value = '';
      document.getElementById('prov-key').value = '';
      document.getElementById('prov-endpoint').value = '';
      V.loadProviders();
    } else {
      AgentDB.toast('Error: ' + (r.error || 'Unknown'), 'error');
    }
  };

  V.setDefault = async function(id) {
    await AgentDB.api('PUT', '/api/providers/' + id, { is_default: true });
    AgentDB.toast('Default provider updated', 'success');
    V.loadProviders();
  };

  V.deleteProvider = async function(id) {
    if (!await AgentDB.confirm('Delete this provider?')) return;
    await AgentDB.api('DELETE', '/api/providers/' + id);
    AgentDB.toast('Provider deleted');
    V.loadProviders();
  };

  V.generateApiKey = async function(key) {
    var bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    var newKey = 'swadb_' + Array.from(bytes).map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
    document.getElementById('cfg-' + key).value = newKey;
    await AgentDB.api('PUT', '/api/config/' + key, { value: newKey });
    AgentDB.toast('API key generated and saved', 'success');
  };

  V.clearApiKey = async function(key) {
    document.getElementById('cfg-' + key).value = '';
    await AgentDB.api('PUT', '/api/config/' + key, { value: '' });
    AgentDB.toast('API key cleared — API is now open', 'info');
  };

  V.saveConfig = async function(key) {
    var elem = document.getElementById('cfg-' + key);
    if (!elem) return;
    var val;
    if (elem.type === 'checkbox') {
      val = elem.checked ? 'true' : 'false';
    } else {
      val = elem.value;
    }
    var r = await AgentDB.api('PUT', '/api/config/' + key, { value: val });
    if (r.status === 'ok') {
      configMap[key] = val;
      AgentDB.toast('Saved ' + key, 'success');
    } else {
      AgentDB.toast('Failed to save ' + key, 'error');
    }
  };

  V.runMaint = async function(action) {
    AgentDB.toast('Running ' + action + '...', 'info');
    var urlMap = { sleep: 'sleep-cycle', integrity_check: 'integrity-check' };
    var endpoint = urlMap[action] || action;
    var r = await AgentDB.api('POST', '/api/maintenance/' + endpoint);
    if (r.status === 'ok') {
      AgentDB.toast(action + ' completed', 'success');
    } else {
      AgentDB.toast(action + ' failed: ' + (r.error || 'Unknown'), 'error');
    }
  };

  // ── Local System Access ─────────────────────────────────────────────
  V.loadLocalSystemAccess = async function() {
    var panel = document.getElementById('lsa-panel');
    if (!panel) return;
    var [grantsR, logR, cfgR] = await Promise.all([
      AgentDB.api('GET', '/api/file-access-grants'),
      AgentDB.api('GET', '/api/shell-log?limit=10'),
      AgentDB.api('GET', '/api/config'),
    ]);
    var grants = (grantsR.status === 'ok' && grantsR.data) ? grantsR.data : [];
    var logs = (logR.status === 'ok' && logR.data) ? logR.data : [];
    var cfg = {};
    if (cfgR.status === 'ok' && cfgR.data) {
      cfgR.data.forEach(function(c) { cfg[c.key] = c.value; });
    }
    var shellEnabled = cfg.shell_access_enabled === 'true';
    var shellTimeout = cfg.shell_timeout_seconds || '30';

    var html = '';

    // ── File access grants ──
    html += '<div style="font-weight:600;margin-bottom:8px">File Access Grants</div>';
    if (grants.length === 0) {
      html += '<div style="color:var(--text2);font-size:13px;padding:8px 0;margin-bottom:12px">No grants configured. Agents have no filesystem access.</div>';
    } else {
      html += '<div style="display:grid;grid-template-columns:1fr;gap:6px;margin-bottom:12px">';
      grants.forEach(function(g) {
        var permBadge = g.permission === 'read_write'
          ? '<span style="background:#f59e0b;color:#000;padding:2px 8px;border-radius:8px;font-size:11px">read_write</span>'
          : '<span style="background:var(--bg3);padding:2px 8px;border-radius:8px;font-size:11px">read</span>';
        html += '<div style="background:var(--bg3);padding:8px 10px;border-radius:6px;display:flex;justify-content:space-between;align-items:center;gap:12px">';
        html += '<div style="flex:1;min-width:0">';
        html += '<div style="font-family:var(--mono);font-size:12px;overflow:hidden;text-overflow:ellipsis">' + AgentDB.esc(g.directory_path) + ' ' + permBadge + '</div>';
        html += '<div style="font-size:11px;color:var(--text2)">agent: ' + AgentDB.esc(g.agent_id) + ' • granted ' + AgentDB.esc(g.granted_at || '') + '</div>';
        html += '</div>';
        html += '<button class="btn btn-sm" style="color:var(--red);flex-shrink:0" data-del-grant="' + AgentDB.esc(g.id) + '">Revoke</button>';
        html += '</div>';
      });
      html += '</div>';
    }

    html += '<div id="add-grant-form" style="display:none;padding:10px;background:var(--bg3);border-radius:6px;margin-bottom:12px">';
    html += '<div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px;margin-bottom:8px">';
    html += '<div><label style="font-size:11px;color:var(--text2)">Directory</label><input type="text" id="grant-path" placeholder="C:\\\\Users\\\\you\\\\workspace" style="width:100%;font-family:var(--mono);font-size:12px"></div>';
    html += '<div><label style="font-size:11px;color:var(--text2)">Permission</label><select id="grant-perm" style="width:100%"><option value="read">read</option><option value="read_write">read_write</option></select></div>';
    html += '<div><label style="font-size:11px;color:var(--text2)">Agent</label><input type="text" id="grant-agent" value="default" style="width:100%"></div>';
    html += '</div>';
    html += '<div style="display:flex;gap:6px"><button class="btn btn-primary btn-sm" id="save-grant-btn">Add Grant</button><button class="btn btn-sm" id="cancel-grant-btn">Cancel</button></div>';
    html += '</div>';
    html += '<button class="btn btn-sm" id="show-add-grant-btn">+ Add Grant</button>';

    // ── Shell access ──
    html += '<div style="border-top:1px solid var(--bg3);margin-top:16px;padding-top:12px">';
    html += '<div style="font-weight:600;margin-bottom:8px">Shell Execution</div>';
    var shellBadge = shellEnabled
      ? '<span style="background:#f59e0b;color:#000;padding:2px 8px;border-radius:8px;font-size:11px">enabled</span>'
      : '<span style="background:var(--text2);color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">disabled</span>';
    html += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">';
    html += '<label class="setting-toggle"><input type="checkbox" id="cfg-shell_access_enabled"' + (shellEnabled ? ' checked' : '') +
            ' onchange="AgentDB.views.settings.saveConfig(\'shell_access_enabled\')"><span class="slider"></span></label>';
    html += '<span style="font-size:13px">Allow shell commands</span>' + shellBadge;
    html += '</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">';
    html += '<div><label style="font-size:11px;color:var(--text2)">Default timeout (s)</label>';
    html += '<input type="number" id="cfg-shell_timeout_seconds" value="' + AgentDB.esc(shellTimeout) + '" min="1" max="600" style="width:100%" onchange="AgentDB.views.settings.saveConfig(\'shell_timeout_seconds\')"></div>';
    html += '<div><label style="font-size:11px;color:var(--text2)">Working dir must be inside a grant</label><input type="text" value="enforced" disabled style="width:100%;color:var(--text2)"></div>';
    html += '</div>';

    // Recent shell commands
    html += '<div style="font-size:13px;font-weight:600;margin-top:8px;margin-bottom:6px">Recent Commands</div>';
    if (logs.length === 0) {
      html += '<div style="color:var(--text2);font-size:12px">No shell commands have been executed yet.</div>';
    } else {
      html += '<div style="display:grid;grid-template-columns:1fr;gap:4px;max-height:240px;overflow-y:auto">';
      logs.forEach(function(l) {
        var ec = l.exit_code;
        var ecBadge;
        if (ec === 0) ecBadge = '<span style="background:#22c55e;color:#fff;padding:1px 6px;border-radius:6px;font-size:10px">0</span>';
        else if (ec === null || ec === undefined) ecBadge = '<span style="background:var(--text2);color:#fff;padding:1px 6px;border-radius:6px;font-size:10px">running</span>';
        else ecBadge = '<span style="background:var(--red);color:#fff;padding:1px 6px;border-radius:6px;font-size:10px">' + ec + '</span>';
        var dur = l.duration_ms != null ? (l.duration_ms + 'ms') : '—';
        html += '<div style="background:var(--bg3);padding:6px 10px;border-radius:4px;font-size:11px;font-family:var(--mono);display:flex;align-items:center;gap:8px">';
        html += '<div style="flex-shrink:0">' + ecBadge + '</div>';
        html += '<div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + AgentDB.esc(l.command || '') + '</div>';
        html += '<div style="color:var(--text2);flex-shrink:0">' + dur + '</div>';
        html += '</div>';
      });
      html += '</div>';
    }
    html += '</div>'; // /shell section

    panel.innerHTML = html;

    // Wire grant form
    var showBtn = document.getElementById('show-add-grant-btn');
    if (showBtn) showBtn.onclick = function() {
      document.getElementById('add-grant-form').style.display = 'block';
    };
    var cancelBtn = document.getElementById('cancel-grant-btn');
    if (cancelBtn) cancelBtn.onclick = function() {
      document.getElementById('add-grant-form').style.display = 'none';
    };
    var saveBtn = document.getElementById('save-grant-btn');
    if (saveBtn) saveBtn.onclick = V.createGrant;
    panel.addEventListener('click', function(e) {
      var btn = e.target.closest('[data-del-grant]');
      if (btn) V.deleteGrant(btn.dataset.delGrant);
    });
  };

  V.createGrant = async function() {
    var p = document.getElementById('grant-path').value.trim();
    var perm = document.getElementById('grant-perm').value;
    var agent = document.getElementById('grant-agent').value.trim() || 'default';
    if (!p) { AgentDB.toast('Directory path is required', 'error'); return; }
    var r = await AgentDB.api('POST', '/api/file-access-grants', {
      directory_path: p, permission: perm, agent_id: agent
    });
    if (r.status === 'ok') {
      AgentDB.toast('Grant added', 'success');
      V.loadLocalSystemAccess();
    } else {
      AgentDB.toast('Failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.deleteGrant = async function(id) {
    if (!confirm('Revoke this access grant?')) return;
    var r = await AgentDB.api('DELETE', '/api/file-access-grants/' + id);
    if (r.status === 'ok') {
      AgentDB.toast('Grant revoked', 'success');
      V.loadLocalSystemAccess();
    } else {
      AgentDB.toast('Revoke failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  // ── Workspaces ──────────────────────────────────────────────────────
  V.loadWorkspaces = async function() {
    var panel = document.getElementById('workspaces-panel');
    if (!panel) return;
    var r = await AgentDB.api('GET', '/api/workspaces');
    if (r.status !== 'ok') {
      panel.innerHTML = '<div style="color:var(--red);font-size:13px">Failed to load workspaces</div>';
      return;
    }
    var workspaces = r.data || [];
    if (workspaces.length === 0) {
      panel.innerHTML = '<div style="color:var(--text2);font-size:13px;padding:8px 0">No workspaces registered yet.</div>';
      return;
    }
    var html = '<div style="display:grid;grid-template-columns:1fr;gap:8px">';
    workspaces.forEach(function(ws) {
      var typeBadge = '<span style="background:var(--bg3);padding:2px 8px;border-radius:8px;font-size:11px;font-family:var(--mono)">' + AgentDB.esc(ws.workspace_type) + '</span>';
      var fileCount = ws.file_count || 0;
      var typeBreakdown = '';
      if (ws.file_types && Object.keys(ws.file_types).length > 0) {
        typeBreakdown = ' (' + Object.keys(ws.file_types).map(function(k) {
          return AgentDB.esc(k) + ': ' + ws.file_types[k];
        }).join(', ') + ')';
      }
      var lastScanned = ws.last_scanned
        ? 'Last scanned: ' + AgentDB.esc(ws.last_scanned)
        : '<span style="color:#f59e0b">Never scanned</span>';
      html += '<div style="background:var(--bg3);padding:10px 12px;border-radius:6px;display:flex;justify-content:space-between;align-items:center;gap:12px">';
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="font-weight:600;margin-bottom:2px">' + AgentDB.esc(ws.name) + ' ' + typeBadge + '</div>';
      html += '<div style="font-family:var(--mono);font-size:11px;color:var(--text2);overflow:hidden;text-overflow:ellipsis">' + AgentDB.esc(ws.root_path) + '</div>';
      html += '<div style="font-size:11px;color:var(--text2);margin-top:2px">' +
              fileCount + ' file' + (fileCount === 1 ? '' : 's') + typeBreakdown + ' • ' + lastScanned + '</div>';
      html += '</div>';
      html += '<div style="display:flex;gap:6px;flex-shrink:0">';
      html += '<button class="btn btn-sm" data-scan-workspace="' + AgentDB.esc(ws.id) + '">Scan</button>';
      html += '<button class="btn btn-sm" style="color:var(--red)" data-del-workspace="' + AgentDB.esc(ws.id) + '">Delete</button>';
      html += '</div></div>';
    });
    html += '</div>';
    panel.innerHTML = html;
  };

  V.createWorkspace = async function() {
    var name = document.getElementById('ws-name').value.trim();
    var path = document.getElementById('ws-path').value.trim();
    var type = document.getElementById('ws-type').value;
    if (!name || !path) {
      AgentDB.toast('Name and root path are required', 'error');
      return;
    }
    var r = await AgentDB.api('POST', '/api/workspaces', {
      name: name, root_path: path, workspace_type: type
    });
    if (r.status === 'ok') {
      AgentDB.toast('Workspace registered', 'success');
      document.getElementById('add-workspace-form').style.display = 'none';
      document.getElementById('ws-name').value = '';
      document.getElementById('ws-path').value = '';
      V.loadWorkspaces();
    } else {
      AgentDB.toast('Failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.scanWorkspace = async function(id) {
    AgentDB.toast('Scanning workspace…', 'info');
    var r = await AgentDB.api('POST', '/api/workspaces/' + id + '/scan');
    if (r.status === 'ok' && r.data) {
      var d = r.data;
      var msg = 'Scan complete: +' + (d.files_added || 0) +
                ' / ~' + (d.files_updated || 0) +
                ' / -' + (d.files_removed || 0) +
                ' / =' + (d.files_unchanged || 0);
      AgentDB.toast(msg, 'success');
      V.loadWorkspaces();
    } else {
      AgentDB.toast('Scan failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.scanAllWorkspaces = async function() {
    AgentDB.toast('Scanning all workspaces…', 'info');
    var r = await AgentDB.api('POST', '/api/workspaces/scan');
    if (r.status === 'ok') {
      AgentDB.toast('Scan complete', 'success');
      V.loadWorkspaces();
    } else {
      AgentDB.toast('Scan failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.deleteWorkspace = async function(id) {
    if (!confirm('Delete this workspace and all its indexed files?')) return;
    var r = await AgentDB.api('DELETE', '/api/workspaces/' + id);
    if (r.status === 'ok') {
      AgentDB.toast('Workspace deleted', 'success');
      V.loadWorkspaces();
    } else {
      AgentDB.toast('Delete failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  // ── Encryption ──────────────────────────────────────────────────────
  V.loadEncryption = async function() {
    var panel = document.getElementById('encryption-panel');
    if (!panel) return;
    var r = await AgentDB.api('GET', '/api/encryption/status');
    if (r.status !== 'ok' || !r.data) {
      panel.innerHTML = '<div style="color:var(--red);font-size:13px">Failed to load encryption status</div>';
      return;
    }
    var s = r.data;
    var html = '';

    // Status grid
    var libBadge = s.sqlcipher_available
      ? '<span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">' + AgentDB.esc(s.library || 'available') + '</span>'
      : '<span style="background:var(--red);color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">not installed</span>';
    var dbBadge = s.db_encrypted
      ? '<span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">encrypted</span>'
      : '<span style="background:var(--text2);color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">plaintext</span>';
    var passBadge = s.passphrase_set
      ? '<span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">set</span>'
      : '<span style="background:var(--text2);color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">not set</span>';

    html += '<div style="display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:13px;margin-bottom:12px">';
    html += '<div style="color:var(--text2)">SQLCipher library:</div><div>' + libBadge + '</div>';
    html += '<div style="color:var(--text2)">Database file:</div><div>' + dbBadge + ' <span style="color:var(--text2);font-size:11px;margin-left:6px">' + AgentDB.esc(s.db_path || '') + '</span></div>';
    html += '<div style="color:var(--text2)">SWADB_PASSPHRASE env:</div><div>' + passBadge + '</div>';
    html += '</div>';

    // Drift warning: config flag says encrypted but DB is plaintext (or vice versa)
    if (s.encryption_enabled_config === true && !s.db_encrypted) {
      html += '<div style="background:#f59e0b;color:#000;padding:8px 10px;border-radius:6px;font-size:12px;margin-bottom:12px">' +
        '⚠ encryption_enabled is set but the DB file is plaintext. Click Enable Encryption below to fix.</div>';
    }
    if (s.encryption_enabled_config === false && s.db_encrypted) {
      html += '<div style="background:#f59e0b;color:#000;padding:8px 10px;border-radius:6px;font-size:12px;margin-bottom:12px">' +
        '⚠ encryption_enabled is false but the DB file is encrypted. Configuration drift.</div>';
    }

    if (!s.sqlcipher_available) {
      html += '<div style="background:var(--bg3);padding:10px 12px;border-radius:6px;font-size:13px">';
      html += '<div style="font-weight:600;margin-bottom:4px">Install SQLCipher to enable encryption</div>';
      html += '<div style="color:var(--text2);font-family:var(--mono);font-size:12px">pip install sqlcipher3</div>';
      html += '<div style="color:var(--text2);font-size:11px;margin-top:6px">After install, restart the server. Encryption uses AES-256 in CBC mode with HMAC-SHA512 page authentication.</div>';
      html += '</div>';
      panel.innerHTML = html;
      return;
    }

    // Action sections
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">';

    // Enable encryption (only if currently plaintext)
    if (!s.db_encrypted) {
      html += '<div style="background:var(--bg3);padding:12px;border-radius:6px">';
      html += '<div style="font-weight:600;margin-bottom:8px">Enable Encryption</div>';
      html += '<input type="password" id="enc-new-pass" placeholder="New passphrase" style="width:100%;margin-bottom:6px">';
      html += '<input type="password" id="enc-new-pass-confirm" placeholder="Confirm passphrase" style="width:100%;margin-bottom:8px">';
      html += '<button class="btn btn-primary" style="width:100%" onclick="AgentDB.views.settings.enableEncryption()">Encrypt Database</button>';
      html += '<div style="color:var(--text2);font-size:11px;margin-top:6px">Server restart required after encryption. Set SWADB_PASSPHRASE before restart.</div>';
      html += '</div>';
    } else {
      // Rekey + Decrypt are only meaningful when DB is currently encrypted
      html += '<div style="background:var(--bg3);padding:12px;border-radius:6px">';
      html += '<div style="font-weight:600;margin-bottom:8px">Rekey (change passphrase)</div>';
      html += '<input type="password" id="enc-old-pass-rekey" placeholder="Current passphrase" style="width:100%;margin-bottom:6px">';
      html += '<input type="password" id="enc-new-pass-rekey" placeholder="New passphrase" style="width:100%;margin-bottom:8px">';
      html += '<button class="btn btn-primary" style="width:100%" onclick="AgentDB.views.settings.rekeyEncryption()">Rekey</button>';
      html += '<div style="color:var(--text2);font-size:11px;margin-top:6px">Update SWADB_PASSPHRASE to the new value before restart.</div>';
      html += '</div>';

      html += '<div style="background:var(--bg3);padding:12px;border-radius:6px">';
      html += '<div style="font-weight:600;margin-bottom:8px">Disable Encryption</div>';
      html += '<input type="password" id="enc-old-pass-decrypt" placeholder="Current passphrase" style="width:100%;margin-bottom:8px">';
      html += '<button class="btn" style="width:100%;color:var(--red);border-color:var(--red)" onclick="AgentDB.views.settings.disableEncryption()">Decrypt Database</button>';
      html += '<div style="color:var(--text2);font-size:11px;margin-top:6px">⚠ Removes encryption. Backup kept as <code>.predecrypt.bak</code> until you delete it.</div>';
      html += '</div>';
    }
    html += '</div>';

    panel.innerHTML = html;
  };

  V.enableEncryption = async function() {
    var p = document.getElementById('enc-new-pass').value;
    var p2 = document.getElementById('enc-new-pass-confirm').value;
    if (!p) { AgentDB.toast('Passphrase is required', 'error'); return; }
    if (p !== p2) { AgentDB.toast('Passphrases do not match', 'error'); return; }
    if (!confirm('Encrypt the database? Server must be restarted afterward with SWADB_PASSPHRASE set.')) return;
    AgentDB.toast('Encrypting database…', 'info');
    var r = await AgentDB.api('POST', '/api/encryption/enable', { passphrase: p });
    if (r.status === 'ok') {
      AgentDB.toast('Database encrypted. Set SWADB_PASSPHRASE and restart the server.', 'success');
      V.loadEncryption();
    } else {
      AgentDB.toast('Encrypt failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.rekeyEncryption = async function() {
    var oldP = document.getElementById('enc-old-pass-rekey').value;
    var newP = document.getElementById('enc-new-pass-rekey').value;
    if (!oldP || !newP) { AgentDB.toast('Both passphrases are required', 'error'); return; }
    if (!confirm('Change the encryption passphrase? Update SWADB_PASSPHRASE to the new value before restart.')) return;
    AgentDB.toast('Rekeying database…', 'info');
    var r = await AgentDB.api('POST', '/api/encryption/rekey', {
      old_passphrase: oldP, new_passphrase: newP
    });
    if (r.status === 'ok') {
      AgentDB.toast('Rekeyed. Update SWADB_PASSPHRASE and restart the server.', 'success');
      V.loadEncryption();
    } else {
      AgentDB.toast('Rekey failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.disableEncryption = async function() {
    var p = document.getElementById('enc-old-pass-decrypt').value;
    if (!p) { AgentDB.toast('Passphrase is required to decrypt', 'error'); return; }
    if (!confirm('Decrypt the database (remove encryption)? An encrypted backup is kept as .predecrypt.bak. Server restart required.')) return;
    AgentDB.toast('Decrypting database…', 'info');
    var r = await AgentDB.api('POST', '/api/encryption/disable', { passphrase: p });
    if (r.status === 'ok') {
      AgentDB.toast('Database decrypted. Restart the server (SWADB_PASSPHRASE no longer needed).', 'success');
      V.loadEncryption();
    } else {
      AgentDB.toast('Decrypt failed: ' + (r.error || 'unknown'), 'error');
    }
  };
})();
