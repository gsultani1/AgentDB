(function() {
  const V = swadb.views.settings = {};
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
    var r = await swadb.api('GET', '/api/config');
    configMap = {};
    if (r.status === 'ok' && r.data) {
      r.data.forEach(function(c) { configMap[c.key] = c.value; });
    }

    var html = '<h2 style="margin-bottom:16px">Settings</h2>';

    // Appearance (theme toggle — applies immediately + persists to meta_config)
    var themeVal = configMap['theme_preference'] || 'auto';
    html += '<div class="card" style="margin-bottom:16px"><h3>Appearance</h3>';
    html += '<div style="display:flex;gap:8px;margin-top:8px">';
    ['auto', 'light', 'dark'].forEach(function (mode) {
      var sel = themeVal === mode;
      html += '<button class="btn' + (sel ? ' btn-primary' : '') +
              '" onclick="swadb.views.settings.setTheme(\'' + mode + '\')">' +
              mode.charAt(0).toUpperCase() + mode.slice(1) + '</button>';
    });
    html += '</div>';
    html += '<div style="font-size:11px;color:var(--text2);margin-top:6px">Auto follows your OS color-scheme preference.</div>';
    html += '</div>';

    // AI Providers section (dynamic from llm_providers table)
    html += '<div class="card" style="margin-bottom:16px"><h3>AI Providers</h3>';
    html += '<p style="font-size:12px;color:var(--text2);margin-bottom:12px">Configure multiple AI providers. The default provider is used for chat and consolidation.</p>';
    html += '<div id="providers-list"></div>';
    html += '<button class="btn" style="margin-top:12px" id="add-provider-btn">+ Add Provider</button>';
    html += '<div id="add-provider-form" style="display:none;margin-top:12px;padding:16px;background:var(--bg3);border-radius:var(--radius)">';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">';
    html += '<div><label style="font-size:12px;color:var(--text2)">Name</label><input type="text" id="prov-name" placeholder="My Claude" style="width:100%"></div>';
    html += '<div><label style="font-size:12px;color:var(--text2)">Type</label><select id="prov-type" style="width:100%">' +
            '<option value="claude">Claude (Anthropic)</option>' +
            '<option value="openai">OpenAI</option>' +
            '<option value="ollama">Ollama (local)</option>' +
            '<option value="llamacpp">llama.cpp (local)</option>' +
            '<option value="lmstudio">LM Studio (local)</option>' +
            '<option value="local">Generic local (OpenAI-compat)</option>' +
            '<option value="custom">Custom OpenAI-compat endpoint</option>' +
            '</select></div>';
    html += '<div><label style="font-size:12px;color:var(--text2)">Model</label><input type="text" id="prov-model" placeholder="claude-sonnet-4-20250514" style="width:100%"></div>';
    html += '<div><label style="font-size:12px;color:var(--text2)">API Key</label><input type="password" id="prov-key" placeholder="sk-..." style="width:100%"></div>';
    html += '<div style="grid-column:1/-1"><label style="font-size:12px;color:var(--text2)">Endpoint (optional)</label><input type="text" id="prov-endpoint" placeholder="Leave blank for default; Ollama: http://localhost:11434" style="width:100%"></div>';
    html += '</div>';
    // Ollama model discovery — only meaningful when type=local; a small chip list
    // appears below the form after the discover call returns.
    html += '<div style="display:flex;gap:8px;align-items:center;margin-top:10px">';
    html += '<button class="btn" id="discover-ollama-btn" title="Probe Ollama at the endpoint above (or localhost:11434) and list installed models">Discover Local Models</button>';
    html += '<span id="discover-ollama-status" style="font-size:11px;color:var(--text2)"></span>';
    html += '</div>';
    html += '<div id="discover-ollama-results" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px"></div>';
    html += '<div style="display:flex;gap:8px;margin-top:10px"><button class="btn btn-primary" id="save-provider-btn">Save Provider</button><button class="btn" id="cancel-provider-btn">Cancel</button></div>';
    html += '</div></div>';

    // Max context tokens (kept from old LLM section)
    html += '<div class="card" style="margin-bottom:16px"><h3>Context Settings</h3>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;margin-top:12px">';
    var mctVal = configMap['max_context_tokens'] || '4000';
    html += '<div><label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px">Max Context Tokens</label>';
    html += '<input type="number" id="cfg-max_context_tokens" value="' + swadb.esc(mctVal) + '" min="500" max="128000" style="width:100%" onchange="swadb.views.settings.saveConfig(\'max_context_tokens\')">';
    html += '<div style="font-size:11px;color:var(--text2);margin-top:2px">Maximum tokens for context window</div></div>';
    html += '</div></div>';

    Object.keys(SETTINGS_SCHEMA).forEach(function(section) {
      html += '<div class="card" style="margin-bottom:16px"><h3>' + swadb.esc(section) + '</h3>';
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;margin-top:12px">';

      SETTINGS_SCHEMA[section].forEach(function(f) {
        var val = configMap[f.key] || '';
        var fullW = f.fullWidth ? 'style="grid-column:1/-1"' : '';
        html += '<div ' + fullW + '>';
        html += '<label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px">' + swadb.esc(f.label) + '</label>';

        if (f.type === 'toggle') {
          var checked = val === 'true' || val === '1' ? ' checked' : '';
          html += '<label class="setting-toggle"><input type="checkbox" id="cfg-' + f.key + '"' + checked +
            ' onchange="swadb.views.settings.saveConfig(\'' + f.key + '\')"><span class="slider"></span></label>';
        } else if (f.type === 'select') {
          html += '<select id="cfg-' + f.key + '" onchange="swadb.views.settings.saveConfig(\'' + f.key + '\')" style="width:100%">';
          f.options.forEach(function(o) {
            html += '<option value="' + o + '"' + (val === o ? ' selected' : '') + '>' + o + '</option>';
          });
          html += '</select>';
        } else if (f.type === 'agent_key_gen') {
          html += '<div style="display:flex;gap:8px;align-items:center">';
          html += '<input type="text" id="cfg-' + f.key + '" value="' + swadb.esc(val) + '" style="flex:1;font-family:var(--mono);font-size:12px" readonly>';
          html += '<button class="btn btn-sm" onclick="swadb.views.settings.generateApiKey(\'' + f.key + '\')">Generate</button>';
          html += '<button class="btn btn-sm" onclick="swadb.copyToClipboard(document.getElementById(\'cfg-' + f.key + '\').value)">Copy</button>';
          html += '<button class="btn btn-sm" style="color:var(--red)" onclick="swadb.views.settings.clearApiKey(\'' + f.key + '\')">Clear</button>';
          html += '</div>';
        } else if (f.type === 'password') {
          html += '<input type="password" id="cfg-' + f.key + '" value="' + swadb.esc(val) + '" style="width:100%" ' +
            'onchange="swadb.views.settings.saveConfig(\'' + f.key + '\')">';
        } else if (f.type === 'number') {
          var attrs = '';
          if (f.min !== undefined) attrs += ' min="' + f.min + '"';
          if (f.max !== undefined) attrs += ' max="' + f.max + '"';
          if (f.step !== undefined) attrs += ' step="' + f.step + '"';
          html += '<input type="number" id="cfg-' + f.key + '" value="' + swadb.esc(val) + '" style="width:100%"' + attrs +
            ' onchange="swadb.views.settings.saveConfig(\'' + f.key + '\')">';
        } else {
          html += '<input type="text" id="cfg-' + f.key + '" value="' + swadb.esc(val) + '" style="width:100%" ' +
            'onchange="swadb.views.settings.saveConfig(\'' + f.key + '\')">';
        }

        if (f.hint) html += '<div style="font-size:11px;color:var(--text2);margin-top:2px">' + swadb.esc(f.hint) + '</div>';
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
    html += '<button class="btn btn-primary" onclick="swadb.views.settings.runMaint(\'consolidation\')">Run Consolidation</button>';
    html += '<button class="btn" onclick="swadb.views.settings.runMaint(\'integrity_check\')">Integrity Check</button>';
    html += '<button class="btn" onclick="swadb.views.settings.runMaint(\'sleep\')">Sleep Cycle</button>';
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
    document.getElementById('discover-ollama-btn').onclick = V.discoverOllama;
    document.getElementById('discover-ollama-results').addEventListener('click', function(e) {
      var chip = e.target.closest('[data-pick-model]');
      if (chip) {
        document.getElementById('prov-model').value = chip.dataset.pickModel;
        document.getElementById('prov-type').value = 'local';
      }
    });
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
    var r = await swadb.api('GET', '/api/providers');
    var wrap = document.getElementById('providers-list');
    if (!wrap) return;
    if (r.status !== 'ok' || !r.data || !r.data.length) {
      wrap.innerHTML = '<p style="color:var(--text2);font-size:13px">No providers configured. Add one to get started.</p>';
      return;
    }
    wrap.innerHTML = '<table style="width:100%"><thead><tr><th>Name</th><th>Type</th><th>Model</th><th>API Key</th><th>Default</th><th></th></tr></thead><tbody>' +
      r.data.map(function(p) {
        return '<tr>' +
          '<td><b>' + swadb.esc(p.name) + '</b></td>' +
          '<td>' + swadb.esc(p.provider_type) + '</td>' +
          '<td style="font-family:var(--mono);font-size:12px">' + swadb.esc(p.model) + '</td>' +
          '<td style="font-size:12px;color:var(--text2)">' + swadb.esc(p.api_key || '') + '</td>' +
          '<td>' + (p.is_default ? '<span class="status ok">Default</span>' : '<button class="btn btn-sm" data-set-default="' + p.id + '">Set Default</button>') + '</td>' +
          '<td><button class="btn btn-sm" style="color:var(--red)" data-del-provider="' + p.id + '">Delete</button></td>' +
          '</tr>';
      }).join('') + '</tbody></table>';
  };

  V.createProvider = async function() {
    var name = document.getElementById('prov-name').value.trim();
    var model = document.getElementById('prov-model').value.trim();
    if (!name || !model) return swadb.toast('Name and model are required', 'error');
    var r = await swadb.api('POST', '/api/providers', {
      name: name,
      provider_type: document.getElementById('prov-type').value,
      model: model,
      api_key: document.getElementById('prov-key').value,
      endpoint: document.getElementById('prov-endpoint').value,
      is_default: false
    });
    if (r.status === 'ok' || r.data?.id) {
      swadb.toast('Provider added', 'success');
      document.getElementById('add-provider-form').style.display = 'none';
      document.getElementById('prov-name').value = '';
      document.getElementById('prov-model').value = '';
      document.getElementById('prov-key').value = '';
      document.getElementById('prov-endpoint').value = '';
      V.loadProviders();
    } else {
      swadb.toast('Error: ' + (r.error || 'Unknown'), 'error');
    }
  };

  V.discoverOllama = async function() {
    var endpoint = document.getElementById('prov-endpoint').value.trim()
                   || 'http://localhost:11434';
    var status = document.getElementById('discover-ollama-status');
    var results = document.getElementById('discover-ollama-results');
    status.textContent = 'Probing ' + endpoint + '…';
    results.innerHTML = '';
    var r = await swadb.api('POST', '/api/providers/ollama/discover', { endpoint: endpoint });
    if (r.status !== 'ok' || !r.data) {
      status.textContent = 'Failed: ' + (r.error || 'unknown');
      return;
    }
    if (r.data.error) {
      status.textContent = r.data.error;
      return;
    }
    var models = r.data.models || [];
    if (!models.length) {
      status.textContent = 'No models installed at ' + endpoint;
      return;
    }
    status.textContent = 'Found ' + models.length + ' model' + (models.length === 1 ? '' : 's') + ' — click to fill';
    results.innerHTML = models.map(function(m) {
      return '<button class="btn btn-sm" data-pick-model="' + swadb.esc(m) + '">' + swadb.esc(m) + '</button>';
    }).join('');
  };

  V.setDefault = async function(id) {
    await swadb.api('PUT', '/api/providers/' + id, { is_default: true });
    swadb.toast('Default provider updated', 'success');
    V.loadProviders();
  };

  V.deleteProvider = async function(id) {
    if (!await swadb.confirm('Delete this provider?')) return;
    await swadb.api('DELETE', '/api/providers/' + id);
    swadb.toast('Provider deleted');
    V.loadProviders();
  };

  V.generateApiKey = async function(key) {
    var bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    var newKey = 'swadb_' + Array.from(bytes).map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
    document.getElementById('cfg-' + key).value = newKey;
    await swadb.api('PUT', '/api/config/' + key, { value: newKey });
    swadb.toast('API key generated and saved', 'success');
  };

  V.clearApiKey = async function(key) {
    document.getElementById('cfg-' + key).value = '';
    await swadb.api('PUT', '/api/config/' + key, { value: '' });
    swadb.toast('API key cleared — API is now open', 'info');
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
    var r = await swadb.api('PUT', '/api/config/' + key, { value: val });
    if (r.status === 'ok') {
      configMap[key] = val;
      swadb.toast('Saved ' + key, 'success');
    } else {
      swadb.toast('Failed to save ' + key, 'error');
    }
  };

  V.setTheme = async function(mode) {
    swadb.applyTheme(mode);
    var r = await swadb.api('PUT', '/api/config/theme_preference', { value: mode });
    if (r.status !== 'ok') {
      swadb.toast('Theme saved locally but failed to persist: ' + (r.error || 'unknown'), 'error');
    }
    // Re-render so the active button highlights correctly
    V.load();
  };

  V.runMaint = async function(action) {
    swadb.toast('Running ' + action + '...', 'info');
    var urlMap = { sleep: 'sleep-cycle', integrity_check: 'integrity-check' };
    var endpoint = urlMap[action] || action;
    var r = await swadb.api('POST', '/api/maintenance/' + endpoint);
    if (r.status === 'ok') {
      swadb.toast(action + ' completed', 'success');
    } else {
      swadb.toast(action + ' failed: ' + (r.error || 'Unknown'), 'error');
    }
  };

  // ── Local System Access ─────────────────────────────────────────────
  V.loadLocalSystemAccess = async function() {
    var panel = document.getElementById('lsa-panel');
    if (!panel) return;
    var [grantsR, logR, cfgR] = await Promise.all([
      swadb.api('GET', '/api/file-access-grants'),
      swadb.api('GET', '/api/shell-log?limit=10'),
      swadb.api('GET', '/api/config'),
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
        html += '<div style="font-family:var(--mono);font-size:12px;overflow:hidden;text-overflow:ellipsis">' + swadb.esc(g.directory_path) + ' ' + permBadge + '</div>';
        html += '<div style="font-size:11px;color:var(--text2)">agent: ' + swadb.esc(g.agent_id) + ' • granted ' + swadb.esc(g.granted_at || '') + '</div>';
        html += '</div>';
        html += '<button class="btn btn-sm" style="color:var(--red);flex-shrink:0" data-del-grant="' + swadb.esc(g.id) + '">Revoke</button>';
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
            ' onchange="swadb.views.settings.saveConfig(\'shell_access_enabled\')"><span class="slider"></span></label>';
    html += '<span style="font-size:13px">Allow shell commands</span>' + shellBadge;
    html += '</div>';
    html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">';
    html += '<div><label style="font-size:11px;color:var(--text2)">Default timeout (s)</label>';
    html += '<input type="number" id="cfg-shell_timeout_seconds" value="' + swadb.esc(shellTimeout) + '" min="1" max="600" style="width:100%" onchange="swadb.views.settings.saveConfig(\'shell_timeout_seconds\')"></div>';
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
        html += '<div style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + swadb.esc(l.command || '') + '</div>';
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
    if (!p) { swadb.toast('Directory path is required', 'error'); return; }
    var r = await swadb.api('POST', '/api/file-access-grants', {
      directory_path: p, permission: perm, agent_id: agent
    });
    if (r.status === 'ok') {
      swadb.toast('Grant added', 'success');
      V.loadLocalSystemAccess();
    } else {
      swadb.toast('Failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.deleteGrant = async function(id) {
    if (!confirm('Revoke this access grant?')) return;
    var r = await swadb.api('DELETE', '/api/file-access-grants/' + id);
    if (r.status === 'ok') {
      swadb.toast('Grant revoked', 'success');
      V.loadLocalSystemAccess();
    } else {
      swadb.toast('Revoke failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  // ── Workspaces ──────────────────────────────────────────────────────
  V.loadWorkspaces = async function() {
    var panel = document.getElementById('workspaces-panel');
    if (!panel) return;
    var r = await swadb.api('GET', '/api/workspaces');
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
      var typeBadge = '<span style="background:var(--bg3);padding:2px 8px;border-radius:8px;font-size:11px;font-family:var(--mono)">' + swadb.esc(ws.workspace_type) + '</span>';
      var fileCount = ws.file_count || 0;
      var typeBreakdown = '';
      if (ws.file_types && Object.keys(ws.file_types).length > 0) {
        typeBreakdown = ' (' + Object.keys(ws.file_types).map(function(k) {
          return swadb.esc(k) + ': ' + ws.file_types[k];
        }).join(', ') + ')';
      }
      var lastScanned = ws.last_scanned
        ? 'Last scanned: ' + swadb.esc(ws.last_scanned)
        : '<span style="color:#f59e0b">Never scanned</span>';
      html += '<div style="background:var(--bg3);padding:10px 12px;border-radius:6px;display:flex;justify-content:space-between;align-items:center;gap:12px">';
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="font-weight:600;margin-bottom:2px">' + swadb.esc(ws.name) + ' ' + typeBadge + '</div>';
      html += '<div style="font-family:var(--mono);font-size:11px;color:var(--text2);overflow:hidden;text-overflow:ellipsis">' + swadb.esc(ws.root_path) + '</div>';
      html += '<div style="font-size:11px;color:var(--text2);margin-top:2px">' +
              fileCount + ' file' + (fileCount === 1 ? '' : 's') + typeBreakdown + ' • ' + lastScanned + '</div>';
      html += '</div>';
      html += '<div style="display:flex;gap:6px;flex-shrink:0">';
      html += '<button class="btn btn-sm" data-scan-workspace="' + swadb.esc(ws.id) + '">Scan</button>';
      html += '<button class="btn btn-sm" style="color:var(--red)" data-del-workspace="' + swadb.esc(ws.id) + '">Delete</button>';
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
      swadb.toast('Name and root path are required', 'error');
      return;
    }
    var r = await swadb.api('POST', '/api/workspaces', {
      name: name, root_path: path, workspace_type: type
    });
    if (r.status === 'ok') {
      swadb.toast('Workspace registered', 'success');
      document.getElementById('add-workspace-form').style.display = 'none';
      document.getElementById('ws-name').value = '';
      document.getElementById('ws-path').value = '';
      V.loadWorkspaces();
    } else {
      swadb.toast('Failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.scanWorkspace = async function(id) {
    swadb.toast('Scanning workspace…', 'info');
    var r = await swadb.api('POST', '/api/workspaces/' + id + '/scan');
    if (r.status === 'ok' && r.data) {
      var d = r.data;
      var msg = 'Scan complete: +' + (d.files_added || 0) +
                ' / ~' + (d.files_updated || 0) +
                ' / -' + (d.files_removed || 0) +
                ' / =' + (d.files_unchanged || 0);
      swadb.toast(msg, 'success');
      V.loadWorkspaces();
    } else {
      swadb.toast('Scan failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.scanAllWorkspaces = async function() {
    swadb.toast('Scanning all workspaces…', 'info');
    var r = await swadb.api('POST', '/api/workspaces/scan');
    if (r.status === 'ok') {
      swadb.toast('Scan complete', 'success');
      V.loadWorkspaces();
    } else {
      swadb.toast('Scan failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.deleteWorkspace = async function(id) {
    if (!confirm('Delete this workspace and all its indexed files?')) return;
    var r = await swadb.api('DELETE', '/api/workspaces/' + id);
    if (r.status === 'ok') {
      swadb.toast('Workspace deleted', 'success');
      V.loadWorkspaces();
    } else {
      swadb.toast('Delete failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  // ── Encryption ──────────────────────────────────────────────────────
  V.loadEncryption = async function() {
    var panel = document.getElementById('encryption-panel');
    if (!panel) return;
    var r = await swadb.api('GET', '/api/encryption/status');
    if (r.status !== 'ok' || !r.data) {
      panel.innerHTML = '<div style="color:var(--red);font-size:13px">Failed to load encryption status</div>';
      return;
    }
    var s = r.data;
    var html = '';

    // Status grid
    var libBadge = s.sqlcipher_available
      ? '<span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">' + swadb.esc(s.library || 'available') + '</span>'
      : '<span style="background:var(--red);color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">not installed</span>';
    var dbBadge = s.db_encrypted
      ? '<span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">encrypted</span>'
      : '<span style="background:var(--text2);color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">plaintext</span>';
    var passBadge = s.passphrase_set
      ? '<span style="background:#22c55e;color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">set</span>'
      : '<span style="background:var(--text2);color:#fff;padding:2px 8px;border-radius:8px;font-size:11px">not set</span>';

    html += '<div style="display:grid;grid-template-columns:auto 1fr;gap:6px 12px;font-size:13px;margin-bottom:12px">';
    html += '<div style="color:var(--text2)">SQLCipher library:</div><div>' + libBadge + '</div>';
    html += '<div style="color:var(--text2)">Database file:</div><div>' + dbBadge + ' <span style="color:var(--text2);font-size:11px;margin-left:6px">' + swadb.esc(s.db_path || '') + '</span></div>';
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
      html += '<div style="background:var(--bg3);padding:12px;border-radius:6px;grid-column:1/-1">';
      html += '<div style="font-weight:600;margin-bottom:8px">Enable Encryption</div>';
      // LOUD warning — clicking through this without setting the env var is
      // the #1 way to lock yourself out, so the warning is in red and the
      // confirm dialog requires re-entering the passphrase.
      html += '<div style="background:rgba(245,158,11,0.1);border:1px solid var(--yellow);color:var(--yellow);padding:10px 12px;border-radius:6px;font-size:12px;margin-bottom:10px">';
      html += '<div style="font-weight:600;margin-bottom:4px">Before you click Encrypt</div>';
      html += '<ul style="margin:0;padding-left:18px;color:var(--text)">';
      html += '<li>You will need this passphrase <b>every time the server starts</b>. The Unlock screen will ask for it.</li>';
      html += '<li>The current plaintext DB is saved as <code>swadb.db.preencrypt.bak</code> next to the active DB. Keep that file as a safety net.</li>';
      html += '<li>If you forget the passphrase, restore <code>.preencrypt.bak</code> as <code>swadb.db</code> (server stopped) or run <code>swadb --db swadb.db encryption disable --passphrase YOURS</code> from a terminal.</li>';
      html += '</ul></div>';
      html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
      html += '<input type="password" id="enc-new-pass" placeholder="New passphrase" style="width:100%">';
      html += '<input type="password" id="enc-new-pass-confirm" placeholder="Confirm passphrase" style="width:100%">';
      html += '</div>';
      html += '<button class="btn btn-primary" style="margin-top:8px" onclick="swadb.views.settings.enableEncryption()">Encrypt Database</button>';
      html += '</div>';
    } else {
      // Rekey + Decrypt are only meaningful when DB is currently encrypted
      html += '<div style="background:var(--bg3);padding:12px;border-radius:6px">';
      html += '<div style="font-weight:600;margin-bottom:8px">Rekey (change passphrase)</div>';
      html += '<input type="password" id="enc-old-pass-rekey" placeholder="Current passphrase" style="width:100%;margin-bottom:6px">';
      html += '<input type="password" id="enc-new-pass-rekey" placeholder="New passphrase" style="width:100%;margin-bottom:8px">';
      html += '<button class="btn btn-primary" style="width:100%" onclick="swadb.views.settings.rekeyEncryption()">Rekey</button>';
      html += '<div style="color:var(--text2);font-size:11px;margin-top:6px">Update SWADB_PASSPHRASE to the new value before restart.</div>';
      html += '</div>';

      html += '<div style="background:var(--bg3);padding:12px;border-radius:6px">';
      html += '<div style="font-weight:600;margin-bottom:8px">Disable Encryption</div>';
      html += '<input type="password" id="enc-old-pass-decrypt" placeholder="Current passphrase" style="width:100%;margin-bottom:8px">';
      html += '<button class="btn" style="width:100%;color:var(--red);border-color:var(--red)" onclick="swadb.views.settings.disableEncryption()">Decrypt Database</button>';
      html += '<div style="color:var(--text2);font-size:11px;margin-top:6px">⚠ Removes encryption. Backup kept as <code>.predecrypt.bak</code> until you delete it.</div>';
      html += '</div>';
    }
    html += '</div>';

    panel.innerHTML = html;
  };

  V.enableEncryption = async function() {
    var p = document.getElementById('enc-new-pass').value;
    var p2 = document.getElementById('enc-new-pass-confirm').value;
    if (!p) { swadb.toast('Passphrase is required', 'error'); return; }
    if (p !== p2) { swadb.toast('Passphrases do not match', 'error'); return; }
    // Re-type confirm. Forgetting the passphrase still costs you data, even
    // though we no longer require restart-time env-var setup.
    var typed = prompt(
      'You are about to encrypt the database.\n\n' +
      'You will need this passphrase EVERY TIME the server starts (entered\n' +
      'on the Unlock screen). Copy it somewhere safe before continuing.\n\n' +
      'A plaintext backup will be saved as swadb.db.preencrypt.bak.\n\n' +
      'Re-type the passphrase to proceed:'
    );
    if (typed !== p) {
      swadb.toast('Passphrase did not match — encryption cancelled.', 'error');
      return;
    }
    swadb.toast('Encrypting database…', 'info');
    var r = await swadb.api('POST', '/api/encryption/enable', { passphrase: p });
    if (r.status === 'ok') {
      swadb.toast(
        'Database encrypted. Your session continues seamlessly. ' +
        'On next server start, enter this passphrase on the Unlock screen.',
        'success', 6000
      );
      V.loadEncryption();
    } else {
      swadb.toast('Encrypt failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.rekeyEncryption = async function() {
    var oldP = document.getElementById('enc-old-pass-rekey').value;
    var newP = document.getElementById('enc-new-pass-rekey').value;
    if (!oldP || !newP) { swadb.toast('Both passphrases are required', 'error'); return; }
    if (!confirm('Change the encryption passphrase? Update SWADB_PASSPHRASE to the new value before restart.')) return;
    swadb.toast('Rekeying database…', 'info');
    var r = await swadb.api('POST', '/api/encryption/rekey', {
      old_passphrase: oldP, new_passphrase: newP
    });
    if (r.status === 'ok') {
      swadb.toast('Rekeyed. Update SWADB_PASSPHRASE and restart the server.', 'success');
      V.loadEncryption();
    } else {
      swadb.toast('Rekey failed: ' + (r.error || 'unknown'), 'error');
    }
  };

  V.disableEncryption = async function() {
    var p = document.getElementById('enc-old-pass-decrypt').value;
    if (!p) { swadb.toast('Passphrase is required to decrypt', 'error'); return; }
    if (!confirm('Decrypt the database (remove encryption)? An encrypted backup is kept as .predecrypt.bak. Server restart required.')) return;
    swadb.toast('Decrypting database…', 'info');
    var r = await swadb.api('POST', '/api/encryption/disable', { passphrase: p });
    if (r.status === 'ok') {
      swadb.toast('Database decrypted. Restart the server (SWADB_PASSPHRASE no longer needed).', 'success');
      V.loadEncryption();
    } else {
      swadb.toast('Decrypt failed: ' + (r.error || 'unknown'), 'error');
    }
  };
})();
