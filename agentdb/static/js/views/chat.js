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
      html += '      <div id="chat-file-preview" style="display:none;padding:8px;flex-wrap:wrap;gap:8px;width:100%"></div>';
      html += '      <input type="file" id="chat-file-input" multiple accept="image/*,.txt,.pdf,.json,.md,.csv" style="display:none">';
      html += '      <textarea id="chat-input" rows="3" placeholder="Type a message..." ';
      html += '        style="flex:1"></textarea>';
      html += '      <button class="btn" id="chat-attach" title="Attach file" style="font-size:18px;padding:6px 10px;align-self:flex-end">&#128206;</button>';
      html += '      <button class="btn btn-primary" id="chat-send" ';
      html += '        style="align-self:flex-end">Send</button>';
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

    return AgentDB.api('POST', '/api/agent/session/start', { provider: providerVal })
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
          if (label) label.textContent = 'Session: ' + data.session_id.slice(0, 8);

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
    if (!pendingFiles.length) { wrap.style.display = 'none'; return; }
    wrap.style.display = 'flex';
    wrap.innerHTML = pendingFiles.map(function(f, i) {
      var isImg = f.type.startsWith('image/');
      return '<div style="display:flex;align-items:center;gap:4px;background:var(--bg3);padding:4px 8px;border-radius:var(--radius);font-size:12px">' +
        (isImg ? '<img src="data:' + f.type + ';base64,' + f.data_b64 + '" style="width:32px;height:32px;object-fit:cover;border-radius:4px">' : '<span>&#128196;</span>') +
        '<span>' + AgentDB.esc(f.name) + '</span>' +
        '<button onclick="AgentDB.views.chat.removeFile(' + i + ')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:14px">&times;</button></div>';
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
        var contentParts = [];
        for (var i = 0; i < uploadedFiles.length; i++) {
          var f = uploadedFiles[i];
          if (f.type.startsWith('image/')) {
            contentParts.push({
              type: "image",
              source: { type: "base64", media_type: f.type, data: f.data_b64 }
            });
          } else {
            contentParts.push({ type: "text", text: "[File: " + f.name + "]\n" + atob(f.data_b64) });
          }
        }
        if (message) {
          contentParts.push({ type: "text", text: message });
        }
        historyContent = contentParts;
        displayContent = contentParts;
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
          if (typingEl && typingEl.parentNode) typingEl.parentNode.removeChild(typingEl);

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
          if (typingEl && typingEl.parentNode) typingEl.parentNode.removeChild(typingEl);
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
    el.innerHTML = '<span></span><span></span><span></span>';

    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    return el;
  };

  /* =============================================================
     V.renderContext  —  Populate the observability sidebar
     ============================================================= */
  V.renderContext = function renderContext(data) {
    var ctx = document.getElementById('chat-context-content');
    if (!ctx) return;

    var payload = data.context_payload || {};
    var html = '';

    /* ---- Memories by tier ---- */
    var tiers = [
      { key: 'short_term',  label: 'SHORT-TERM MEMORIES' },
      { key: 'midterm',     label: 'MID-TERM MEMORIES' },
      { key: 'long_term',   label: 'LONG-TERM MEMORIES' },
    ];

    for (var t = 0; t < tiers.length; t++) {
      var memories = payload[tiers[t].key];
      if (!memories || !memories.length) continue;

      html += '<div style="margin-bottom:14px">';
      html += '<div class="text-sm font-bold mb-8" style="text-transform:uppercase;letter-spacing:.04em;color:var(--text2)">' +
              AgentDB.esc(tiers[t].label) + '</div>';

      for (var m = 0; m < memories.length; m++) {
        var mem = memories[m];
        var score = (typeof mem.similarity === 'number') ? mem.similarity.toFixed(3) : '—';
        var snippet = AgentDB.truncate(mem.content || mem.text || '', 100);

        html += '<div style="background:var(--bg);padding:8px 10px;border-radius:var(--radius);margin-bottom:6px;font-size:.85rem">';
        html += '  <span class="text-accent text-mono font-bold" style="margin-right:6px">' + AgentDB.esc(score) + '</span>';
        html += '  <span class="text-muted">' + AgentDB.esc(snippet) + '</span>';
        html += '</div>';
      }
      html += '</div>';
    }

    /* ---- Goals ---- */
    var goals = payload.goals;
    if (goals && goals.length) {
      html += '<div style="margin-bottom:14px">';
      html += '<div class="text-sm font-bold mb-8" style="text-transform:uppercase;letter-spacing:.04em;color:var(--text2)">MATCHED GOALS</div>';
      for (var g = 0; g < goals.length; g++) {
        html += '<div style="background:var(--bg);padding:8px 10px;border-radius:var(--radius);margin-bottom:6px;font-size:.85rem">';
        html += '  <span>' + AgentDB.esc(goals[g].description || goals[g].name || goals[g]) + '</span>';
        html += '</div>';
      }
      html += '</div>';
    }

    /* ---- Skills ---- */
    var skills = payload.skills;
    if (skills && skills.length) {
      html += '<div style="margin-bottom:14px">';
      html += '<div class="text-sm font-bold mb-8" style="text-transform:uppercase;letter-spacing:.04em;color:var(--text2)">MATCHED SKILLS</div>';
      for (var s = 0; s < skills.length; s++) {
        var sk = skills[s];
        html += '<div style="background:var(--bg);padding:8px 10px;border-radius:var(--radius);margin-bottom:6px;font-size:.85rem">';
        html += '  <span class="font-bold">' + AgentDB.esc(sk.name || '') + '</span>';
        if (sk.description) {
          html += ' <span class="text-muted"> — ' + AgentDB.esc(sk.description) + '</span>';
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

    html += '</div>';

    /* ---- Empty state fallback ---- */
    if (!html.trim()) {
      html = '<p class="text-muted text-sm">No context data returned for this response.</p>';
    }

    ctx.innerHTML = html;
  };

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
