/* ============================================================
   AgentDB — Application Core
   All shared state, utilities, and navigation live here.
   View modules attach themselves to AgentDB.views.
   ============================================================ */

window.AgentDB = window.AgentDB || {};

AgentDB.views = {};

AgentDB.state = {
  currentView: 'dashboard',
  sidebarCollapsed: localStorage.getItem('sidebar-collapsed') === 'true',
  currentAgent: '',
};

/* ---------------------------------------------------------------
   1. API helper
   --------------------------------------------------------------- */
AgentDB._agentApiKey = null;   // cached agent API key (fetched once on first agent call)
AgentDB._agentKeyLoaded = false;

AgentDB._ensureAgentKey = async function () {
  if (AgentDB._agentKeyLoaded) return;
  AgentDB._agentKeyLoaded = true;
  try {
    var r = await fetch('/api/config/agent_api_key');
    var json = await r.json();
    if (json.status === 'ok' && json.data && json.data.value) {
      AgentDB._agentApiKey = json.data.value;
    }
  } catch (_) { /* key not set or network error — leave null */ }
};

AgentDB.api = async function api(method, path, body) {
  try {
    var opts = {
      method: method.toUpperCase(),
      headers: {},
    };
    if (body !== undefined && body !== null) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    // Inject agent API key for /api/agent/* requests
    if (path.indexOf('/api/agent/') === 0) {
      await AgentDB._ensureAgentKey();
      if (AgentDB._agentApiKey) {
        opts.headers['X-API-Key'] = AgentDB._agentApiKey;
      }
    }
    var res = await fetch(path, opts);
    var data = await res.json();
    return data;
  } catch (err) {
    return { status: 'error', error: err.message || 'Network error' };
  }
};

/* ---------------------------------------------------------------
   2. Toast notifications
   --------------------------------------------------------------- */
AgentDB.toast = function toast(msg, type, duration) {
  if (type === undefined) type = 'info';
  if (duration === undefined) duration = 3000;

  var container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  var el = document.createElement('div');
  el.className = 'toast toast-' + type;
  el.textContent = msg;
  container.appendChild(el);

  setTimeout(function () {
    el.classList.add('removing');
    el.addEventListener('animationend', function () {
      el.remove();
    });
  }, duration);
};

/* ---------------------------------------------------------------
   3. HTML escape
   --------------------------------------------------------------- */
AgentDB.esc = function esc(s) {
  var d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
};

/* ---------------------------------------------------------------
   4. Copy to clipboard
   --------------------------------------------------------------- */
AgentDB.copyToClipboard = function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function () {
      AgentDB.toast('Copied to clipboard', 'success', 2000);
    }).catch(function () {
      AgentDB.toast('Failed to copy', 'error', 2000);
    });
  } else {
    // Fallback
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      AgentDB.toast('Copied to clipboard', 'success', 2000);
    } catch (_) {
      AgentDB.toast('Failed to copy', 'error', 2000);
    }
    document.body.removeChild(ta);
  }
};

/* ---------------------------------------------------------------
   5. Confirm dialog (returns Promise<boolean>)
   --------------------------------------------------------------- */
AgentDB.confirm = function confirmDialog(message) {
  return new Promise(function (resolve) {
    // Remove any existing modal
    var existing = document.querySelector('.modal-overlay.confirm-modal');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay confirm-modal active';

    var dialog = document.createElement('div');
    dialog.className = 'modal-dialog';

    var msgEl = document.createElement('p');
    msgEl.textContent = message;

    var actions = document.createElement('div');
    actions.className = 'modal-actions';

    var cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn';
    cancelBtn.textContent = 'Cancel';

    var okBtn = document.createElement('button');
    okBtn.className = 'btn btn-primary';
    okBtn.textContent = 'OK';

    function cleanup(result) {
      overlay.classList.remove('active');
      setTimeout(function () { overlay.remove(); }, 200);
      resolve(result);
    }

    cancelBtn.addEventListener('click', function () { cleanup(false); });
    okBtn.addEventListener('click', function () { cleanup(true); });
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) cleanup(false);
    });

    actions.appendChild(cancelBtn);
    actions.appendChild(okBtn);
    dialog.appendChild(msgEl);
    dialog.appendChild(actions);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    okBtn.focus();
  });
};

