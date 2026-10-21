with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

# ─────────────────────────────────────────────────────────────
# 1. Remove garden-filters from Left Sidebar Garden Library Header
# ─────────────────────────────────────────────────────────────

old_sidebar_header = """  <!-- ── LEFT SIDEBAR: GARDEN LIBRARY ───────────────────────────── -->
  <aside class="sidebar-garden">
    <div class="garden-header">
      <div class="logo-container">
        <a href="index.html">Seed<em>Reflections</em></a>
        <div class="avatar" id="hdr-avatar">SR</div>
      </div>
      
      <div class="search-input-wrap">
        <input type="search" id="garden-search" class="search-input" placeholder="Search seeds..." oninput="filterGardenList()" autocomplete="off" name="garden_search_query" />
      </div>

      <div class="garden-filters">
        <button class="filter-pill active" onclick="setGardenFilter(null)" id="filter-all">All</button>
        <button class="filter-pill" onclick="setGardenFilter('planted')" id="filter-planted">Planted</button>
        <button class="filter-pill" onclick="setGardenFilter('growing')" id="filter-growing">Active</button>
        <button class="filter-pill" onclick="setGardenFilter('bloomed')" id="filter-bloomed">Completed</button>
        <button class="filter-pill" onclick="setGardenFilter('wilted')" id="filter-wilted">Wilted</button>
      </div>
    </div>"""

new_sidebar_header = """  <!-- ── LEFT SIDEBAR: GARDEN LIBRARY ───────────────────────────── -->
  <aside class="sidebar-garden">
    <div class="garden-header">
      <div class="logo-container">
        <a href="index.html">Seed<em>Reflections</em></a>
        <div class="avatar" id="hdr-avatar">SR</div>
      </div>
      
      <div class="search-input-wrap">
        <input type="search" id="garden-search" class="search-input" placeholder="Search seeds..." oninput="filterGardenList()" autocomplete="off" name="garden_search_query" />
      </div>
    </div>"""

if old_sidebar_header in content:
    content = content.replace(old_sidebar_header, new_sidebar_header, 1)
    print("1. Sidebar header filter pills removed.")
else:
    print("WARNING: Sidebar header block not found!")

# ─────────────────────────────────────────────────────────────
# 2. Add Filter Pills + Close Focus button to Central Chat Header
# ─────────────────────────────────────────────────────────────

old_chat_header = """    <!-- View A: Central Chat View -->
    <div class="chat-view" id="view-chat">
      <header class="chat-header">
        <div style="font-weight:700; font-size:14px;" id="chat-title-context">Workspace Intelligence</div>
        <div class="workspace-stats">
          <div class="stat-badge">Total: <strong id="stats-total">—</strong></div>
          <div class="stat-badge" style="color:var(--accent-emerald);">Active: <strong id="stats-active">—</strong></div>
          <div class="stat-badge" style="color:var(--accent-pink);">Signed: <strong id="stats-signed">—</strong></div>
        </div>
      </header>"""

new_chat_header = """    <!-- View A: Central Chat View -->
    <div class="chat-view" id="view-chat">
      <header class="chat-header" style="justify-content: space-between;">
        <div style="display:flex; align-items:center; gap:10px;">
          <div style="font-weight:700; font-size:14px;" id="chat-title-context">Workspace Intelligence</div>
          <button class="btn-ghost-sm" id="btn-close-focus" style="display:none; padding:4px 8px; font-size:11px;" onclick="closeSeedFocus()">✕ Close Focus</button>
        </div>
        
        <!-- Filter Pills moved from Sidebar to Header -->
        <div class="garden-filters" style="padding:0; margin:0; border:none; background:none; display:flex; gap:6px;">
          <button class="filter-pill active" onclick="setGardenFilter(null)" id="filter-all">All</button>
          <button class="filter-pill" onclick="setGardenFilter('planted')" id="filter-planted">Planted</button>
          <button class="filter-pill" onclick="setGardenFilter('growing')" id="filter-growing">Active</button>
          <button class="filter-pill" onclick="setGardenFilter('bloomed')" id="filter-bloomed">Completed</button>
          <button class="filter-pill" onclick="setGardenFilter('wilted')" id="filter-wilted">Wilted</button>
        </div>

        <div class="workspace-stats">
          <div class="stat-badge">Total: <strong id="stats-total">—</strong></div>
          <div class="stat-badge" style="color:var(--accent-emerald);">Active: <strong id="stats-active">—</strong></div>
          <div class="stat-badge" style="color:var(--accent-pink);">Signed: <strong id="stats-signed">—</strong></div>
        </div>
      </header>"""

