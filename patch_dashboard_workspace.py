with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update CSS:
old_css = """    .chat-view {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100vh;
      z-index: 1;
    }"""

new_css = """    .chat-view, .staging-view {
      flex: 1;
      display: flex;
      flex-direction: column;
      height: 100vh;
      z-index: 1;
    }

    /* Staging Workspace Grid Styles */
    .staging-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 8px;
      cursor: pointer;
      transition: all 0.2s ease;
      position: relative;
      user-select: none;
    }
    .staging-card:hover {
      border-color: var(--border-focus);
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .staging-card.selected {
      border-color: var(--accent-cyan);
      background: rgba(57, 208, 216, 0.04);
      box-shadow: 0 0 10px rgba(57, 208, 216, 0.05);
    }
    .staging-card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
    }
    .staging-card-title {
      font-size: 13px;
      font-weight: 700;
      color: var(--text-primary);
      line-height: 1.4;
      word-break: break-word;
      max-height: 38px;
      overflow: hidden;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }
    .staging-card-checkbox {
      accent-color: var(--accent-cyan);
      width: 15px;
      height: 15px;
      cursor: pointer;
    }
    .staging-card-snippet {
      font-size: 11px;
      color: var(--text-dim);
      line-height: 1.4;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      height: 48px;
      margin: 4px 0;
    }
    .staging-card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 10.5px;
      color: var(--text-muted);
      border-top: 1px solid rgba(255,255,255,0.03);
      padding-top: 8px;
      margin-top: 4px;
    }"""

content = content.replace(old_css, new_css, 1)
print("CSS updated successfully.")

# 2. Update central workspace HTML structure:
old_workspace = """  <!-- ── CENTRAL WORKSPACE ───────────────────────────────────────── -->
  <div class="main-workspace">
    
    <!-- Central Chat View -->
    <div class="chat-view">
      <header class="chat-header">
        <div style="font-weight:700; font-size:14px;" id="chat-title-context">Workspace Intelligence</div>
        <div class="workspace-stats">
          <div class="stat-badge">Total: <strong id="stats-total">—</strong></div>
          <div class="stat-badge" style="color:var(--accent-emerald);">Active: <strong id="stats-active">—</strong></div>
          <div class="stat-badge" style="color:var(--accent-pink);">Signed: <strong id="stats-signed">—</strong></div>
        </div>
      </header>

      <!-- Chat Conversation Stream -->
      <div class="chat-stream" id="chat-messages">
        <!-- Default Welcome Area -->
        <div class="chat-welcome" id="chat-welcome">
          <div class="welcome-icon-large">🌱</div>
          <h2 class="welcome-title">Seed Reflections Workspace</h2>
          <p class="welcome-desc">
            This is your central workspace. Paste a long AI conversation transcript or import a JSON export file to extract new sparks. Type a question below to chat with your seed database.
          </p>
          <div class="chat-suggestions">
            <button class="chat-suggestion" onclick="triggerSuggestion('What seeds did I abandon?')">What seeds did I abandon?</button>
            <button class="chat-suggestion" onclick="triggerSuggestion('What is my most active seed?')">What is my most active seed?</button>
            <button class="chat-suggestion" onclick="triggerSuggestion('Give me a status overview')">Give me a status overview</button>
          </div>
        </div>
      </div>

      <!-- Chat Input Area -->
      <div class="chat-input-area">
        <div class="chat-input-wrapper">
          <div class="detect-badge" id="transcript-detect-badge">⚡ Detected AI conversation transcript. Send to reflect.</div>
          <div class="chat-input-row">
            <label for="import-file" class="btn-icon" style="margin:0; font-size:15px; font-weight:normal;" title="Attach JSON Export">📎</label>
            <input type="file" id="import-file" accept=".json" style="display:none" onchange="handleFileImport(this.files)">
            <textarea class="chat-input-box" id="chat-input" placeholder="Paste an AI transcript or type a query..." rows="1" oninput="handleInputDetection()" onkeydown="handleInputKeydown(event)"></textarea>
            <button class="btn purple-grad" style="padding: 8px 16px; border-radius: 8px;" id="btn-chat-send" onclick="sendChatInput()">Send →</button>
          </div>
        </div>
      </div>
    </div>"""