/* ---------------------------------------------------------------
   6. Format date
   --------------------------------------------------------------- */
AgentDB.formatDate = function formatDate(iso) {
  if (!iso) return '';
  var d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }) + ' ' + d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
};

/* ---------------------------------------------------------------
   7. Truncate
   --------------------------------------------------------------- */
AgentDB.truncate = function truncate(text, len) {
  if (len === undefined) len = 100;
  if (!text) return '';
  text = String(text);
  if (text.length <= len) return text;
  return text.slice(0, len) + '\u2026';
};

/* ---------------------------------------------------------------
   8. Markdown renderer
   --------------------------------------------------------------- */
AgentDB.renderMarkdown = function renderMarkdown(text) {
  if (!text) return '';
  var html = text;

  // ---- Phase 1: extract fenced code blocks to protect them ----
  var codeBlocks = [];
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function (_, lang, code) {
    var idx = codeBlocks.length;
    codeBlocks.push({ lang: lang, code: code });
    return '\x00CODEBLOCK' + idx + '\x00';
  });

  // ---- Phase 2: block-level elements ----

  // Horizontal rules (must come before list processing)
  html = html.replace(/^---+$/gm, '<hr>');

  // Tables
  html = html.replace(/((?:^\|.+\|$\n?)+)/gm, function (tableBlock) {
    var rows = tableBlock.trim().split('\n');
    if (rows.length < 2) return tableBlock;
    var out = '<table>';
    // Header
    var headerCells = rows[0].split('|').filter(function (c) { return c.trim() !== ''; });
    out += '<thead><tr>';
    headerCells.forEach(function (c) { out += '<th>' + c.trim() + '</th>'; });
    out += '</tr></thead>';
    // Skip separator row (row[1] if it matches --- pattern)
    var startIdx = 1;
    if (rows[1] && /^[\|\s\-:]+$/.test(rows[1])) startIdx = 2;
    // Body
    if (startIdx < rows.length) {
      out += '<tbody>';
      for (var i = startIdx; i < rows.length; i++) {
        var cells = rows[i].split('|').filter(function (c) { return c.trim() !== ''; });
        out += '<tr>';
        cells.forEach(function (c) { out += '<td>' + c.trim() + '</td>'; });
        out += '</tr>';
      }
      out += '</tbody>';
    }
    out += '</table>';
    return out;
  });

  // Headings
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Unordered lists
  html = html.replace(/((?:^- .+$\n?)+)/gm, function (block) {
    var items = block.trim().split('\n');
    var out = '<ul>';
    items.forEach(function (item) {
      out += '<li>' + item.replace(/^- /, '') + '</li>';
    });
    out += '</ul>';
    return out;
  });

  // Ordered lists
  html = html.replace(/((?:^\d+\. .+$\n?)+)/gm, function (block) {
    var items = block.trim().split('\n');
    var out = '<ol>';
    items.forEach(function (item) {
      out += '<li>' + item.replace(/^\d+\.\s*/, '') + '</li>';
    });
    out += '</ol>';
    return out;
  });

  // ---- Phase 3: inline elements ----

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // ---- Phase 4: paragraphs ----

  // Split on double newline for paragraphs, skip blocks that start with HTML tags
  html = html.replace(/\n{2,}/g, '\n\n');
  var blocks = html.split('\n\n');
  html = blocks.map(function (block) {
    block = block.trim();
    if (!block) return '';
    // Don't wrap if it already starts with an HTML block element
    if (/^<(h[1-6]|ul|ol|li|table|thead|tbody|tr|th|td|hr|pre|div|blockquote|\x00)/.test(block)) {
      return block;
    }
    // Convert single newlines to <br> within paragraphs
    block = block.replace(/\n/g, '<br>');
    return '<p>' + block + '</p>';
  }).join('\n');

  // ---- Phase 5: restore code blocks ----
  html = html.replace(/\x00CODEBLOCK(\d+)\x00/g, function (_, idx) {
    var info = codeBlocks[parseInt(idx, 10)];
    var escaped = AgentDB.esc(info.code.replace(/\n$/, ''));
    var langLabel = info.lang ? info.lang : 'code';
    return '<div class="code-header"><span class="code-lang">' + AgentDB.esc(langLabel) +
      '</span><button class="code-copy" onclick="AgentDB.copyToClipboard(this.closest(\'.code-header\').nextElementSibling.textContent)">Copy</button></div>' +
      '<pre class="has-header"><code>' + escaped + '</code></pre>';
  });

  return html;
};

