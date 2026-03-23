(function() {
  const V = AgentDB.views.notifications = {};
  const el = () => document.getElementById('view-notifications');

  V.load = function() {
    el().innerHTML = `
      <h2 style="margin-bottom:16px">Notifications</h2>
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap">
        <select id="notif-priority" style="width:130px">
          <option value="">All Priorities</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>
        <select id="notif-read" style="width:120px">
          <option value="">All</option>
          <option value="0">Unread</option>
          <option value="1">Read</option>
        </select>
        <button class="btn btn-primary" id="notif-filter-btn">Filter</button>
        <button class="btn btn-danger" id="notif-dismiss-btn">Dismiss All Read</button>
      </div>
      <div id="notif-list"></div>`;
    document.getElementById('notif-filter-btn').onclick = V.loadList;
    document.getElementById('notif-dismiss-btn').onclick = V.dismissAll;
    V.loadList();
  };

  V.loadList = async function() {
    const params = new URLSearchParams();
    const pri = document.getElementById('notif-priority').value;
    const read = document.getElementById('notif-read').value;
    if (pri) params.set('priority', pri);
    if (read !== '') params.set('read', read);
    params.set('limit', '50');
    const r = await AgentDB.api('GET', '/api/notifications?' + params.toString());
    const items = r.data?.notifications || r.data || [];
    const box = document.getElementById('notif-list');
    if (!items.length) {
      box.innerHTML = '<p style="color:var(--text2)">No notifications.</p>';
      return;
    }
    let html = '';
    items.forEach(n => {
      const p = n.priority || 'medium';
      const borderColor = p === 'critical' ? 'var(--red)' : p === 'high' ? 'var(--yellow)' : p === 'medium' ? 'var(--text)' : 'var(--text2)';
      const isRead = n.read || n.is_read;
      const opacity = isRead ? 'opacity:0.6;' : '';
      html += `<div class="card" style="margin-bottom:10px;padding:14px;border-left:4px solid ${borderColor};${opacity}">
        <div style="display:flex;justify-content:space-between;align-items:start">
          <div>
            <strong>${AgentDB.esc(n.title || n.message || 'Notification')}</strong>
            <div style="margin-top:4px;font-size:0.85em;color:var(--text2)">
              ${AgentDB.esc(n.trigger_type || '')} | <span style="font-weight:600">${AgentDB.esc(p)}</span>
            </div>
            <div style="margin-top:2px;font-size:0.8em;color:var(--text2)">${AgentDB.formatDate(n.created_at || n.timestamp)}</div>
            ${n.body ? '<p style="margin-top:6px;font-size:0.9em">' + AgentDB.esc(n.body) + '</p>' : ''}
          </div>
          <div>
            ${isRead
              ? '<span class="badge">read</span>'
              : '<button class="btn btn-sm" onclick="AgentDB.views.notifications.markRead(\'' + AgentDB.esc(n.id || n.notification_id) + '\')">Mark Read</button>'}
          </div>
        </div>
      </div>`;
    });
    box.innerHTML = html;
  };

  V.markRead = async function(id) {
    await AgentDB.api('PUT', '/api/notifications/' + id + '/read');
    V.loadList();
    V.updateBadge();
  };

  V.dismissAll = async function() {
    await AgentDB.api('POST', '/api/notifications/dismiss');
    AgentDB.toast('Read notifications dismissed', 'success');
    V.loadList();
    V.updateBadge();
  };

  V.updateBadge = async function() {
    const r = await AgentDB.api('GET', '/api/notifications?read=0&limit=100');
    const items = r.data?.notifications || r.data || [];
    const badge = document.getElementById('notif-badge');
    if (badge) {
      badge.textContent = items.length || '';
      badge.style.display = items.length ? 'inline-block' : 'none';
    }
  };

  AgentDB.updateNotifBadge = V.updateBadge;
})();
