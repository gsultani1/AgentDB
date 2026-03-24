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
      { key: 'encryption_enabled', label: 'Encryption', type: 'toggle', hint: 'Enable at-rest encryption for sensitive memory content' },
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

    // Load providers
    V.loadProviders();
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
    var newKey = 'agentdb_' + Array.from(bytes).map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
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
})();