/* ---------------------------------------------------------------
   9. Navigate
   --------------------------------------------------------------- */
AgentDB.navigate = function navigate(viewName) {
  if (!viewName) viewName = 'dashboard';

  // Hide all views
  var views = document.querySelectorAll('.view');
  views.forEach(function (v) { v.classList.remove('active'); });

  // Show target
  var target = document.getElementById('view-' + viewName);
  if (target) {
    target.classList.add('active');
  }

  // Update nav active state
  var links = document.querySelectorAll('nav a[data-view]');
  links.forEach(function (a) {
    var href = a.getAttribute('data-view');
    if (href === viewName) {
      a.classList.add('active');
    } else {
      a.classList.remove('active');
    }
  });

  // Update state and hash
  AgentDB.state.currentView = viewName;
  if (location.hash !== '#' + viewName) {
    history.replaceState(null, '', '#' + viewName);
  }

  // Expand the sidebar group containing this view
  if (typeof AgentDB._expandActiveGroup === 'function') {
    AgentDB._expandActiveGroup(viewName);
  }

  // Close mobile nav only if navigating from a nav link click (not on initial load)
  if (AgentDB._closeNavOnNavigate) {
    var nav = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebar-overlay');
    if (nav) nav.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
  }

  // Call view loader
  if (AgentDB.views[viewName] && typeof AgentDB.views[viewName].load === 'function') {
    AgentDB.views[viewName].load();
  }
};

/* ---------------------------------------------------------------
   10. Toggle Sidebar
   --------------------------------------------------------------- */
AgentDB.toggleSidebar = function toggleSidebar() {
  var isMobile = window.innerWidth <= 768;

  if (isMobile) {
    var nav = document.getElementById('sidebar');
    var overlay = document.querySelector('.sidebar-overlay');
    if (nav) nav.classList.toggle('open');
    if (overlay) overlay.classList.toggle('active');
  } else {
    document.body.classList.toggle('sidebar-collapsed');
    var collapsed = document.body.classList.contains('sidebar-collapsed');
    AgentDB.state.sidebarCollapsed = collapsed;
    localStorage.setItem('sidebar-collapsed', collapsed ? 'true' : 'false');
  }
};

/* ---------------------------------------------------------------
   11. Show loading skeleton
   --------------------------------------------------------------- */
AgentDB.showLoading = function showLoading(containerId) {
  var el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML =
    '<div class="skeleton skeleton-line" style="width:90%"></div>' +
    '<div class="skeleton skeleton-line" style="width:75%"></div>' +
    '<div class="skeleton skeleton-line" style="width:60%"></div>' +
    '<div class="skeleton skeleton-card"></div>' +
    '<div class="skeleton skeleton-line" style="width:80%"></div>' +
    '<div class="skeleton skeleton-line" style="width:50%"></div>';
};

/* ---------------------------------------------------------------
   12. Hide loading
   --------------------------------------------------------------- */
AgentDB.hideLoading = function hideLoading(containerId) {
  var el = document.getElementById(containerId);
  if (!el) return;
  // Remove only skeleton elements
  var skeletons = el.querySelectorAll('.skeleton');
  skeletons.forEach(function (s) { s.remove(); });
};

/* ---------------------------------------------------------------
   Notification badge polling
   --------------------------------------------------------------- */
AgentDB._pollNotifications = function pollNotifications() {
  AgentDB.api('GET', '/api/notifications?read=0&limit=100').then(function (res) {
    var badge = document.getElementById('notif-badge');
    if (!badge) return;
    if (res && res.status === 'ok' && res.data && res.data.length > 0) {
      badge.textContent = res.data.length > 99 ? '99+' : res.data.length;
      badge.style.display = 'inline';
    } else {
      badge.style.display = 'none';
    }
  });
};

/* ---------------------------------------------------------------
   Init
   --------------------------------------------------------------- */
