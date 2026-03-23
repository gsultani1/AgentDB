(function() {
  const V = AgentDB.views.editor = {};
  const el = () => document.getElementById('view-editor');

  const TEMPLATES = {
    memory: '---\ntype: memory\ncategory: fact\ntags: []\nentities: []\n---\n\nYour memory content here.',
    instruction: '---\ntype: instruction\npriority: normal\ntags: [behavior]\n---\n\nYour behavioral directive here.',
    skill: '---\ntype: skill\nexecution_type: code_procedure\nlanguage: python\ndependencies: []\n---\n\n# Skill Name\n\nDescription.\n\n```python\ndef execute(input):\n    return result\n```',
    knowledge: '---\ntype: knowledge\ntitle: Document Title\ntags: []\nentities: []\n---\n\n## Section One\n\nContent.\n\n## Section Two\n\nMore content.',
  };

  V.load = function() {
    el().innerHTML = `
      <h2 style="margin-bottom:16px">Markdown Editor</h2>
      <div style="margin-bottom:12px;display:flex;gap:8px;align-items:center">
        <select id="editor-type" style="width:160px">
          <option value="memory">Memory</option>
          <option value="instruction">Instruction</option>
          <option value="skill">Skill</option>
          <option value="knowledge">Knowledge</option>
        </select>
        <button class="btn btn-primary" id="editor-submit-btn">Submit</button>
      </div>
      <div class="editor-layout">
        <div class="editor-pane"><textarea id="editor-textarea" placeholder="Write your markdown here..."></textarea></div>
        <div class="preview-pane" id="editor-preview"></div>
      </div>`;
    document.getElementById('editor-type').onchange = V.updateTemplate;
    document.getElementById('editor-textarea').oninput = V.updatePreview;
    document.getElementById('editor-submit-btn').onclick = V.submit;
    V.updateTemplate();
  };

  V.updateTemplate = function() {
    const type = document.getElementById('editor-type').value;
    document.getElementById('editor-textarea').value = TEMPLATES[type] || '';
    V.updatePreview();
  };

  V.updatePreview = function() {
    const text = document.getElementById('editor-textarea').value;
    document.getElementById('editor-preview').innerHTML = AgentDB.renderMarkdown(text);
  };

  V.submit = async function() {
    const text = document.getElementById('editor-textarea').value;
    const r = await AgentDB.api('POST', '/api/markdown/submit', { text });
    if (r.data && r.data.status === 'ok') {
      AgentDB.toast(r.data.type + ' ' + r.data.action + ': ' + (r.data.id || r.data.skill_id || r.data.document_entity_id), 'success');
    } else {
      AgentDB.toast('Error: ' + JSON.stringify(r.data?.errors || r.error), 'error');
    }
  };
})();