if old_chat_header in content:
    content = content.replace(old_chat_header, new_chat_header, 1)
    print("2. Chat header layout updated with filters and Close Focus button.")
else:
    print("WARNING: Chat header block not found!")

# ─────────────────────────────────────────────────────────────
# 3. Remove slide-over Seed Focus Panel completely from HTML
# ─────────────────────────────────────────────────────────────

old_focus_panel_html = """    <!-- ── SLIDE-OVER SEED DETAILS PANEL ─────────────────────────── -->
    <div class="focus-panel" id="focus-panel">
      <div class="focus-header">
        <div class="focus-title" id="focus-seed-title-header">Seed Details</div>
        <button class="btn-ghost-sm" onclick="closeFocusPanel()">✕ Close</button>
      </div>
      
      <div class="focus-body" id="focus-panel-body">
        <!-- Content dynamic -->
      </div>
    </div>"""

if old_focus_panel_html in content:
    content = content.replace(old_focus_panel_html, "", 1)
    print("3. Slide-over details focus panel removed from HTML.")
else:
    # Try finding without comments or with spacing changes
    import re
    cleaned, count = re.subn(r'<!--[^>]*SLIDE-OVER[^>]*-->\s*<div class="focus-panel" id="focus-panel">.*?</div>\s*</div>', "", content, flags=re.DOTALL)
    if count > 0:
        content = cleaned
        print("3. Slide-over details focus panel removed via regex.")
    else:
        print("WARNING: Focus panel HTML block not found!")

# ─────────────────────────────────────────────────────────────
# 4. Replace JS openFocusPanel down to startFocusSigning with Workspace-native logic
# ─────────────────────────────────────────────────────────────

# First, find the openFocusPanel block range
lines = content.splitlines()
start_js_idx = None
end_js_idx = None

for i, line in enumerate(lines):
    if "function openFocusPanel(seedId) {" in line:
        start_js_idx = i - 1  # Include let focusDiscussMessages = []; or comment
    if start_js_idx and i > start_js_idx and "async function startFocusSigning(seedId) {" in line:
        end_js_idx = i
        break