// Apply theme. Reads localStorage first for instant paint (no FOUC),
// then refreshes from server config in case the user changed it on
// another machine. theme_preference values: "auto" | "light" | "dark".
AgentDB.applyTheme = function (pref) {
  if (pref === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else if (pref === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else {
    // "auto" or unknown -> remove attribute, fall through to OS preference
    document.documentElement.removeAttribute('data-theme');
  }
  try { localStorage.setItem('theme-preference', pref || 'auto'); } catch (_) {}
};
AgentDB.applyTheme(localStorage.getItem('theme-preference') || 'auto');

document.addEventListener('DOMContentLoaded', function () {
  // Apply sidebar state
  if (AgentDB.state.sidebarCollapsed && window.innerWidth > 768) {
    document.body.classList.add('sidebar-collapsed');
  }

  // Sync theme from server config (handles cross-device changes; falls
  // back to whatever localStorage already applied above).
  AgentDB.api('GET', '/api/config/theme_preference').then(function (r) {
    if (r.status === 'ok' && r.data && r.data.value) {
      AgentDB.applyTheme(r.data.value);
    }
  });

  // Ensure toast container exists
  if (!document.querySelector('.toast-container')) {
    var tc = document.createElement('div');
    tc.className = 'toast-container';
    document.body.appendChild(tc);
  }

  // Wire nav group toggles (collapsible sidebar groups)
  var groupHeaders = document.querySelectorAll('.nav-group-header');
  groupHeaders.forEach(function (header) {
    header.addEventListener('click', function () {
      var group = header.closest('.nav-group');
      if (group) group.classList.toggle('open');
    });
  });

  // Auto-expand the group containing the active view
  AgentDB._expandActiveGroup = function (viewName) {
    document.querySelectorAll('.nav-group').forEach(function (g) {
      g.classList.remove('has-active');
      var activeLink = g.querySelector('a[data-view="' + viewName + '"]');
      if (activeLink) {
        g.classList.add('open', 'has-active');
      }
    });
  };

  // Wire nav link clicks
  var navLinks = document.querySelectorAll('nav a[data-view]');
  navLinks.forEach(function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      AgentDB._closeNavOnNavigate = true;
      AgentDB.navigate(link.getAttribute('data-view'));
      AgentDB._closeNavOnNavigate = false;
    });
  });

  // Hamburger is wired via inline script in index.html

  // Overlay is wired via inline script in index.html

  // Wire nav toggle button (desktop collapse)
  var navToggle = document.querySelector('.nav-toggle');
  if (navToggle) {
    navToggle.addEventListener('click', function () {
      AgentDB.toggleSidebar();
    });
  }

  // Hash-based navigation
  function onHash() {
    var hash = location.hash.slice(1);
    AgentDB.navigate(hash || 'dashboard');
  }
  window.addEventListener('hashchange', onHash);

  // Initial navigation
  onHash();

  // Poll notification badge every 60 seconds
  AgentDB._pollNotifications();
  setInterval(AgentDB._pollNotifications, 60000);

  // ── Keyboard shortcuts (Vim/GitHub-style two-key navigation) ──
  AgentDB._installKeyboardShortcuts();
});

/* ============================================================
   Keyboard shortcuts
   - "G <letter>" navigates to a view (G prefix held for 1.5s)
   - "?" opens the help overlay
   - "/" focuses the first visible search input
   - Esc closes help overlay
   - Ignored while typing in input/textarea/contenteditable (except Esc)
   ============================================================ */
AgentDB._gShortcuts = {
  d: 'dashboard',
  m: 'memories',
  c: 'chat',
  t: 'tasks',
  s: 'settings',
  n: 'notifications',
  g: 'mindmap',     // (g)raph
  e: 'connect',     // (e)ntities
  k: 'skills',      // (k)ills (skills)
  b: 'dbconsole',   // data(b)ase
  l: 'audit',       // (l)og
  f: 'feedback',
  i: 'import',
  p: 'scheduler',   // (p)lanner
  o: 'editor',      // markd(o)wn editor
  r: 'threads',     // th(r)eads
};