new_workspace = """  <!-- ── CENTRAL WORKSPACE ───────────────────────────────────────── -->
  <div class="main-workspace">
    
    <!-- View A: Central Chat View -->
    <div class="chat-view" id="view-chat">
      <header class="chat-header">
        <div style="font-weight:700; font-size:14px;" id="chat-title-context">Workspace Intelligence</div>
        <div class="workspace-stats">
          <div class="stat-badge">Total: <strong id="stats-total">—</strong></div>
          <div class="stat-badge" style="color:var(--accent-emerald);">Active: <strong id="stats-active">—</strong></div>
          <div class="stat-badge" style="color:var(--accent-pink);">Signed: <strong id="stats-signed">—</strong></div>
        </div>
      </header>

      <!-- Chat Conversation Stream -->
      <div class="chat-stream" id="chat-messages">
        <!-- Default Welcome Area -->
        <div class="chat-welcome" id="chat-welcome">
          <div class="welcome-icon-large">🌱</div>
          <h2 class="welcome-title">Seed Reflections Workspace</h2>
          <p class="welcome-desc">
            This is your central workspace. Paste a long AI conversation transcript or import a JSON export file to extract new sparks. Type a question below to chat with your seed database.
          </p>
          <div class="chat-suggestions">
            <button class="chat-suggestion" onclick="triggerSuggestion('What seeds did I abandon?')">What seeds did I abandon?</button>
            <button class="chat-suggestion" onclick="triggerSuggestion('What is my most active seed?')">What is my most active seed?</button>
            <button class="chat-suggestion" onclick="triggerSuggestion('Give me a status overview')">Give me a status overview</button>
          </div>
        </div>
      </div>

      <!-- Chat Input Area -->
      <div class="chat-input-area">
        <div class="chat-input-wrapper">
          <div class="detect-badge" id="transcript-detect-badge">⚡ Detected AI conversation transcript. Send to reflect.</div>
          <div class="chat-input-row">
            <label for="import-file" class="btn-icon" style="margin:0; font-size:15px; font-weight:normal;" title="Attach JSON Export">📎</label>
            <input type="file" id="import-file" accept=".json" style="display:none" onchange="handleFileImport(this.files)">
            <textarea class="chat-input-box" id="chat-input" placeholder="Paste an AI transcript or type a query..." rows="1" oninput="handleInputDetection()" onkeydown="handleInputKeydown(event)"></textarea>
            <button class="btn purple-grad" style="padding: 8px 16px; border-radius: 8px;" id="btn-chat-send" onclick="sendChatInput()">Send →</button>
          </div>
        </div>
      </div>
    </div>

    <!-- View B: Ingestion Workspace Staging -->
    <div class="staging-view" id="view-staging" style="display:none; flex-direction:column; height:100%; overflow:hidden;">
      <!-- Staging Header -->
      <div style="padding:16px 24px; border-bottom:1px solid var(--border); display:flex; flex-direction:column; gap:12px; background:var(--bg-card);">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h3 style="font-size:16px; font-weight:800; color:var(--text-primary); margin:0;">📥 Ingestion Workspace</h3>
            <p style="font-size:11px; color:var(--text-dim); margin:2px 0 0 0;">Select conversation threads to extract seeds. Selected: <strong id="staging-selected-counter" style="color:var(--accent-cyan);">0</strong> / <span id="staging-total-counter">0</span></p>
          </div>
          <div style="display:flex; gap:10px;">
            <button class="btn-ghost-sm" onclick="exitStagingView()">✕ Cancel</button>
            <button class="btn purple-grad" onclick="importSelectedStagingWorkspace()" id="btn-staging-import-workspace">Run Ingestion Engine →</button>
          </div>
        </div>
        
        <!-- Search and Select All -->
        <div style="display:flex; gap:12px; align-items:center;">
          <div style="position:relative; flex:1;">
            <span style="position:absolute; left:12px; top:50%; transform:translateY(-50%); color:var(--text-dim); font-size:12px;">🔍</span>
            <input type="text" id="staging-search-input" placeholder="Search conversations by keywords (e.g. platform, Axum, fitness)..." oninput="filterStagingConversations()" style="width:100%; padding:8px 12px 8px 32px; background:var(--bg-deep); border:1px solid var(--border); border-radius:6px; color:var(--text-primary); font-family:inherit; font-size:12px;" />
          </div>
          <button class="btn-ghost-sm" onclick="toggleSelectAllStaging()" id="btn-staging-select-all" style="font-size:12px; padding:6px 12px; white-space:nowrap;">Select All</button>
        </div>
      </div>
      
      <!-- Staging Grid -->
      <div id="staging-workspace-grid" style="flex:1; overflow-y:auto; padding:20px; display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:16px; background:var(--bg-deep);">
        <!-- Staging cards populated dynamically -->
      </div>
    </div>"""

