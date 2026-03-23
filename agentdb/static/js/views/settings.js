(function() {
  const V = AgentDB.views.settings = {};
  const el = () => document.getElementById('view-settings');

  const SETTINGS_SCHEMA = {
    "LLM Provider": [
      { key: 'llm_provider', label: 'Provider', type: 'select', options: ['claude','openai','local'], hint: 'LLM backend to use for consolidation and chat' },
      { key: 'llm_api_key', label: 'API Key', type: 'password', hint: 'API key for the selected LLM provider' },
      { key: 'llm_model', label: 'Model', type: 'text', hint: 'Model name (e.g. claude-sonnet-4-20250514, gpt-4o)' },
      { key: 'llm_endpoint', label: 'Endpoint URL', type: 'text', fullWidth: true, hint: 'Custom API endpoint (leave blank for default)' },
      { key: 'max_context_tokens', label: 'Max Context Tokens', type: 'number', min: 500, max: 128000, hint: 'Maximum tokens for context window' },
    ],
    "Agent API": [
      { key: 'agent_api_key', label: 'Agent API Key', type: 'password', fullWidth: true, hint: 'API key clients must send to authenticate with AgentDB' },
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
    var r = await AgentDB.api('POST', '/api/maintenance/' + action);
    if (r.status === 'ok') {
      AgentDB.toast(action + ' completed', 'success');
    } else {
      AgentDB.toast(action + ' failed: ' + (r.error || 'Unknown'), 'error');
    }
  };
})();