if start_js_idx is not None and end_js_idx is not None:
    print(f"Found Focus JS block at lines {start_js_idx+1} to {end_js_idx+1}")
    
    new_focus_js = """  // ── WORKSPACE-NATIVE SEED FOCUS INTEL ─────────────────────────
  let seedDiscussions = {}; // Store seed discussions to survive workspace updates

  function openFocusPanel(seedId) {
    activeFocusSeedId = seedId;
    renderGardenList(); // Refresh active highlights in sidebar list
    
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;

    // Show Close Focus button in workspace top header
    $('btn-close-focus').style.display = 'inline-block';
    $('chat-title-context').textContent = '🌱 Focus: ' + seed.title.substring(0, 30) + (seed.title.length > 30 ? '...' : '');

    // Hide standard chat welcome board
    const welcome = $('chat-welcome');
    if (welcome) welcome.style.display = 'none';

    // Build Workspace-Native Seed Meta Header Block
    const badgeClass = seed.status === 'bloomed' ? 'badge-blue' : seed.status === 'wilted' ? 'badge-red' : 'badge-emerald';
    const threadTitle = seed.source_thread_title ? esc(seed.source_thread_title) : 'Direct input';
    const hasTranscript = !!seed.source_transcript_id;

    const metaPanelHTML = `
      <div class="seed-meta-panel" style="margin-bottom:24px; padding:20px; background:var(--bg-card); border:1px solid var(--border); border-radius:12px; display:flex; flex-direction:column; gap:16px; text-align:left; animation: fadeIn 0.2s ease-out;">
        <div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span class="badge ${badgeClass}">${seed.status}</span>
            <span style="font-size:11px; color:var(--text-dim);">Created ${seed.created_at ? seed.created_at.split('T')[0] : 'today'}</span>
          </div>
          <h3 style="font-size:18px; font-weight:800; margin-bottom:12px; line-height:1.4; color:var(--text-primary);">${esc(seed.title)}</h3>
          <p style="font-size:13.5px; color:var(--text-secondary); line-height:1.65; background:var(--bg-surface); padding:16px; border-radius:8px; border:1px solid var(--border); margin:0;">${esc(seed.intent || seed.description)}</p>
        </div>

        <div style="font-size:12px; color:var(--text-dim); display:flex; align-items:center; gap:6px;">
          <span>📂</span> Source conversation: <strong style="color:var(--text-muted);">${threadTitle}</strong>
        </div>

        <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center; border-top:1px solid rgba(255,255,255,0.03); padding-top:14px; margin-top:4px;">
          <button class="btn-ghost-sm" onclick="emailSeed('${seed.id}')">📧 Email</button>
          <button class="btn-ghost-sm" onclick="copySeedToClipboard('${seed.id}')">📋 Copy</button>
          <button class="btn-ghost-sm" onclick="downloadSeedMarkdown('${seed.id}')">💾 Download</button>
          <button class="btn-ghost-sm" onclick="openFocusHandoff('${seed.id}', '${esc(seed.title)}')">🚀 Handoff Payload</button>
          ${seed.is_cryptographically_signed ? `
            <span style="font-size:11px; color:#10b981; font-family:monospace; padding:6px 10px; background:#0f172a; border:1px solid #1e293b; border-radius:6px; display:inline-flex; align-items:center; gap:4px;">🔐 Signed</span>
          ` : `
            <button class="btn-ghost-sm" style="color:var(--accent-purple); border-color:var(--accent-purple);" onclick="startFocusSigning('${seed.id}')">✍️ Sign Seed</button>
          `}
          <button class="btn-ghost-sm" style="color:var(--accent-red); border-color:var(--accent-red); margin-left:auto;" onclick="deleteActiveSeed('${seed.id}')">🗑️ Delete Seed</button>
        </div>

        ${hasTranscript ? `
          <div style="border-top:1px solid rgba(255,255,255,0.03); padding-top:14px; margin-top:4px;">
            <button class="btn-ghost-sm" style="width:100%; justify-content:center; gap:6px;" onclick="toggleWorkspaceTranscript('${seed.source_transcript_id}')" id="btn-workspace-transcript">
              📜 View Original Conversation
            </button>
            <div id="workspace-transcript-container" style="display:none; margin-top:14px;">
              <div class="transcript-viewer" id="workspace-transcript-content" style="max-height:280px; border-radius:8px;">Loading transcript...</div>
            </div>
          </div>
        ` : ''}
      </div>
    `;

    // Initialize seed discussion thread in main chat if not present
    if (!seedDiscussions[seedId]) {
      seedDiscussions[seedId] = [
        {
          role: 'assistant',
          text: `👋 Ready to discuss: **${esc(seed.title.substring(0, 80))}**. ${hasTranscript ? "I have the original conversation loaded. Ask me anything about it!" : "What would you like to explore?"}`
        }
      ];
    }

    const msgs = $('chat-messages');
    msgs.innerHTML = metaPanelHTML + '<div id="seed-chat-history" style="display:flex; flex-direction:column; gap:12px;"></div>';
    
    renderSeedChatHistory(seedId);
  }

  function renderSeedChatHistory(seedId) {
    const container = $('seed-chat-history');
    if (!container) return;
    
    const history = seedDiscussions[seedId] || [];
    container.innerHTML = history.map(msg => `
      <div class="chat-msg ${msg.role}">
        <div class="msg-label">${msg.role === 'user' ? 'You' : 'Seed Reflections'}</div>
        <div class="msg-bubble">${renderMarkdown(msg.text)}</div>
      </div>
    `).join('');
    
    const msgs = $('chat-messages');
    msgs.scrollTop = msgs.scrollHeight;
  }

  function closeSeedFocus() {
    activeFocusSeedId = null;
    $('btn-close-focus').style.display = 'none';
    $('chat-title-context').textContent = 'Workspace Intelligence';
    
    const msgs = $('chat-messages');
    msgs.innerHTML = `
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
    `;
    
    renderGardenList(); // Remove active borders
  }

  async function toggleWorkspaceTranscript(transcriptId) {
    const container = $('workspace-transcript-container');
    const viewer = $('workspace-transcript-content');
    const btn = $('btn-workspace-transcript');

    if (container.style.display === 'block') {
      container.style.display = 'none';
      btn.textContent = '📜 View Original Conversation';
      return;
    }

    container.style.display = 'block';
    btn.textContent = '📜 Hide Conversation';
    viewer.textContent = 'Loading transcript...';

    try {
      const resp = await SeedReflectionsPlatform.apiRequest('/transcripts/' + transcriptId);
      const data = await resp.json();
      if (resp.ok && data.text) {
        let formatted = data.text;
        formatted = formatted.replace(/\\\\[user\\\\]:/gi, '<span class="transcript-role-user">[You]:</span>');
        formatted = formatted.replace(/\\\\[human\\\\]:/gi, '<span class="transcript-role-user">[You]:</span>');
        formatted = formatted.replace(/\\\\[assistant\\\\]:/gi, '<span class="transcript-role-assistant">[AI]:</span>');
        viewer.innerHTML = formatted;
      } else {
        viewer.textContent = 'Transcript not found or expired.';
      }
    } catch (e) {
      viewer.textContent = 'Failed to load transcript: ' + e.message;
    }
  }

  async function deleteActiveSeed(seedId) {
    if (!confirm("Are you sure you want to delete this seed permanently?")) return;
    
    try {
      toast('Deleting seed...', 'info');
      const resp = await fetch(SeedReflectionsPlatform.API_BASE + '/seeds/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ seed_id: seedId })
      });
      const data = await resp.json();
      if (resp.ok) {
        toast('🗑️ Seed successfully deleted.', 'success');
        closeSeedFocus();
        await loadGarden();
        await refreshStats();
      } else {
        toast(data.error || 'Failed to delete seed', 'error');
      }
    } catch (e) {
      toast('Connection error. Failed to delete seed.', 'error');
    }
  }

  function copySeedToClipboard(seedId) {
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;
    const text = '## ' + seed.title + '\\\\n\\\\n' + (seed.intent || seed.description) + '\\\\n\\\\nStatus: ' + seed.status + '\\\\nCreated: ' + (seed.created_at || 'today');
    navigator.clipboard.writeText(text).then(() => toast('Seed copied to clipboard!', 'success')).catch(() => toast('Copy failed', 'error'));
  }

  function downloadSeedMarkdown(seedId) {
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;
    const md = '# ' + seed.title + '\\\\n\\\\n**Status:** ' + seed.status + '  \\\\n**Created:** ' + (seed.created_at || 'today') + '\\\\n\\\\n---\\\\n\\\\n' + (seed.intent || seed.description);
    const blob = new Blob([md], {type: 'text/markdown'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (seed.title || 'seed').substring(0, 40).replace(/[^a-zA-Z0-9]/g, '_') + '.md';
    a.click();
    toast('Seed downloaded as markdown.', 'success');
  }

"""
    lines = lines[:start_js_idx] + new_focus_js.splitlines() + lines[end_js_idx:]
    content = "\n".join(lines)
    print("4. Focused Details JS utility functions completely updated.")