content = content.replace(old_workspace, new_workspace, 1)
print("Central Workspace HTML view blocks updated successfully.")

# 3. Remove old staging-modal HTML code block:
old_modal_html = """<!-- ── STAGING MODAL ── -->
<div id="staging-modal" class="modal-overlay" style="display:none;">
  <div class="modal-content" style="max-width:800px; width: 100%;">
    <div class="modal-header">
      <h3 style="font-size:17px; font-weight:800;">📥 Select Conversations (<span id="staging-count">0</span> found)</h3>
      <button class="btn-ghost-sm" onclick="closeStagingModal()">✕</button>
    </div>
    <div style="font-size:12px; color:var(--text-muted); margin-bottom:16px;">
      Your large JSON export file has been safely parsed on the local backend server. Select the specific threads you wish to reflect and extract seeds from:
    </div>
    
    <div style="max-height:300px; overflow-y:auto; border:1px solid var(--border); border-radius:8px; background:var(--bg-deep); margin-bottom:16px;">
      <table style="width:100%; border-collapse:collapse; text-align:left; font-size:12.5px;">
        <thead style="position:sticky; top:0; background:var(--bg-surface); border-bottom:1px solid var(--border); z-index:2;">
          <tr>
            <th style="padding:10px; width:40px;"><input type="checkbox" id="staging-select-all" onchange="selectAllStaging(this.checked)" style="accent-color:var(--accent-cyan);" /></th>
            <th style="padding:10px; color:var(--text-muted);">Conversation Thread Preview</th>
            <th style="padding:10px; color:var(--text-muted); width:120px;">Created</th>
            <th style="padding:10px; color:var(--text-muted); width:80px; text-align:center;">Messages</th>
          </tr>
        </thead>
        <tbody id="staging-tbody" style="color:var(--text-secondary);">
          <!-- Dynamic rows -->
        </tbody>
      </table>
    </div>

    <div style="display:flex; justify-content:flex-end; gap:10px; border-top:1px solid var(--border); padding-top:16px;">
      <button class="btn-ghost-sm" onclick="closeStagingModal()">Cancel</button>
      <button class="btn purple-grad" id="btn-staging-import" onclick="importSelectedStaging()">Run Ingestion Engine →</button>
    </div>
  </div>
</div>"""

content = content.replace(old_modal_html, "")
print("Staging Modal HTML markup removed.")

