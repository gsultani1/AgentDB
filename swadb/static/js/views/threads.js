(function() {
  const V = swadb.views.threads = {};
  const el = () => document.getElementById('view-threads');

  V.load = async function() {
    el().innerHTML = `
      <div class="view-header">
        <h2>Projects</h2>
        <button class="btn btn-primary" id="threads-new-btn">+ New Project</button>
      </div>
      <div id="threads-list" class="card-list"></div>
      <div id="threads-detail" style="display:none"></div>
    `;
    document.getElementById('threads-new-btn').addEventListener('click', showNewForm);
    await loadThreads();
  };

  async function loadThreads() {
    const container = document.getElementById('threads-list');
    container.innerHTML = '<div class="loading">Loading projects...</div>';
    const res = await swadb.api('GET', '/api/threads?limit=100');
    if (!res || res.error) {
      container.innerHTML = '<div class="empty">No projects found</div>';
      return;
    }
    const threads = res.data || res || [];
    if (!threads.length) {
      container.innerHTML = '<div class="empty">No projects yet. Create one to organize conversations.</div>';
      return;
    }
    container.innerHTML = threads.map(t => `
      <div class="card thread-card" data-id="${swadb.esc(t.id)}">
        <div class="card-header">
          <strong>${swadb.esc(t.name)}</strong>
          <span class="badge badge-${t.status === 'active' ? 'green' : 'gray'}">${t.status || 'active'}</span>
        </div>
        <div class="card-meta">
          ${t.summary ? `<div>${swadb.esc(t.summary)}</div>` : ''}
          <span>Agent: ${swadb.esc(t.agent_id || 'default')}</span>
          <span>Created: ${swadb.formatDate(t.created_at)}</span>
          ${t.last_active ? `<span>Last active: ${swadb.formatDate(t.last_active)}</span>` : ''}
        </div>
        <div class="card-actions">
          <button class="btn btn-sm btn-primary" onclick="swadb.views.threads.chatInProject('${t.id}')">Chat</button>
          <button class="btn btn-sm" onclick="swadb.views.threads.viewThread('${t.id}')">View</button>
          <button class="btn btn-sm btn-danger" onclick="swadb.views.threads.deleteThread('${t.id}')">Delete</button>
        </div>
      </div>
    `).join('');
  }

  function showNewForm() {
    const container = document.getElementById('threads-detail');
    container.style.display = 'block';
    container.innerHTML = `
      <div class="card">
        <h3>New Project</h3>
        <div class="form-group">
          <label>Name</label>
          <input type="text" id="thread-name" class="form-input" placeholder="Project name">
        </div>
        <div class="form-group">
          <label>Description</label>
          <input type="text" id="thread-desc" class="form-input" placeholder="Optional description">
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" id="thread-create-btn">Create</button>
          <button class="btn" onclick="document.getElementById('threads-detail').style.display='none'">Cancel</button>
        </div>
      </div>
    `;
    document.getElementById('thread-create-btn').addEventListener('click', async () => {
      const name = document.getElementById('thread-name').value.trim();
      if (!name) return swadb.toast('Name is required', 'error');
      const res = await swadb.api('POST', '/api/threads', {
        name,
        description: document.getElementById('thread-desc').value.trim() || undefined,
      });
      if (res && !res.error) {
        swadb.toast('Project created', 'success');
        container.style.display = 'none';
        await loadThreads();
      } else {
        swadb.toast(res?.error || 'Failed to create project', 'error');
      }
    });
  }

  V.viewThread = async function(id) {
    const container = document.getElementById('threads-detail');
    container.style.display = 'block';
    container.innerHTML = '<div class="loading">Loading project...</div>';
    const res = await swadb.api('GET', `/api/threads/${id}`);
    const msgs = await swadb.api('GET', `/api/threads/${id}/messages?limit=50`);
    const thread = res?.data || res;
    const messages = msgs?.data || msgs || [];
    container.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h3>${swadb.esc(thread?.name || id)}</h3>
          <button class="btn btn-sm" onclick="document.getElementById('threads-detail').style.display='none'">Close</button>
        </div>
        ${thread?.summary ? `<p class="text-secondary">${swadb.esc(thread.summary)}</p>` : ''}
        <h4>Messages (${messages.length})</h4>
        <div class="thread-messages">
          ${messages.length ? messages.map(m => `
            <div class="thread-msg">
              <span class="text-secondary">${swadb.formatDate(m.timestamp || m.created_at)}</span>
              <span class="badge">${m.source || m.role || 'message'}</span>
              <div>${swadb.esc((m.content || '').substring(0, 300))}</div>
            </div>
          `).join('') : '<div class="empty">No messages in this project yet.</div>'}
        </div>
      </div>
    `;
  };

  V.chatInProject = function(id) {
    swadb.state.chatThreadId = id;
    swadb.state.chatSessionId = null;
    swadb.state.chatHistory = [];
    swadb.navigate('chat');
  };

  V.deleteThread = async function(id) {
    if (!confirm('Delete this project?')) return;
    const res = await swadb.api('DELETE', `/api/threads/${id}`);
    if (res && !res.error) {
      swadb.toast('Project deleted', 'success');
      await loadThreads();
    }
  };
})();