AgentDB._installKeyboardShortcuts = function () {
  var gPending = false;
  var gTimer = null;

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function clearGPrefix() {
    gPending = false;
    if (gTimer) { clearTimeout(gTimer); gTimer = null; }
  }

  document.addEventListener('keydown', function (e) {
    // Esc always works (closes help overlay or entity drawer)
    if (e.key === 'Escape') {
      AgentDB._closeShortcutHelp();
      AgentDB._closeEntityDetail();
      clearGPrefix();
      return;
    }
    // Don't intercept while typing
    if (isTypingTarget(e.target)) return;
    // Ignore modified key combos except plain G/?, /, etc.
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    var k = e.key;

    if (gPending) {
      var target = AgentDB._gShortcuts[k.toLowerCase()];
      clearGPrefix();
      if (target) {
        e.preventDefault();
        AgentDB.navigate(target);
      }
      return;
    }

    if (k === 'g' || k === 'G') {
      gPending = true;
      gTimer = setTimeout(clearGPrefix, 1500);
      return;
    }
    if (k === '?') {
      e.preventDefault();
      AgentDB._openShortcutHelp();
      return;
    }
    if (k === '/') {
      // Focus first visible search input in the active view
      var active = document.querySelector('.view.active');
      if (!active) return;
      var search = active.querySelector(
        'input[type="search"], input[placeholder*="Search" i], input[placeholder*="search" i]'
      );
      if (search) {
        e.preventDefault();
        search.focus();
        search.select && search.select();
      }
    }
  });
};

AgentDB._openShortcutHelp = function () {
  if (document.getElementById('shortcut-help-overlay')) return;
  var entries = Object.keys(AgentDB._gShortcuts).map(function (k) {
    return { key: 'G ' + k.toUpperCase(), label: AgentDB._gShortcuts[k] };
  });
  var rows = entries.map(function (e) {
    return '<tr><td style="font-family:var(--mono);padding:4px 12px 4px 0">' +
           AgentDB.esc(e.key) + '</td><td>' + AgentDB.esc(e.label) + '</td></tr>';
  }).join('');
  rows += '<tr><td colspan="2" style="padding-top:10px;color:var(--text2);font-size:11px">— Other —</td></tr>';
  rows += '<tr><td style="font-family:var(--mono);padding:4px 12px 4px 0">?</td><td>Show this help</td></tr>';
  rows += '<tr><td style="font-family:var(--mono);padding:4px 12px 4px 0">/</td><td>Focus search in current view</td></tr>';
  rows += '<tr><td style="font-family:var(--mono);padding:4px 12px 4px 0">Esc</td><td>Close overlay</td></tr>';
  rows += '<tr><td style="font-family:var(--mono);padding:4px 12px 4px 0">Enter</td><td>Send (in chat)</td></tr>';
  rows += '<tr><td style="font-family:var(--mono);padding:4px 12px 4px 0">Shift+Enter</td><td>Newline (in chat)</td></tr>';

  var overlay = document.createElement('div');
  overlay.id = 'shortcut-help-overlay';
  overlay.style.cssText =
    'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;' +
    'display:flex;align-items:center;justify-content:center';
  overlay.innerHTML =
    '<div style="background:var(--bg2);border-radius:var(--radius);padding:24px;' +
    'min-width:360px;max-width:560px;max-height:80vh;overflow:auto;' +
    'box-shadow:0 8px 32px var(--shadow)">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">' +
    '<h3 style="margin:0">Keyboard Shortcuts</h3>' +
    '<button class="btn btn-sm" id="shortcut-help-close">Close</button></div>' +
    '<table style="width:100%;font-size:13px">' + rows + '</table>' +
    '<div style="font-size:11px;color:var(--text2);margin-top:12px">' +
    'Press <kbd>?</kbd> any time outside a text input to reopen this.</div>' +
    '</div>';
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) AgentDB._closeShortcutHelp();
  });
  document.body.appendChild(overlay);
  var closeBtn = document.getElementById('shortcut-help-close');
  if (closeBtn) closeBtn.addEventListener('click', AgentDB._closeShortcutHelp);
};

AgentDB._closeShortcutHelp = function () {
  var o = document.getElementById('shortcut-help-overlay');
  if (o) o.remove();
};

/* ============================================================
   Entity detail drawer
   Right-side slide-in drawer with tabs:
     Overview / Memories / Relations / Co-occurring
   Reusable from any view via AgentDB.openEntityDetail(entityId).
   ============================================================ */
