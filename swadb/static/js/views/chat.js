/* ============================================================
   AgentDB — Chat Console View
   Primary interaction surface: chat with the agent, view
   retrieved context and observability data in real time.
   ============================================================ */

(function () {
  'use strict';

  var V = {};
  AgentDB.views.chat = V;
  var pendingFiles = []; // [{name, type, data_b64, url}]

  /* -- Ensure persistent state fields exist -- */
  if (!AgentDB.state.chatSessionId) AgentDB.state.chatSessionId = null;
  if (!AgentDB.state.chatHistory)   AgentDB.state.chatHistory = [];

  /* =============================================================
     V.load  —  Render the full chat layout into #view-chat
     ============================================================= */
  V.load = function load() {
    var container = document.getElementById('view-chat');
    if (!container) return;

    /* Only render the skeleton once; subsequent loads just restore state */
    if (!container.querySelector('.chat-layout')) {
      var html = '';

      /* ---- Header ---- */
      html += '<div class="view-header">';
      html += '  <h2>Chat Console</h2>';
      html += '</div>';

      /* ---- Controls bar ---- */
      html += '<div class="flex items-center gap-8 mb-16" style="flex-wrap:wrap">';
      html += '  <select id="chat-provider" class="btn" style="min-width:180px">';
      html += '    <option value="">Default Provider</option>';
      html += '  </select>';
      html += '  <select id="chat-project" class="btn" style="min-width:160px">';
      html += '    <option value="">No Project</option>';
      html += '  </select>';
      html += '  <button class="btn btn-primary" id="chat-new-session">New Session</button>';
      html += '  <span class="text-muted text-sm" id="chat-session-label">';
      html += AgentDB.state.chatSessionId
        ? 'Session: ' + AgentDB.esc(AgentDB.state.chatSessionId.slice(0, 8))
        : 'No active session';
      html += '  </span>';
      html += '</div>';

      /* ---- Chat layout ---- */
      html += '<div class="chat-layout">';

      /* -- Thread -- */
      html += '  <div class="chat-thread">';
      html += '    <div class="chat-messages" id="chat-messages"></div>';
      html += '    <div class="chat-input-area">';
      html += '      <div id="chat-file-preview" class="chat-file-preview"></div>';
      html += '      <input type="file" id="chat-file-input" multiple accept="image/*,.txt,.pdf,.json,.md,.csv" style="display:none">';
      html += '      <div class="chat-input-row">';
      html += '        <textarea id="chat-input" rows="3" placeholder="Type a message..."></textarea>';
      html += '        <button class="btn" id="chat-attach" title="Attach file" style="font-size:18px;padding:6px 10px;align-self:flex-end">';
      html += '          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>';
      html += '        </button>';
      html += '        <button class="btn btn-primary" id="chat-send" style="align-self:flex-end">Send</button>';
      html += '      </div>';
      html += '    </div>';
      html += '  </div>';

      /* -- Context sidebar -- */
      html += '  <div class="chat-sidebar" id="chat-sidebar">';
      html += '    <div class="flex items-center justify-between mb-8">';
      html += '      <button class="btn btn-sm" id="chat-sidebar-toggle">Hide Context</button>';
      html += '    </div>';
      html += '    <div class="text-sm font-bold mb-8" style="text-transform:uppercase;letter-spacing:.04em;color:var(--text2)">Observability</div>';
      html += '    <div id="chat-context-content">';
      html += '      <p class="text-muted text-sm">Send a message to see retrieved context and observability data here.</p>';
      html += '    </div>';
      html += '  </div>';

      html += '</div>'; /* end chat-layout */

      container.innerHTML = html;

      /* ---- Populate provider dropdown from API ---- */
      AgentDB.api('GET', '/api/providers').then(function(r) {
        var sel = document.getElementById('chat-provider');
        if (r.status === 'ok' && r.data && r.data.length) {
          r.data.forEach(function(p) {
            var opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name + ' (' + p.model + ')' + (p.is_default ? ' *' : '');
            if (p.is_default) opt.selected = true;
            sel.appendChild(opt);
          });
        } else {
          // Fallback: add hardcoded options if no providers configured
          ['claude', 'openai', 'local'].forEach(function(v) {
            sel.innerHTML += '<option value="' + v + '">' + v + '</option>';
          });
        }
      });

      /* ---- Populate project dropdown ---- */
      AgentDB.api('GET', '/api/threads?limit=100').then(function(r) {
        var sel = document.getElementById('chat-project');
        if (!sel) return;
        var threads = (r.status === 'ok' && r.data) ? r.data : (Array.isArray(r) ? r : []);
        threads.forEach(function(t) {
          var opt = document.createElement('option');
          opt.value = t.id;
          opt.textContent = t.name;
          sel.appendChild(opt);
        });
        /* Pre-select if navigated from projects view */
        if (AgentDB.state.chatThreadId) {
          sel.value = AgentDB.state.chatThreadId;
        }
      });

      /* ---- Wire events (once) ---- */
      document.getElementById('chat-new-session').addEventListener('click', function () {
        V.startSession();
      });

      document.getElementById('chat-send').addEventListener('click', function () {
        V.send();
      });

      document.getElementById('chat-sidebar-toggle').addEventListener('click', function () {
        V.toggleSidebar();
      });

      var input = document.getElementById('chat-input');
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          V.send();
        }
      });

      document.getElementById('chat-attach').addEventListener('click', function() {
        document.getElementById('chat-file-input').click();
      });
      document.getElementById('chat-file-input').addEventListener('change', function(e) {
        Array.from(e.target.files).forEach(function(file) {
          var reader = new FileReader();
          reader.onload = function(ev) {
            var b64 = ev.target.result.split(',')[1];
            pendingFiles.push({name: file.name, type: file.type, data_b64: b64});
            renderFilePreview();
          };
          reader.readAsDataURL(file);
        });
        e.target.value = '';
      });
    }

    /* ---- Restore messages from state ---- */
    V._restoreHistory();
  };

  /* =============================================================
     V._restoreHistory  —  Re-render messages from AgentDB.state
     ============================================================= */
  V._restoreHistory = function _restoreHistory() {
    var messagesEl = document.getElementById('chat-messages');
    if (!messagesEl) return;
    messagesEl.innerHTML = '';

    var history = AgentDB.state.chatHistory;
    for (var i = 0; i < history.length; i++) {
      V.appendMsg(history[i].role, history[i].content);
    }
  };

  /* =============================================================
     V.startSession  —  POST /api/agent/session/start
     ============================================================= */
  V.startSession = function startSession() {
    var provider = document.getElementById('chat-provider');
    var providerVal = provider ? provider.value : 'claude';
    var projectSel = document.getElementById('chat-project');
    var threadId = projectSel ? projectSel.value : '';

    return AgentDB.api('POST', '/api/agent/session/start', {
      provider: providerVal,
      thread_id: threadId || undefined,
      provider_id: providerVal || undefined,
    })
      .then(function (res) {
        var data = res.data || res;
        if (data && data.session_id) {
          AgentDB.state.chatSessionId = data.session_id;
          AgentDB.state.chatHistory = [];

          /* Clear UI */
          var messagesEl = document.getElementById('chat-messages');
          if (messagesEl) messagesEl.innerHTML = '';

          /* Reset context sidebar */
          var ctx = document.getElementById('chat-context-content');
          if (ctx) {
            ctx.innerHTML = '<p class="text-muted text-sm">Send a message to see retrieved context and observability data here.</p>';
          }

          /* Update session label */
          var label = document.getElementById('chat-session-label');
          var projectSel = document.getElementById('chat-project');
          var projectName = projectSel && projectSel.value ? projectSel.options[projectSel.selectedIndex].textContent : '';
          if (label) label.textContent = 'Session: ' + data.session_id.slice(0, 8) + (projectName ? ' | ' + projectName : '');

          AgentDB.toast('New session started', 'success');
        } else {
          AgentDB.toast(res.error || 'Failed to start session', 'error');
        }
        return res;
      });
  };

  /* =============================================================
     renderFilePreview  —  Show pending file attachments
     ============================================================= */
  function renderFilePreview() {
    var wrap = document.getElementById('chat-file-preview');
    if (!wrap) return;
    if (!pendingFiles.length) { wrap.innerHTML = ''; return; }
    wrap.innerHTML = pendingFiles.map(function(f, i) {
      var isImg = f.type.startsWith('image/');
      var preview = isImg
        ? '<img src="data:' + f.type + ';base64,' + f.data_b64 + '" style="width:32px;height:32px;object-fit:cover;border-radius:4px">'
        : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
      return '<div class="chat-preview-chip">' + preview +
        '<span>' + AgentDB.esc(f.name) + '</span>' +
        '<button onclick="AgentDB.views.chat.removeFile(' + i + ')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:14px;line-height:1">&times;</button></div>';
    }).join('');
  }

  V.removeFile = function(idx) {
    pendingFiles.splice(idx, 1);
    renderFilePreview();
  };

  /* =============================================================
     V.send  —  Send a message to the agent
     ============================================================= */
  V.send = function send() {
    var inputEl = document.getElementById('chat-input');
    if (!inputEl) return;

    var message = inputEl.value.trim();
    if (!message && !pendingFiles.length) return;
    if (!message) message = '';

    /* Capture pending files before clearing */
    var filesToSend = pendingFiles.slice();
    pendingFiles = [];
    renderFilePreview();

    /* Clear input immediately */
    inputEl.value = '';
    inputEl.style.height = 'auto';

    /* Auto-start session if none exists */
    var sessionReady;
    if (!AgentDB.state.chatSessionId) {
      sessionReady = V.startSession();
    } else {
      sessionReady = Promise.resolve();
    }

    sessionReady.then(function () {
      /* Upload files and build content parts */
      var uploadPromises = filesToSend.map(function(f) {
        return AgentDB.api('POST', '/api/uploads', {
          filename: f.name, data: f.data_b64, content_type: f.type
        }).then(function() { return f; });
      });
      return Promise.all(uploadPromises);
    }).then(function(uploadedFiles) {
      var displayContent = message;
      var historyContent = message;

      /* Build multi-part content if files attached */
      if (uploadedFiles.length) {
        var apiParts = [];    // full content — sent to LLM
        var displayParts = []; // compact chips — shown in chat bubble

        for (var i = 0; i < uploadedFiles.length; i++) {
          var f = uploadedFiles[i];
          if (f.type.startsWith('image/')) {
            apiParts.push({
              type: "image",
              source: { type: "base64", media_type: f.type, data: f.data_b64 }
            });
            displayParts.push({
              type: "image",
              source: { type: "base64", media_type: f.type, data: f.data_b64 }
            });
          } else {
            // Decode file for the API so the LLM can read it
            var decoded = '';
            try { decoded = atob(f.data_b64); } catch (_) { decoded = '[binary file]'; }
            apiParts.push({ type: "text", text: "[File: " + f.name + "]\n" + decoded });
            // Display only shows a compact attachment chip
            displayParts.push({ type: "file", name: f.name, size: decoded.length });
          }
        }
        if (message) {
          apiParts.push({ type: "text", text: message });
          displayParts.push({ type: "text", text: message });
        }
        historyContent = apiParts;
        displayContent = displayParts;
      }

      /* Append user message to UI and state */
      V.appendMsg('user', displayContent);
      AgentDB.state.chatHistory.push({ role: 'user', content: historyContent });

      /* Show typing indicator */
      var typingEl = V.showTyping();

      /* Build request */
      var payload = {
        message: message,
        session_id: AgentDB.state.chatSessionId,
        history: AgentDB.state.chatHistory,
      };

      /* If multi-part content, set it on payload */
      if (uploadedFiles.length) {
        payload.content = historyContent;
      }

      var provider = document.getElementById('chat-provider');
      if (provider) payload.provider = provider.value;

      AgentDB.api('POST', '/api/agent/chat', payload)
        .then(function (res) {
          /* Remove typing indicator */
          V.removeTyping(typingEl);

          var d = res.data || {};
          if (res.status === 'ok' && d.response) {
            /* Append assistant message */
            V.appendMsg('assistant', d.response);
            AgentDB.state.chatHistory.push({ role: 'assistant', content: d.response });

            /* Update sidebar with context */
            V.renderContext(d);
          } else {
            var errMsg = res.error || 'Unknown error from agent';
            V.appendMsg('error', errMsg);
          }
        })
        .catch(function () {
          V.removeTyping(typingEl);
          V.appendMsg('error', 'Network error — could not reach the agent.');
        });
    });
  };

  /* =============================================================
     V.appendMsg  —  Add a message bubble to the chat thread
     ============================================================= */
  V.appendMsg = function appendMsg(role, content) {
    var messagesEl = document.getElementById('chat-messages');
    if (!messagesEl) return;

    var wrapper = document.createElement('div');

    if (role === 'user') {
      wrapper.className = 'chat-msg chat-msg-user';
      if (Array.isArray(content)) {
        var htmlParts = content.map(function(part) {
          if (part.type === 'image') return '<img src="data:' + part.source.media_type + ';base64,' + part.source.data + '" style="max-width:200px;border-radius:8px;margin:4px 0">';
          if (part.type === 'file') {
            var sizeStr = part.size > 1024 ? Math.round(part.size / 1024) + ' KB' : part.size + ' B';
            return '<div class="chat-file-chip">' +
              '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>' +
              '<span>' + AgentDB.esc(part.name) + '</span>' +
              '<span style="opacity:.7;font-size:.75rem">' + sizeStr + '</span></div>';
          }
          if (part.type === 'text') return '<p>' + AgentDB.esc(part.text) + '</p>';
          return '';
        }).join('');
        wrapper.innerHTML = '<div class="chat-msg-role" style="font-size:.75rem;opacity:.8;margin-bottom:2px">You</div>' + htmlParts;
      } else {
        wrapper.innerHTML =
          '<div class="chat-msg-role" style="font-size:.75rem;opacity:.8;margin-bottom:2px">You</div>' +
          '<div>' + AgentDB.esc(content) + '</div>';
      }
    } else if (role === 'assistant') {
      wrapper.className = 'chat-msg chat-msg-assistant md-content';
      wrapper.innerHTML =
        '<div class="chat-msg-role" style="font-size:.75rem;color:var(--text2);margin-bottom:2px">Assistant</div>' +
        '<div>' + AgentDB.renderMarkdown(content) + '</div>';
    } else {
      /* error */
      wrapper.className = 'chat-msg chat-msg-assistant';
      wrapper.style.borderLeft = '3px solid var(--red)';
      wrapper.innerHTML =
        '<div class="chat-msg-role" style="font-size:.75rem;color:var(--red);margin-bottom:2px">Error</div>' +
        '<div style="color:var(--red)">' + AgentDB.esc(content) + '</div>';
    }

    messagesEl.appendChild(wrapper);

    /* Auto-scroll to bottom */
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  /* =============================================================
     V.showTyping  —  Animated typing indicator
     ============================================================= */
  V.showTyping = function showTyping() {
    var messagesEl = document.getElementById('chat-messages');
    if (!messagesEl) return null;

    var el = document.createElement('div');
    el.className = 'typing-indicator';
    el.id = 'typing-indicator';
    el.innerHTML = '<span></span><span></span><span></span>' +
                   '<span class="typing-status" id="typing-status">Retrieving context\u2026</span>';

    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    /* Phase the status label based on elapsed time */
    var startMs = Date.now();
    el._statusInterval = setInterval(function () {
      var statusEl = document.getElementById('typing-status');
      if (!statusEl) { clearInterval(el._statusInterval); return; }
      var elapsed = Date.now() - startMs;
      if (elapsed > 8000) {
        statusEl.textContent = 'Still working\u2026 models may be loading';
      } else if (elapsed > 3000) {
        statusEl.textContent = 'Waiting for model response\u2026';
      }
    }, 1000);

    return el;
  };

  /* Clean up typing indicator interval */
  V.removeTyping = function removeTyping(el) {
    if (!el) return;
    if (el._statusInterval) clearInterval(el._statusInterval);
    if (el.parentNode) el.parentNode.removeChild(el);
  };

  /* =============================================================
     V.renderContext  —  Populate the observability sidebar
     ============================================================= */
  V.renderContext = function renderContext(data) {
    var ctx = document.getElementById('chat-context-content');
    if (!ctx) return;

    var payload = data.context_payload || {};
    var memBucket = payload.memories || {};
    var html = '';

    /* ---- Retrieval strategies used ---- */
    var strats = payload.retrieval_strategies;
    if (strats && strats.length) {
      html += '<div class="obs-strategies">';
      for (var i = 0; i < strats.length; i++) {
        html += '<span class="obs-strategy-badge">' + AgentDB.esc(strats[i]) + '</span>';
      }
      html += '</div>';
    }

    /* ---- Memories by tier ---- */
    var tiers = [
      { key: 'short_term',  label: 'Short-Term Memories', color: '#3b82f6' },
      { key: 'midterm',     label: 'Mid-Term Memories',   color: '#8b5cf6' },
      { key: 'long_term',   label: 'Long-Term Memories',  color: '#10b981' },
    ];

    for (var t = 0; t < tiers.length; t++) {
      var memories = memBucket[tiers[t].key];
      if (!memories || !memories.length) continue;

      html += '<div class="obs-section">';
      html += '<div class="obs-section-title">' +
              AgentDB.esc(tiers[t].label) +
              ' <span class="obs-count">' + memories.length + '</span></div>';

      for (var m = 0; m < memories.length; m++) {
        var mem = memories[m];
        var combined = (typeof mem.combined_score === 'number') ? mem.combined_score.toFixed(3) : '';
        var semantic = (typeof mem.similarity_score === 'number') ? mem.similarity_score.toFixed(3) : '';
        var displayScore = combined || semantic || '—';
        var snippet = AgentDB.truncate(mem.content || mem.text || '', 120);

        html += '<div class="obs-mem-card" data-tier="' + tiers[t].key + '">';

        /* Header: score, type badge, metadata */
        html += '<div class="obs-mem-header">';
        html += '<span class="obs-mem-score">' + AgentDB.esc(displayScore) + '</span>';
        if (mem.type) {
          html += '<span class="obs-mem-type">' + AgentDB.esc(mem.type) + '</span>';
        }
        html += '<span class="obs-mem-meta">';
        if (typeof mem.confidence === 'number') {
          html += '<span title="Confidence">' + (mem.confidence * 100).toFixed(0) + '%</span>';
        }
        if (mem.source) {
          html += '<span title="Source">' + AgentDB.esc(AgentDB.truncate(mem.source, 20)) + '</span>';
        }
        if (mem.created_at || mem.timestamp) {
          var ts = mem.created_at || mem.timestamp;
          html += '<span title="' + AgentDB.esc(ts) + '">' + AgentDB.esc(_relativeTime(ts)) + '</span>';
        }
        html += '</span>';
        html += '</div>';

        /* Content */
        html += '<div class="obs-mem-content">' + AgentDB.esc(snippet) + '</div>';

        /* Strategy score breakdown bars */
        var rs = mem.retrieval_strategies;
        if (rs && typeof rs === 'object') {
          html += '<div class="obs-mem-strategies" title="Strategy contribution">';
          var stratKeys = ['semantic', 'bm25', 'graph', 'temporal'];
          for (var si = 0; si < stratKeys.length; si++) {
            var sv = rs[stratKeys[si]];
            if (sv && sv > 0) {
              var barW = Math.max(8, Math.round(sv * 60));
              html += '<span class="obs-mem-strat-bar" data-strat="' + stratKeys[si] +
                      '" style="width:' + barW + 'px" title="' + stratKeys[si] + ': ' + sv.toFixed(3) + '"></span>';
            }
          }
          html += '</div>';
        }

        html += '</div>'; /* end obs-mem-card */
      }
      html += '</div>'; /* end obs-section */
    }

    /* ---- Entities ---- */
    var entities = payload.entities;
    if (entities && entities.length) {
      html += '<div class="obs-section">';
      html += '<div class="obs-section-title">Matched Entities <span class="obs-count">' + entities.length + '</span></div>';
      for (var e = 0; e < entities.length; e++) {
        var ent = entities[e];
        html += '<div class="obs-entity-card">';
        if (ent.entity_type) {
          html += '<span class="obs-entity-type">' + AgentDB.esc(ent.entity_type) + '</span>';
        }
        html += '<span class="font-bold">' + AgentDB.esc(ent.name || ent.id || '') + '</span>';
        if (ent.description) {
          html += ' <span class="text-muted">— ' + AgentDB.esc(AgentDB.truncate(ent.description, 60)) + '</span>';
        }
        html += '</div>';
      }
      html += '</div>';
    }

    /* ---- Identity ---- */
    var identity = payload.identity;
    if (identity && identity.length) {
      html += '<div class="obs-section">';
      html += '<div class="obs-section-title">Identity Memories <span class="obs-count">' + identity.length + '</span></div>';
      for (var id = 0; id < identity.length; id++) {
        var idm = identity[id];
        html += '<div style="background:var(--bg);padding:6px 10px;border-radius:var(--radius);margin-bottom:4px;font-size:.82rem">';
        html += AgentDB.esc(AgentDB.truncate(idm.content || idm.text || '', 100));
        html += '</div>';
      }
      html += '</div>';
    }

    /* ---- Goals ---- */
    var goals = payload.goals;
    if (goals && goals.length) {
      html += '<div class="obs-section">';
      html += '<div class="obs-section-title">Matched Goals <span class="obs-count">' + goals.length + '</span></div>';
      for (var g = 0; g < goals.length; g++) {
        html += '<div style="background:var(--bg);padding:6px 10px;border-radius:var(--radius);margin-bottom:4px;font-size:.82rem">';
        html += '<span>' + AgentDB.esc(goals[g].description || goals[g].name || goals[g]) + '</span>';
        html += '</div>';
      }
      html += '</div>';
    }

    /* ---- Skills ---- */
    var skills = payload.skills;
    if (skills && skills.length) {
      html += '<div class="obs-section">';
      html += '<div class="obs-section-title">Matched Skills <span class="obs-count">' + skills.length + '</span></div>';
      for (var s = 0; s < skills.length; s++) {
        var sk = skills[s];
        html += '<div style="background:var(--bg);padding:6px 10px;border-radius:var(--radius);margin-bottom:4px;font-size:.82rem">';
        html += '<span class="font-bold">' + AgentDB.esc(sk.name || '') + '</span>';
        if (sk.description) {
          html += ' <span class="text-muted"> — ' + AgentDB.esc(AgentDB.truncate(sk.description, 60)) + '</span>';
        }
        html += '</div>';
      }
      html += '</div>';
    }

    /* ---- Observability footer ---- */
    html += '<hr style="margin:14px 0">';
    html += '<div style="font-size:.82rem;color:var(--text2);display:flex;flex-direction:column;gap:4px">';

    if (data.provider) {
      html += '<div><span class="font-bold">Provider:</span> ' + AgentDB.esc(data.provider) + '</div>';
    }
    if (data.model) {
      html += '<div><span class="font-bold">Model:</span> ' + AgentDB.esc(data.model) + '</div>';
    }
    if (typeof data.llm_latency_seconds === 'number') {
      html += '<div><span class="font-bold">Latency:</span> ' + data.llm_latency_seconds.toFixed(2) + 's</div>';
    }
    if (data.snapshot_id) {
      html += '<div><span class="font-bold">Snapshot:</span> <span class="text-mono">' +
              AgentDB.esc(String(data.snapshot_id).slice(0, 8)) + '</span></div>';
    }
    if (data.llm_error) {
      html += '<div style="color:#ef4444"><span class="font-bold">Error:</span> ' + AgentDB.esc(data.llm_error) + '</div>';
    }

    html += '</div>';

    /* ---- Collapsible: Full context payload sent to model ---- */
    if (data.formatted_context) {
      html += '<div class="obs-collapsible">';
      html += '<button class="obs-collapsible-toggle" data-obs-toggle="ctx-payload">';
      html += '<span class="obs-chevron">&#9654;</span> Context Payload Sent to Model';
      html += '</button>';
      html += '<div class="obs-collapsible-body" id="obs-ctx-payload">';
      html += '<div class="obs-context-payload">' + AgentDB.esc(data.formatted_context) + '</div>';
      html += '</div>';
      html += '</div>';
    }

    /* ---- Empty state fallback ---- */
    if (!html.trim()) {
      html = '<p class="text-muted text-sm">No context data returned for this response.</p>';
    }

    ctx.innerHTML = html;

    /* Wire up collapsible toggles */
    var toggles = ctx.querySelectorAll('.obs-collapsible-toggle');
    for (var ti = 0; ti < toggles.length; ti++) {
      toggles[ti].addEventListener('click', function () {
        var targetId = 'obs-' + this.getAttribute('data-obs-toggle');
        var body = document.getElementById(targetId);
        if (body) {
          body.classList.toggle('open');
          this.classList.toggle('open');
        }
      });
    }
  };

  /* helper: relative time from ISO string */
  function _relativeTime(iso) {
    try {
      var d = new Date(iso);
      var now = new Date();
      var diff = (now - d) / 1000;
      if (diff < 60) return 'just now';
      if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
      if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
      if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
      return d.toLocaleDateString();
    } catch (e) { return iso; }
  }

  /* =============================================================
     V.toggleSidebar  —  Show / hide context sidebar
     ============================================================= */
  V.toggleSidebar = function toggleSidebar() {
    var sidebar = document.getElementById('chat-sidebar');
    var btn = document.getElementById('chat-sidebar-toggle');
    if (!sidebar) return;

    var isHidden = sidebar.style.display === 'none';
    if (isHidden) {
      sidebar.style.display = '';
      if (btn) btn.textContent = 'Hide Context';
    } else {
      sidebar.style.display = 'none';
      if (btn) btn.textContent = 'Show Context';
    }
  };
})();
