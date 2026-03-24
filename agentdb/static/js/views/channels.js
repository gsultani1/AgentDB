(function() {
  const V = AgentDB.views.channels = {};
  const el = () => document.getElementById('view-channels');

  V.load = async function() {
    el().innerHTML = `
      <div class="view-header">
        <h2>External Channels</h2>
        <button class="btn btn-primary" id="channels-new-btn">+ New Channel</button>
      </div>
      <div id="channels-list" class="card-list"></div>
      <div id="channels-form" style="display:none"></div>
    `;
    document.getElementById('channels-new-btn').addEventListener('click', showNewForm);
    await loadChannels();
  };

  async function loadChannels() {
    const container = document.getElementById('channels-list');
    container.innerHTML = '<div class="loading">Loading channels...</div>';
    const res = await AgentDB.api('GET', '/api/channels');
    const channels = res?.data || res || [];

    if (!channels.length) {
      container.innerHTML = '<div class="empty">No channels configured. Add one to connect external messaging.</div>';
      return;
    }
    container.innerHTML = channels.map(ch => `
      <div class="card channel-card">
        <div class="card-header">
          <strong>${AgentDB.esc(ch.name)}</strong>
          <span class="badge badge-${ch.enabled !== false ? 'green' : 'gray'}">${ch.enabled !== false ? 'Active' : 'Disabled'}</span>
          <span class="badge">${AgentDB.esc(ch.channel_type || 'unknown')}</span>
        </div>
        <div class="card-meta">
          <span>Agent: ${AgentDB.esc(ch.agent_id || 'default')}</span>
          <span>Created: ${AgentDB.formatDate(ch.created_at)}</span>
        </div>
        <div class="card-actions">
          <button class="btn btn-sm" onclick="AgentDB.views.channels.viewMessages('${ch.id}')">Messages</button>
          <button class="btn btn-sm btn-danger" onclick="AgentDB.views.channels.deleteChannel('${ch.id}')">Delete</button>
        </div>
      </div>
    `).join('');
  }

  function showNewForm() {
    const container = document.getElementById('channels-form');
    container.style.display = 'block';
    container.innerHTML = `
      <div class="card">
        <h3>New Channel</h3>
        <div class="form-group">
          <label>Name</label>
          <input type="text" id="ch-name" class="form-input" placeholder="Channel name">
        </div>
        <div class="form-group">
          <label>Type</label>
          <select id="ch-type" class="form-input">
            <option value="email">Email (IMAP/SMTP)</option>
            <option value="whatsapp">WhatsApp (Twilio)</option>
            <option value="sms">SMS (Twilio)</option>
            <option value="imessage">iMessage (macOS)</option>
          </select>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" id="ch-create-btn">Create</button>
          <button class="btn" onclick="document.getElementById('channels-form').style.display='none'">Cancel</button>
        </div>
      </div>
    `;
    document.getElementById('ch-create-btn').addEventListener('click', async () => {
      const name = document.getElementById('ch-name').value.trim();
      const channel_type = document.getElementById('ch-type').value;
      if (!name) return AgentDB.toast('Name is required', 'error');
      const res = await AgentDB.api('POST', '/api/channels', { name, channel_type });
      if (res && !res.error) {
        AgentDB.toast('Channel created', 'success');
        container.style.display = 'none';
        await loadChannels();
      } else {
        AgentDB.toast(res?.error || 'Failed', 'error');
      }
    });
  }

  V.viewMessages = async function(channelId) {
    const container = document.getElementById('channels-list');
    container.innerHTML = '<div class="loading">Loading messages...</div>';
    const res = await AgentDB.api('GET', `/api/channels/${channelId}/messages?limit=50`);
    const msgs = res?.data || res || [];
    container.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h3>Messages</h3>
          <button class="btn btn-sm" onclick="AgentDB.views.channels.load()">Back</button>
        </div>
        ${msgs.length ? msgs.map(m => `
          <div class="thread-msg">
            <span class="badge badge-${m.direction === 'inbound' ? 'blue' : 'green'}">${m.direction}</span>
            <span class="text-secondary">${AgentDB.formatDate(m.created_at)}</span>
            ${m.sender ? `<span>From: ${AgentDB.esc(m.sender)}</span>` : ''}
            <div>${AgentDB.esc((m.content || '').substring(0, 500))}</div>
          </div>
        `).join('') : '<div class="empty">No messages.</div>'}
      </div>
    `;
  };

  V.deleteChannel = async function(id) {
    if (!confirm('Delete this channel and all its messages?')) return;
    await AgentDB.api('DELETE', `/api/channels/${id}`);
    AgentDB.toast('Channel deleted', 'success');
    await loadChannels();
  };
})();