else:
    print(f"FAILED: start_js_idx={start_js_idx}, end_js_idx={end_js_idx}")

# ─────────────────────────────────────────────────────────────
# 5. Route discussSeedContext to workspace-native openFocusPanel
# ─────────────────────────────────────────────────────────────

old_discuss_context = """  function discussSeedContext(seedId) {
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;
    closeFocusPanel();
    triggerSuggestion(`Let's discuss my active seed: '${seed.title}'. What is my next actionable step?`);
  }"""

new_discuss_context = """  function discussSeedContext(seedId) {
    openFocusPanel(seedId);
  }"""

if old_discuss_context in content:
    content = content.replace(old_discuss_context, new_discuss_context, 1)
    print("5. discussSeedContext routed directly to native focus workspace.")
else:
    print("WARNING: discussSeedContext block not found!")

# ─────────────────────────────────────────────────────────────
# 6. Route sendChatInput to discuss seed if activeFocusSeedId is set
# ─────────────────────────────────────────────────────────────

old_send_chat_start = """  async function sendChatInput() {
    const input = $('chat-input');
    const text = input.value.trim();
    if (!text) return;"""

new_send_chat_start = """  async function sendChatInput() {
    const input = $('chat-input');
    const text = input.value.trim();
    if (!text) return;

    if (activeFocusSeedId) {
      // Focused Seed Discussion chat flow
      const history = seedDiscussions[activeFocusSeedId];
      history.push({ role: 'user', text: text });
      renderSeedChatHistory(activeFocusSeedId);
      input.value = '';
      
      const loadId = 'discuss-load-' + Date.now();
      const historyContainer = $('seed-chat-history');
      historyContainer.innerHTML += `
        <div class="chat-msg assistant" id="${loadId}">
          <div class="msg-label">Seed Reflections</div>
          <div class="msg-bubble"><span class="spinner"></span> Thinking...</div>
        </div>
      `;
      
      const msgs = $('chat-messages');
      msgs.scrollTop = msgs.scrollHeight;
      
      try {
        const resp = await SeedReflectionsPlatform.apiRequest('/seeds/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: { prompt: text, active_seed_id: activeFocusSeedId }
        });
        const data = await resp.json();
        
        history.push({ role: 'assistant', text: data.answer });
        renderSeedChatHistory(activeFocusSeedId);
      } catch (e) {
        const loadEl = $(loadId);
        if (loadEl) {
          loadEl.innerHTML = `
            <div class="msg-label">Seed Reflections</div>
            <div class="msg-bubble" style="color:var(--accent-red);">Failed to query AI backend.</div>
          `;
        }
      }
      return;
    }"""

if old_send_chat_start in content:
    content = content.replace(old_send_chat_start, new_send_chat_start, 1)
    print("6. sendChatInput active seed discussion routing added.")
else:
    print("WARNING: sendChatInput start block not found!")

# ─────────────────────────────────────────────────────────────
# 7. Update signature modal completion callback to call openFocusPanel(seedId)
# ─────────────────────────────────────────────────────────────

old_sig_complete = """            if (saveResp.ok) {
              toast('🌸 Seed successfully signed and verified!', 'success');
              await loadGarden();
              openFocusPanel(seedId); // Refresh focus UI
              await refreshStats();
            }"""

new_sig_complete = """            if (saveResp.ok) {
              toast('🌸 Seed successfully signed and verified!', 'success');
              await loadGarden();
              openFocusPanel(seedId); // Refresh focus workspace
              await refreshStats();
            }"""

if old_sig_complete in content:
    content = content.replace(old_sig_complete, new_sig_complete, 1)
    print("7. Signature modal openFocusPanel refresh updated.")
else:
    print("WARNING: Signature complete block not found!")


with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)

print("\n=== Dashboard Workspace-Native Focus patch complete ===")
