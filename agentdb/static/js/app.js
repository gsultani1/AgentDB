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
AgentDB.api = async function api(method, path, body) {
  try {
    const opts = {
      method: method.toUpperCase(),
      headers: {},
    };
    if (body !== undefined && body !== null) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    const data = await res.json();
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

  // Close mobile nav
  var nav = document.getElementById('sidebar');
  var overlay = document.querySelector('.sidebar-overlay');
  if (nav) nav.classList.remove('open');
  if (overlay) overlay.classList.remove('active');

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
document.addEventListener('DOMContentLoaded', function () {
  // Apply sidebar state
  if (AgentDB.state.sidebarCollapsed && window.innerWidth > 768) {
    document.body.classList.add('sidebar-collapsed');
  }

  // Ensure toast container exists
  if (!document.querySelector('.toast-container')) {
    var tc = document.createElement('div');
    tc.className = 'toast-container';
    document.body.appendChild(tc);
  }

  // Wire nav link clicks
  var navLinks = document.querySelectorAll('nav a[data-view][data-view]');
  navLinks.forEach(function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      AgentDB.navigate(link.getAttribute('data-view'));
    });
  });

  // Wire hamburger
  var hamburger = document.querySelector('.hamburger');
  if (hamburger) {
    hamburger.addEventListener('click', function () {
      AgentDB.toggleSidebar();
    });
  }

  // Wire sidebar overlay click to close
  var overlay = document.querySelector('.sidebar-overlay');
  if (overlay) {
    overlay.addEventListener('click', function () {
      var nav = document.getElementById('sidebar');
      if (nav) nav.classList.remove('open');
      overlay.classList.remove('active');
    });
  }

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
});