AgentDB.openEntityDetail = async function (entityId) {
  if (!entityId) return;
  AgentDB._closeEntityDetail();

  var overlay = document.createElement('div');
  overlay.id = 'entity-detail-overlay';
  overlay.style.cssText =
    'position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:9990;' +
    'display:flex;justify-content:flex-end';
  overlay.innerHTML =
    '<div id="entity-detail-drawer" style="width:min(560px,100vw);height:100%;' +
    'background:var(--bg2);box-shadow:-8px 0 32px var(--shadow);overflow-y:auto;' +
    'padding:20px;animation:entity-slide-in 0.18s ease-out">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">' +
    '<div style="display:flex;align-items:center;gap:10px">' +
    '<h3 style="margin:0">Entity</h3>' +
    '<span style="color:var(--text2);font-size:12px;font-family:var(--mono)">' +
    AgentDB.esc(entityId.slice(0, 8)) + '</span></div>' +
    '<button class="btn btn-sm" id="entity-detail-close">Close</button>' +
    '</div>' +
    '<div id="entity-detail-body"><div class="spinner"></div></div>' +
    '</div>';
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) AgentDB._closeEntityDetail();
  });
  document.body.appendChild(overlay);
  document.getElementById('entity-detail-close').addEventListener(
    'click', AgentDB._closeEntityDetail);

  // Inject keyframes once
  if (!document.getElementById('entity-detail-anim')) {
    var st = document.createElement('style');
    st.id = 'entity-detail-anim';
    st.textContent =
      '@keyframes entity-slide-in {' +
      ' from { transform: translateX(40px); opacity: 0; }' +
      ' to { transform: translateX(0); opacity: 1; } }';
    document.head.appendChild(st);
  }

  var r = await AgentDB.api('GET', '/api/entities/' + encodeURIComponent(entityId) + '/detail');
  var body = document.getElementById('entity-detail-body');
  if (!body) return; // closed before fetch resolved
  if (r.status !== 'ok' || !r.data) {
    body.innerHTML = '<div style="color:var(--red);font-size:13px">' +
      AgentDB.esc(r.error || 'Failed to load entity') + '</div>';
    return;
  }
  AgentDB._renderEntityDetail(body, r.data);
};

AgentDB._closeEntityDetail = function () {
  var o = document.getElementById('entity-detail-overlay');
  if (o) o.remove();
};