# 4. Replace JS block for file import and staging logic:
old_js_methods = """  // ── FILE IMPORT INLINE (LARGE GIGABYTE-SCALE CHATGPT JSON PARSER) ──
  async function handleFileImport(files) {
    if (!files.length) return;
    const file = files[0];
    
    toast(`Uploading and parsing '${file.name}' (${(file.size / (1024*1024)).toFixed(1)} MB)...`, 'info');

    const formData = new FormData();
    formData.append("file", file);

    try {
      const resp = await fetch(SeedReflectionsPlatform.API_BASE + '/upload_export', {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();
      
      if (!resp.ok) {
        throw new Error(data.error || 'Failed to upload export file.');
      }
      
      const convs = data.conversations || [];
      toast(`Loaded ${convs.length} threads. Select items to reflect.`, 'success');
      openStagingModal(convs);
    } catch (err) {
      console.error(err);
      toast('Upload failed: ' + err.message, 'error');
    }
  }

  let stagingConvs = [];

  function openStagingModal(convs) {
    stagingConvs = convs;
    $('staging-count').textContent = convs.length;
    $('staging-select-all').checked = false;

    const tbody = $('staging-tbody');
    if (convs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:20px; color:var(--text-dim);">No conversation threads parsed.</td></tr>`;
    } else {
      tbody.innerHTML = convs.map(c => `
        <tr style="border-bottom:1px solid var(--border); transition: background-color 0.15s;" onmouseover="this.style.backgroundColor='rgba(255,255,255,0.02)'" onmouseout="this.style.backgroundColor='transparent'">
          <td style="padding:12px 10px; vertical-align:middle;"><input type="checkbox" class="staging-box" value="${c.id}" style="accent-color:var(--accent-cyan);" /></td>
          <td style="padding:12px 10px; vertical-align:middle;">
            <strong style="font-size:13px; color:var(--text-primary); display:block; margin-bottom:4px;" title="${esc(c.title)}">${esc(c.title)}</strong>
            <span style="font-size:11px; color:var(--text-dim); display:block; line-height:1.4; max-width:550px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${esc(c.snippet || '')}">${esc(c.snippet || 'No preview available')}</span>
          </td>
          <td style="padding:12px 10px; color:var(--text-secondary); vertical-align:middle; font-size:12px;">${esc(c.created_at || '—')}</td>
          <td style="padding:12px 10px; text-align:center; vertical-align:middle;"><span class="badge badge-emerald" style="font-size:11px; padding:3px 8px; border-radius:4px; font-weight:600;">${c.depth || 0}</span></td>
        </tr>
      `).join('');
    }
    $('staging-modal').style.display = 'flex';
  }

  function closeStagingModal() {
    $('staging-modal').style.display = 'none';
  }

  function selectAllStaging(checked) {
    document.querySelectorAll('.staging-box').forEach(box => box.checked = checked);
  }

  async function importSelectedStaging() {
    const selectedBoxes = document.querySelectorAll('.staging-box:checked');
    if (selectedBoxes.length === 0) {
      toast('Please select at least one thread to reflect.', 'error');
      return;
    }

    const ids = Array.from(selectedBoxes).map(b => b.value);
    closeStagingModal();
    
    const welcome = $('chat-welcome');
    if (welcome) welcome.style.display = 'none';

    const msgs = $('chat-messages');
    
    msgs.innerHTML += `
      <div class="chat-msg user">
        <div class="msg-label">You</div>
        <div class="msg-bubble"><em>[Requested reflection ingestion for ${ids.length} selected threads]</em></div>
      </div>
    `;
    msgs.scrollTop = msgs.scrollHeight;

    const loadId = 'load-' + Date.now();
    msgs.innerHTML += `
      <div class="chat-msg assistant" id="${loadId}">
        <div class="msg-label">Seed Reflections</div>
        <div class="msg-bubble"><span class="spinner"></span> Running reflection ingestion engine on backend...</div>
      </div>
    `;
    msgs.scrollTop = msgs.scrollHeight;

    try {
      const resp = await fetch(SeedReflectionsPlatform.API_BASE + '/reflect_selected', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ conversations: ids })
      });
      const data = await resp.json();
      
      const loadEl = $(loadId);
      if (resp.ok) {
        const seeds = data.seeds || [];
        loadEl.innerHTML = `
          <div class="msg-label">Seed Reflections</div>
          <div class="msg-bubble">
            <strong>${esc(data.answer)}</strong>
            <div class="inline-staging-card">
              <div class="staging-header">
                <span>Assimilated Seeds (${seeds.length})</span>
                <span class="badge badge-emerald">Imported</span>
              </div>
              <div class="staging-list">
                ${seeds.map(s => `
                  <div class="staging-item" onclick="openFocusPanel('${s.seed_id}')" style="cursor:pointer; transition: background 0.15s; border-radius:4px; padding:6px;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                    <span>🌱</span>
                    <div>
                      <strong>${esc(s.title)}</strong><br>
                      <span style="font-size:11px; color:var(--text-muted);">${esc(s.description)}</span>
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>
          </div>
        `;
        await loadGarden();
        await refreshStats();
      } else {
        loadEl.innerHTML = `<div class="msg-label">Seed Reflections</div><div class="msg-bubble" style="color:var(--accent-red);">Failed to process: ${esc(data.error || 'Server error')}</div>`;
      }
    } catch (e) {
      $(loadId).innerHTML = `<div class="msg-label">Seed Reflections</div><div class="msg-bubble" style="color:var(--accent-red);">Connection error. Failed to execute reflection.</div>`;
    }
    msgs.scrollTop = msgs.scrollHeight;
  }"""

new_js_methods = """  // ── FILE IMPORT & WORKSPACE STAGINGflow ──
  let stagingConvs = [];
  let selectedStagingIds = new Set();

  async function handleFileImport(files) {
    if (!files.length) return;
    const file = files[0];
    
    toast(`Uploading and parsing '${file.name}' (${(file.size / (1024*1024)).toFixed(1)} MB)...`, 'info');

    const formData = new FormData();
    formData.append("file", file);

    try {
      const resp = await fetch(SeedReflectionsPlatform.API_BASE + '/upload_export', {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();
      
      if (!resp.ok) {
        throw new Error(data.error || 'Failed to upload export file.');
      }
      
      stagingConvs = data.conversations || [];
      selectedStagingIds.clear();
      
      $('staging-search-input').value = '';
      $('staging-total-counter').textContent = stagingConvs.length;
      updateSelectedStagingCount();
      
      // Render cards in the central staging workspace
      renderStagingWorkspaceCards(stagingConvs);
      
      // Transition from Chat View to Staging Workspace View
      $('view-chat').style.display = 'none';
      $('view-staging').style.display = 'flex';
      
      toast(`Successfully loaded ${stagingConvs.length} threads in staging workspace.`, 'success');
    } catch (err) {
      console.error(err);
      toast('Upload failed: ' + err.message, 'error');
    }
  }

  function renderStagingWorkspaceCards(convs) {
    const grid = $('staging-workspace-grid');
    if (convs.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:60px 20px; color:var(--text-dim);">
          <span style="font-size:32px; margin-bottom:8px;">🔍</span>
          <strong style="color:var(--text-muted); font-size:14px;">No matching conversation threads</strong>
          <span style="font-size:12px;">Try adjusting your keyword query.</span>
        </div>
      `;
      return;
    }

    grid.innerHTML = convs.map(c => {
      const isSelected = selectedStagingIds.has(c.id);
      const selectedClass = isSelected ? 'selected' : '';
      const checkedAttr = isSelected ? 'checked' : '';
      return `
        <div class="staging-card ${selectedClass}" onclick="toggleStagingCard('${c.id}', event)">
          <div class="staging-card-header">
            <div class="staging-card-title" title="${esc(c.title)}">${esc(c.title)}</div>
            <input type="checkbox" class="staging-card-checkbox" data-id="${c.id}" ${checkedAttr} onclick="toggleStagingCard('${c.id}', event); event.stopPropagation();" />
          </div>
          <div class="staging-card-snippet">${esc(c.snippet || 'No preview snippet available')}</div>
          <div class="staging-card-footer">
            <span>📅 ${esc(c.created_at || '—')}</span>
            <span class="badge badge-emerald" style="font-size:10px; font-weight:600; padding:2px 6px; border-radius:4px;">${c.depth || 0} turns</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function toggleStagingCard(id, event) {
    // If clicked the checkbox itself, prevent double-triggering
    if (event && event.target && event.target.className === 'staging-card-checkbox') {
      // Handled by onclick attribute in template
      const checked = event.target.checked;
      if (checked) {
        selectedStagingIds.add(id);
      } else {
        selectedStagingIds.delete(id);
      }
    } else {
      // Toggle set state
      if (selectedStagingIds.has(id)) {
        selectedStagingIds.delete(id);
      } else {
        selectedStagingIds.add(id);
      }
    }
    
    updateSelectedStagingCount();
    
    // Rerender the active search cards to preserve search query
    filterStagingConversations();
  }

  function filterStagingConversations() {
    const query = $('staging-search-input').value.toLowerCase().trim();
    let filtered = stagingConvs;
    if (query) {
      filtered = stagingConvs.filter(c => 
        (c.title || '').toLowerCase().includes(query) || 
        (c.snippet || '').toLowerCase().includes(query)
      );
    }
    renderStagingWorkspaceCards(filtered);
  }

  function toggleSelectAllStaging() {
    const query = $('staging-search-input').value.toLowerCase().trim();
    let visibleConvs = stagingConvs;
    if (query) {
      visibleConvs = stagingConvs.filter(c => 
        (c.title || '').toLowerCase().includes(query) || 
        (c.snippet || '').toLowerCase().includes(query)
      );
    }

    // Check if all visible ones are already selected
    const allSelected = visibleConvs.every(c => selectedStagingIds.has(c.id));
    
    if (allSelected) {
      // Unselect all visible
      visibleConvs.forEach(c => selectedStagingIds.delete(c.id));
      toast(`Deselected ${visibleConvs.length} threads.`, 'info');
    } else {
      // Select all visible
      visibleConvs.forEach(c => selectedStagingIds.add(c.id));
      toast(`Selected ${visibleConvs.length} threads.`, 'success');
    }
    
    updateSelectedStagingCount();
    filterStagingConversations();
  }

  function updateSelectedStagingCount() {
    const count = selectedStagingIds.size;
    $('staging-selected-counter').textContent = count;
    
    // Toggle button state
    const btn = $('btn-staging-import-workspace');
    if (count === 0) {
      btn.disabled = true;
      btn.style.opacity = '0.5';
      btn.style.cursor = 'not-allowed';
    } else {
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.style.cursor = 'pointer';
    }

    // Toggle Select All text button
    const btnAll = $('btn-staging-select-all');
    if (btnAll) {
      const query = $('staging-search-input').value.toLowerCase().trim();
      let visibleConvs = stagingConvs;
      if (query) {
        visibleConvs = stagingConvs.filter(c => 
          (c.title || '').toLowerCase().includes(query) || 
          (c.snippet || '').toLowerCase().includes(query)
        );
      }
      const allSelected = visibleConvs.length > 0 && visibleConvs.every(c => selectedStagingIds.has(c.id));
      btnAll.textContent = allSelected ? 'Deselect All' : 'Select All';
    }
  }

  function exitStagingView() {
    // Hide staging view, show chat view
    $('view-staging').style.display = 'none';
    $('view-chat').style.display = 'flex';
    selectedStagingIds.clear();
  }

  async function importSelectedStagingWorkspace() {
    if (selectedStagingIds.size === 0) {
      toast('Please select at least one thread to reflect.', 'error');
      return;
    }

    const ids = Array.from(selectedStagingIds);
    exitStagingView(); // Return to chat view
    
    const welcome = $('chat-welcome');
    if (welcome) welcome.style.display = 'none';

    const msgs = $('chat-messages');
    
    msgs.innerHTML += `
      <div class="chat-msg user">
        <div class="msg-label">You</div>
        <div class="msg-bubble"><em>[Requested reflection ingestion for ${ids.length} selected threads]</em></div>
      </div>
    `;
    msgs.scrollTop = msgs.scrollHeight;

    const loadId = 'load-' + Date.now();
    msgs.innerHTML += `
      <div class="chat-msg assistant" id="${loadId}">
        <div class="msg-label">Seed Reflections</div>
        <div class="msg-bubble"><span class="spinner"></span> Running reflection ingestion engine on backend...</div>
      </div>
    `;
    msgs.scrollTop = msgs.scrollHeight;

    try {
      const resp = await fetch(SeedReflectionsPlatform.API_BASE + '/reflect_selected', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ conversations: ids })
      });
      const data = await resp.json();
      
      const loadEl = $(loadId);
      if (resp.ok) {
        const seeds = data.seeds || [];
        loadEl.innerHTML = `
          <div class="msg-label">Seed Reflections</div>
          <div class="msg-bubble">
            <strong>${esc(data.answer)}</strong>
            <div class="inline-staging-card">
              <div class="staging-header">
                <span>Assimilated Seeds (${seeds.length})</span>
                <span class="badge badge-emerald">Imported</span>
              </div>
              <div class="staging-list">
                ${seeds.map(s => `
                  <div class="staging-item" onclick="openFocusPanel('${s.seed_id}')" style="cursor:pointer; transition: background 0.15s; border-radius:4px; padding:6px;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='transparent'">
                    <span>🌱</span>
                    <div>
                      <strong>${esc(s.title)}</strong><br>
                      <span style="font-size:11px; color:var(--text-muted);">${esc(s.description)}</span>
                    </div>
                  </div>
                `).join('')}
              </div>
            </div>
          </div>
        `;
        await loadGarden();
        await refreshStats();
      } else {
        loadEl.innerHTML = `<div class="msg-label">Seed Reflections</div><div class="msg-bubble" style="color:var(--accent-red);">Failed to process: ${esc(data.error || 'Server error')}</div>`;
      }
    } catch (e) {
      $(loadId).innerHTML = `<div class="msg-label">Seed Reflections</div><div class="msg-bubble" style="color:var(--accent-red);">Connection error. Failed to execute reflection.</div>`;
    }
    msgs.scrollTop = msgs.scrollHeight;
  }"""

content = content.replace(old_js_methods, new_js_methods, 1)
print("JS file import and workspace staging logic updated successfully.")

with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Workspace-Native refactoring complete in rebuild_dashboard.py.")