AgentDB._renderEntityDetail = function (body, data) {
  var ent = data.entity || {};
  var memories = data.memories || [];
  var relations = data.relations || [];
  var coOccurring = data.co_occurring || [];

  // Aliases come from JSON column; coerce to array
  var aliases = ent.aliases;
  if (typeof aliases === 'string') {
    try { aliases = JSON.parse(aliases); } catch (_) { aliases = []; }
  }
  if (!Array.isArray(aliases)) aliases = [];

  function tierBadge(tier) {
    var color = tier === 'long_term' ? '#10b981'
              : tier === 'midterm' ? '#8b5cf6' : '#3b82f6';
    return '<span style="background:' + color + ';color:#fff;padding:1px 6px;' +
           'border-radius:6px;font-size:10px;font-family:var(--mono)">' +
           AgentDB.esc(tier) + '</span>';
  }

  var html = '';

  // ── Overview ──
  html += '<div style="background:var(--bg3);padding:12px;border-radius:6px;margin-bottom:12px">';
  html += '<div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap">';
  html += '<input type="text" id="ent-name" value="' + AgentDB.esc(ent.canonical_name || '') +
          '" style="font-size:18px;font-weight:600;border:none;background:transparent;flex:1;min-width:200px;padding:4px 6px;border-radius:4px" title="Click to edit canonical name">';
  if (ent.entity_type) {
    html += '<span style="background:var(--bg2);padding:2px 8px;border-radius:8px;font-size:11px;font-family:var(--mono)">' +
            AgentDB.esc(ent.entity_type) + '</span>';
  }
  html += '</div>';

  html += '<div style="display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:12px;margin-top:8px">';
  if (ent.first_seen) {
    html += '<div style="color:var(--text2)">First seen:</div><div>' + AgentDB.esc(ent.first_seen) + '</div>';
  }
  if (ent.last_seen) {
    html += '<div style="color:var(--text2)">Last seen:</div><div>' + AgentDB.esc(ent.last_seen) + '</div>';
  }
  if (ent.created_at) {
    html += '<div style="color:var(--text2)">Created:</div><div>' + AgentDB.esc(ent.created_at) + '</div>';
  }
  html += '</div>';

  // Aliases (editable)
  html += '<div style="margin-top:10px">';
  html += '<div style="font-size:12px;color:var(--text2);margin-bottom:4px">Aliases (comma-separated)</div>';
  html += '<input type="text" id="ent-aliases" value="' + AgentDB.esc(aliases.join(', ')) +
          '" style="width:100%;font-size:13px" placeholder="No aliases">';
  html += '</div>';

  html += '<div style="display:flex;gap:6px;margin-top:10px">';
  html += '<button class="btn btn-sm btn-primary" id="ent-save">Save changes</button>';
  html += '<button class="btn btn-sm" style="color:var(--red)" id="ent-delete">Delete</button>';
  html += '</div>';
  html += '</div>';

  // ── Tabs ──
  html += '<div class="tabs" id="ent-tabs" style="margin-bottom:12px">';
  html += '<button class="tab active" data-ent-tab="memories">Memories <span style="opacity:0.6">' + memories.length + '</span></button>';
  html += '<button class="tab" data-ent-tab="relations">Relations <span style="opacity:0.6">' + relations.length + '</span></button>';
  html += '<button class="tab" data-ent-tab="co">Co-occurring <span style="opacity:0.6">' + coOccurring.length + '</span></button>';
  html += '</div>';

  // Memories panel
  html += '<div data-ent-panel="memories">';
  html += '<div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap">';
  html += '<button class="btn btn-sm tier-filter active" data-tier-filter="all">All</button>';
  html += '<button class="btn btn-sm tier-filter" data-tier-filter="midterm">Midterm</button>';
  html += '<button class="btn btn-sm tier-filter" data-tier-filter="long_term">Long-term</button>';
  html += '</div>';
  if (!memories.length) {
    html += '<div style="color:var(--text2);font-size:12px;padding:8px 0">No memories reference this entity yet (short-term memories don\'t carry entity links).</div>';
  } else {
    html += '<div id="ent-memories-list">';
    memories.forEach(function (m) {
      var content = m.content || '';
      if (content.length > 240) content = content.substring(0, 240) + '…';
      html += '<div class="ent-memory-row" data-tier="' + AgentDB.esc(m.tier) + '" style="background:var(--bg3);padding:8px 10px;border-radius:6px;margin-bottom:6px">';
      html += '<div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px">';
      html += tierBadge(m.tier);
      html += '<span style="font-size:11px;color:var(--text2)">' +
              AgentDB.esc(m.created_at || m.timestamp || '') + '</span>';
      html += '</div>';
      html += '<div style="font-size:12px;line-height:1.4">' + AgentDB.esc(content) + '</div>';
      if (typeof m.confidence === 'number') {
        html += '<div style="font-size:11px;color:var(--text2);margin-top:2px">confidence: ' +
                m.confidence.toFixed(2) + '</div>';
      }
      html += '</div>';
    });
    html += '</div>';
  }
  html += '</div>';

  // Relations panel
  html += '<div data-ent-panel="relations" style="display:none">';
  if (!relations.length) {
    html += '<div style="color:var(--text2);font-size:12px;padding:8px 0">No relations.</div>';
  } else {
    relations.forEach(function (rel) {
      var weight = (typeof rel.weight === 'number') ? rel.weight.toFixed(2) : '—';
      html += '<div style="background:var(--bg3);padding:8px 10px;border-radius:6px;margin-bottom:6px;display:flex;justify-content:space-between;gap:8px;align-items:center">';
      html += '<div style="flex:1;min-width:0">';
      html += '<div style="font-size:13px"><span style="font-family:var(--mono);font-size:11px;background:var(--bg2);padding:1px 6px;border-radius:4px">' +
              AgentDB.esc(rel.relation_type || rel.edge_type || 'related') + '</span> ' +
              AgentDB.esc(rel.other_name || rel.other_id || '') + '</div>';
      html += '<div style="font-size:11px;color:var(--text2)">' +
              'target: ' + AgentDB.esc(rel.other_table || '') +
              ' • weight ' + weight + '</div>';
      html += '</div>';
      // Drill into another entity if the other side is an entity
      if (rel.other_table === 'entities') {
        html += '<button class="btn btn-sm" data-open-entity="' + AgentDB.esc(rel.other_id) + '">Open</button>';
      }
      html += '</div>';
    });
  }
  html += '</div>';

  // Co-occurring panel
  html += '<div data-ent-panel="co" style="display:none">';
  if (!coOccurring.length) {
    html += '<div style="color:var(--text2);font-size:12px;padding:8px 0">No co-occurring entities yet (need at least one shared mid/long-term memory).</div>';
  } else {
    coOccurring.forEach(function (co) {
      var e = co.entity || {};
      html += '<div style="background:var(--bg3);padding:8px 10px;border-radius:6px;margin-bottom:6px;display:flex;justify-content:space-between;gap:8px;align-items:center">';
      html += '<div><b>' + AgentDB.esc(e.canonical_name || e.id) + '</b>';
      if (e.entity_type) {
        html += ' <span style="font-size:11px;color:var(--text2);font-family:var(--mono)">' +
                AgentDB.esc(e.entity_type) + '</span>';
      }
      html += '<div style="font-size:11px;color:var(--text2)">co-occurs in ' +
              co.co_occurrence_count + ' memor' +
              (co.co_occurrence_count === 1 ? 'y' : 'ies') + '</div></div>';
      html += '<button class="btn btn-sm" data-open-entity="' + AgentDB.esc(e.id) + '">Open</button>';
      html += '</div>';
    });
  }
  html += '</div>';

  body.innerHTML = html;

  // Wire tabs
  body.querySelectorAll('[data-ent-tab]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      body.querySelectorAll('[data-ent-tab]').forEach(function (b) {
        b.classList.remove('active');
      });
      btn.classList.add('active');
      var which = btn.dataset.entTab;
      body.querySelectorAll('[data-ent-panel]').forEach(function (p) {
        p.style.display = p.dataset.entPanel === which ? 'block' : 'none';
      });
    });
  });

  // Wire tier filter
  body.querySelectorAll('[data-tier-filter]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      body.querySelectorAll('[data-tier-filter]').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      var tf = btn.dataset.tierFilter;
      body.querySelectorAll('.ent-memory-row').forEach(function (row) {
        row.style.display = (tf === 'all' || row.dataset.tier === tf) ? '' : 'none';
      });
    });
  });

  // Wire drill-down
  body.querySelectorAll('[data-open-entity]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      AgentDB.openEntityDetail(btn.dataset.openEntity);
    });
  });

  // Wire save / delete
  var saveBtn = document.getElementById('ent-save');
  if (saveBtn) saveBtn.addEventListener('click', async function () {
    var newName = document.getElementById('ent-name').value.trim();
    var aliasStr = document.getElementById('ent-aliases').value.trim();
    var aliasArr = aliasStr ? aliasStr.split(',').map(function (a) { return a.trim(); }).filter(Boolean) : [];
    var payload = { canonical_name: newName, aliases: aliasArr };
    var r = await AgentDB.api('PUT', '/api/entities/' + encodeURIComponent(ent.id), payload);
    if (r.status === 'ok') {
      AgentDB.toast('Entity updated', 'success');
      AgentDB.openEntityDetail(ent.id); // reload with fresh data
    } else {
      AgentDB.toast('Update failed: ' + (r.error || 'unknown'), 'error');
    }
  });
  var delBtn = document.getElementById('ent-delete');
  if (delBtn) delBtn.addEventListener('click', async function () {
    if (!confirm('Delete this entity? Relations and references remain in place but the entity record will be removed.')) return;
    var r = await AgentDB.api('DELETE', '/api/entities/' + encodeURIComponent(ent.id));
    if (r.status === 'ok') {
      AgentDB.toast('Entity deleted', 'success');
      AgentDB._closeEntityDetail();
    } else {
      AgentDB.toast('Delete failed: ' + (r.error || 'unknown'), 'error');
    }
  });
};
