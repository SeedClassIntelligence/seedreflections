"""
Patch rebuild_dashboard.py with:
1. Focus Panel tab CSS
2. Redesigned openFocusPanel with Overview/Discuss/Actions tabs
3. Transcript lazy-loading
4. Focus panel discuss mini-chat
5. Clear search input on page load
"""

with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

# ─────────────────────────────────────────────────────────────
# 1. Add Focus Panel tab CSS before the closing </style> tag
# ─────────────────────────────────────────────────────────────

old_close_style = """    .chat-suggestion:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(57,208,216,0.05); }

  </style>"""

new_close_style = """    .chat-suggestion:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(57,208,216,0.05); }

    /* ── FOCUS PANEL TABS ─────────────────────────────────────── */
    .focus-tabs {
      display: flex;
      border-bottom: 1px solid var(--border);
      background: var(--bg-surface);
    }
    .focus-tab {
      flex: 1;
      padding: 10px 8px;
      text-align: center;
      font-size: 11.5px;
      font-weight: 700;
      color: var(--text-dim);
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.15s;
      background: none;
      border-top: none;
      border-left: none;
      border-right: none;
      font-family: 'Inter', sans-serif;
    }
    .focus-tab:hover { color: var(--text-secondary); }
    .focus-tab.active {
      color: var(--accent-cyan);
      border-bottom-color: var(--accent-cyan);
    }
    .focus-tab-content { display: none; }
    .focus-tab-content.active { display: flex; flex-direction: column; gap: 16px; }

    .transcript-viewer {
      background: var(--bg-deep);
      border: 1px solid var(--border);
      border-radius: 8px;
      max-height: 350px;
      overflow-y: auto;
      padding: 14px;
      font-size: 12px;
      color: var(--text-secondary);
      line-height: 1.65;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: 'Inter', sans-serif;
    }
    .transcript-viewer::-webkit-scrollbar { width: 5px; }
    .transcript-viewer::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    .transcript-role-user { color: var(--accent-cyan); font-weight: 700; }
    .transcript-role-assistant { color: var(--accent-purple); font-weight: 700; }

    .focus-discuss-input-area {
      display: flex;
      gap: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--border);
    }
    .focus-discuss-input {
      flex: 1;
      padding: 8px 12px;
      background: var(--bg-deep);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text-primary);
      font-family: 'Inter', sans-serif;
      font-size: 12px;
      resize: none;
    }
    .focus-discuss-input:focus {
      outline: none;
      border-color: var(--accent-cyan);
    }
    .focus-discuss-messages {
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-height: calc(100vh - 320px);
      min-height: 200px;
    }
    .focus-discuss-messages::-webkit-scrollbar { width: 5px; }
    .focus-discuss-messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    .discuss-msg {
      padding: 10px 12px;
      border-radius: 8px;
      font-size: 12.5px;
      line-height: 1.55;
      max-width: 92%;
    }
    .discuss-msg.user {
      background: rgba(57,208,216,0.08);
      border: 1px solid rgba(57,208,216,0.15);
      align-self: flex-end;
      color: var(--text-primary);
    }
    .discuss-msg.assistant {
      background: var(--bg-card);
      border: 1px solid var(--border);
      align-self: flex-start;
      color: var(--text-secondary);
    }

  </style>"""

if old_close_style in content:
    content = content.replace(old_close_style, new_close_style, 1)
    print("1. Focus Panel tab CSS added.")
else:
    print("WARNING: Close style block not found!")

# ─────────────────────────────────────────────────────────────
# 2. Replace openFocusPanel function with tabbed version
# ─────────────────────────────────────────────────────────────

old_focus_panel_fn = """  // ── FOCUS DETAILS PANEL UTILITIES ────────────────────────────
  function openFocusPanel(seedId) {
    activeFocusSeedId = seedId;
    renderGardenList(); // Refresh active state classes
    
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;

    $('focus-seed-title-header').textContent = seed.title.substring(0, 30) + (seed.title.length > 30 ? '...' : '');

    const body = $('focus-panel-body');
    const badgeClass = seed.status === 'bloomed' ? 'badge-blue' : seed.status === 'wilted' ? 'badge-red' : 'badge-emerald';
    
    const sigSection = seed.is_cryptographically_signed ? `
      <div style="font-size:11px; background:#0f172a; padding:10px 12px; border-radius:6px; border:1px solid #1e293b; color:#10b981; font-family:monospace;">
        <strong>Verified &amp; Secured by Seed Reflections Authority</strong><br>
        <span style="font-size:9.5px; color:var(--text-dim);">Sig ID: ${esc(seed.trust_state?.signature)}</span>
      </div>
    ` : `
      <div style="display:flex; justify-content:flex-end;">
        <button class="btn-ghost-sm" style="color:var(--accent-purple); border-color:var(--accent-purple);" onclick="startFocusSigning('${seed.id}')">✍️ Sign Seed</button>
      </div>
    `;

    body.innerHTML = `
      <div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <span class="badge ${badgeClass}">${seed.status}</span>
          <span style="font-size:11.5px; color:var(--text-dim);">Created ${seed.created_at ? seed.created_at.split('T')[0] : 'today'}</span>
        </div>
        <h3 style="font-size:18px; font-weight:800; margin-bottom:12px; line-height:1.35;">${esc(seed.title)}</h3>
        <p style="font-size:13.5px; color:var(--text-secondary); line-height:1.6; background:var(--bg-surface); padding:14px; border-radius:8px; border:1px solid var(--border);">${esc(seed.intent || seed.description)}</p>
      </div>

      <div style="display:flex; flex-direction:column; gap:10px;">
        <h4 style="font-size:11px; font-weight:800; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Provenance & Trust</h4>
        ${sigSection}
      </div>

      <div style="display:flex; flex-direction:column; gap:12px; padding:16px; background:rgba(255,255,255,0.01); border:1px solid var(--border); border-radius:10px;">
        <h4 style="font-size:11.5px; font-weight:800; color:var(--text-secondary); display:flex; justify-content:space-between; align-items:center;">
          <span>🚀 Assistant Handoff</span>
          <span style="font-size:10px; font-weight:normal; color:var(--text-dim);">Share with coding LLMs</span>
        </h4>
        <button class="btn purple-grad" style="width:100%;" onclick="openFocusHandoff('${seed.id}', '${esc(seed.title)}')">🚀 Generate Context Handoff Payload</button>
        <p style="font-size:10.5px; color:var(--text-dim); line-height:1.4;">Creates a structured markdown envelope with proof signatures to initialize code assistants (like Gemini, Claude Code, or ChatGPT).</p>
      </div>

      <div style="display:flex; flex-direction:column; gap:12px; padding:16px; background:rgba(255,255,255,0.01); border:1px solid var(--border); border-radius:10px;">
        <h4 style="font-size:11.5px; font-weight:800; color:var(--text-secondary);">📤 Export & Share</h4>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
          <button class="btn-ghost-sm" style="display:inline-flex; align-items:center; justify-content:center; gap:4px;" onclick="emailSeed('${seed.id}')">📧 Email Seed</button>
          <button class="btn-ghost-sm" style="display:inline-flex; align-items:center; justify-content:center; gap:4px;" onclick="discussSeedContext('${seed.id}')">💬 Chat Discuss</button>
        </div>
      </div>
    `;

    $('focus-panel').classList.add('active');
  }"""

new_focus_panel_fn = """  // ── FOCUS DETAILS PANEL UTILITIES ────────────────────────────
  let focusDiscussMessages = [];

  function openFocusPanel(seedId) {
    activeFocusSeedId = seedId;
    renderGardenList();
    
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;

    $('focus-seed-title-header').textContent = seed.title.substring(0, 30) + (seed.title.length > 30 ? '...' : '');

    const body = $('focus-panel-body');
    const badgeClass = seed.status === 'bloomed' ? 'badge-blue' : seed.status === 'wilted' ? 'badge-red' : 'badge-emerald';
    const threadTitle = seed.source_thread_title ? esc(seed.source_thread_title) : 'Direct input';
    const hasTranscript = !!seed.source_transcript_id;

    body.innerHTML = `
      <!-- Tabs -->
      <div class="focus-tabs">
        <button class="focus-tab active" onclick="switchFocusTab('overview', this)">📋 Overview</button>
        <button class="focus-tab" onclick="switchFocusTab('discuss', this)">💬 Discuss</button>
        <button class="focus-tab" onclick="switchFocusTab('actions', this)">⚡ Actions</button>
      </div>

      <!-- Tab: Overview -->
      <div class="focus-tab-content active" id="focus-tab-overview" style="padding:20px; gap:16px;">
        <div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span class="badge ${badgeClass}">${seed.status}</span>
            <span style="font-size:11px; color:var(--text-dim);">Created ${seed.created_at ? seed.created_at.split('T')[0] : 'today'}</span>
          </div>
          <h3 style="font-size:17px; font-weight:800; margin-bottom:10px; line-height:1.35; color:var(--text-primary);">${esc(seed.title)}</h3>
          <p style="font-size:13px; color:var(--text-secondary); line-height:1.65; background:var(--bg-surface); padding:14px; border-radius:8px; border:1px solid var(--border);">${esc(seed.intent || seed.description)}</p>
        </div>

        <div style="font-size:11.5px; color:var(--text-dim); display:flex; align-items:center; gap:6px;">
          <span>📂</span> Source thread: <strong style="color:var(--text-muted);">${threadTitle}</strong>
        </div>

        ${hasTranscript ? `
          <div>
            <button class="btn-ghost-sm" style="width:100%; justify-content:center; gap:6px;" onclick="loadTranscriptViewer('${seed.source_transcript_id}')" id="btn-load-transcript">
              📜 View Original Conversation
            </button>
            <div id="transcript-viewer-container" style="display:none; margin-top:12px;">
              <div class="transcript-viewer" id="transcript-viewer-content">Loading...</div>
            </div>
          </div>
        ` : `
          <div style="font-size:11.5px; color:var(--text-dim); padding:12px; background:var(--bg-deep); border-radius:6px; text-align:center;">
            No source transcript attached to this seed.
          </div>
        `}
      </div>

      <!-- Tab: Discuss -->
      <div class="focus-tab-content" id="focus-tab-discuss" style="padding:16px; flex:1; display:none; flex-direction:column; height: calc(100vh - 180px);">
        <div style="margin-bottom:10px;">
          <p style="font-size:11.5px; color:var(--text-dim); line-height:1.4;">
            Chat about this seed. ${hasTranscript ? 'The AI has access to the full original conversation for context.' : ''}
          </p>
        </div>
        <div class="focus-discuss-messages" id="focus-discuss-messages">
          <div class="discuss-msg assistant">
            👋 I'm ready to discuss this seed: <strong>${esc(seed.title.substring(0, 60))}</strong>.
            ${hasTranscript ? "I have the original conversation loaded for context. Ask me anything about it!" : "What would you like to explore?"}
          </div>
        </div>
        <div class="focus-discuss-input-area">
          <textarea class="focus-discuss-input" id="focus-discuss-input" placeholder="Ask about this seed..." rows="1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendFocusDiscuss();}"></textarea>
          <button class="btn purple-grad" style="padding:8px 14px; font-size:12px; border-radius:6px;" onclick="sendFocusDiscuss()">Send</button>
        </div>
      </div>

      <!-- Tab: Actions -->
      <div class="focus-tab-content" id="focus-tab-actions" style="padding:20px; gap:16px; display:none;">
        <div style="display:flex; flex-direction:column; gap:12px; padding:16px; background:rgba(255,255,255,0.02); border:1px solid var(--border); border-radius:10px;">
          <h4 style="font-size:12px; font-weight:800; color:var(--text-secondary);">📤 Export & Share</h4>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
            <button class="btn-ghost-sm" style="display:inline-flex; align-items:center; justify-content:center; gap:4px;" onclick="emailSeed('${seed.id}')">📧 Email</button>
            <button class="btn-ghost-sm" style="display:inline-flex; align-items:center; justify-content:center; gap:4px;" onclick="copySeedToClipboard('${seed.id}')">📋 Copy</button>
            <button class="btn-ghost-sm" style="display:inline-flex; align-items:center; justify-content:center; gap:4px;" onclick="downloadSeedMarkdown('${seed.id}')">💾 Download</button>
            <button class="btn-ghost-sm" style="display:inline-flex; align-items:center; justify-content:center; gap:4px;" onclick="switchFocusTab('discuss', document.querySelectorAll('.focus-tab')[1])">💬 Discuss</button>
          </div>
        </div>

        <div style="display:flex; flex-direction:column; gap:12px; padding:16px; background:rgba(255,255,255,0.02); border:1px solid var(--border); border-radius:10px;">
          <h4 style="font-size:12px; font-weight:800; color:var(--text-secondary);">🚀 Assistant Handoff</h4>
          <button class="btn purple-grad" style="width:100%;" onclick="openFocusHandoff('${seed.id}', '${esc(seed.title)}')">Generate Context Handoff Payload</button>
          <p style="font-size:10.5px; color:var(--text-dim); line-height:1.4;">Creates a structured markdown envelope to initialize external AI code assistants.</p>
        </div>

        <div style="display:flex; flex-direction:column; gap:10px; padding:16px; background:rgba(255,255,255,0.02); border:1px solid var(--border); border-radius:10px;">
          <h4 style="font-size:12px; font-weight:800; color:var(--text-secondary);">🔐 Provenance & Trust</h4>
          ${seed.is_cryptographically_signed ? `
            <div style="font-size:11px; background:#0f172a; padding:10px 12px; border-radius:6px; border:1px solid #1e293b; color:#10b981; font-family:monospace;">
              <strong>Verified & Secured</strong><br>
              <span style="font-size:9.5px; color:var(--text-dim);">Sig: ${esc(seed.trust_state?.signature)}</span>
            </div>
          ` : `
            <button class="btn-ghost-sm" style="color:var(--accent-purple); border-color:var(--accent-purple); width:100%; justify-content:center;" onclick="startFocusSigning('${seed.id}')">✍️ Sign This Seed</button>
          `}
        </div>
      </div>
    `;

    focusDiscussMessages = [];
    $('focus-panel').classList.add('active');
  }"""

if old_focus_panel_fn in content:
    content = content.replace(old_focus_panel_fn, new_focus_panel_fn, 1)
    print("2. Focus Panel function replaced with tabbed version.")
else:
    print("WARNING: Old focus panel function not found!")

# ─────────────────────────────────────────────────────────────
# 3. Add new helper functions after closeFocusPanel
# ─────────────────────────────────────────────────────────────

old_close_focus = """  function closeFocusPanel() {
    $('focus-panel').classList.remove('active');
    activeFocusSeedId = null;
    renderGardenList();
  }"""

new_close_focus_plus_helpers = """  function closeFocusPanel() {
    $('focus-panel').classList.remove('active');
    activeFocusSeedId = null;
    renderGardenList();
  }

  function switchFocusTab(tabName, btnEl) {
    document.querySelectorAll('.focus-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.focus-tab-content').forEach(c => { c.classList.remove('active'); c.style.display = 'none'; });
    if (btnEl) btnEl.classList.add('active');
    const panel = $('focus-tab-' + tabName);
    if (panel) { panel.classList.add('active'); panel.style.display = 'flex'; }
  }

  async function loadTranscriptViewer(transcriptId) {
    const container = $('transcript-viewer-container');
    const viewer = $('transcript-viewer-content');
    const btn = $('btn-load-transcript');

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
        // Format the transcript with colored roles
        let formatted = data.text;
        formatted = formatted.replace(/\\[user\\]:/gi, '<span class="transcript-role-user">[You]:</span>');
        formatted = formatted.replace(/\\[human\\]:/gi, '<span class="transcript-role-user">[You]:</span>');
        formatted = formatted.replace(/\\[assistant\\]:/gi, '<span class="transcript-role-assistant">[AI]:</span>');
        viewer.innerHTML = formatted;
      } else {
        viewer.textContent = 'Transcript not found or expired.';
      }
    } catch (e) {
      viewer.textContent = 'Failed to load transcript: ' + e.message;
    }
  }

  async function sendFocusDiscuss() {
    const input = $('focus-discuss-input');
    const text = input.value.trim();
    if (!text || !activeFocusSeedId) return;

    input.value = '';
    const msgs = $('focus-discuss-messages');

    // Show user message
    msgs.innerHTML += '<div class="discuss-msg user">' + esc(text) + '</div>';
    msgs.scrollTop = msgs.scrollHeight;

    // Show loading
    const loadId = 'discuss-load-' + Date.now();
    msgs.innerHTML += '<div class="discuss-msg assistant" id="' + loadId + '"><span class="spinner"></span> Thinking...</div>';
    msgs.scrollTop = msgs.scrollHeight;

    try {
      const resp = await SeedReflectionsPlatform.apiRequest('/seeds/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: { prompt: text, active_seed_id: activeFocusSeedId }
      });
      const data = await resp.json();
      $(loadId).innerHTML = renderMarkdown(data.answer);
    } catch (e) {
      $(loadId).innerHTML = '<span style="color:var(--accent-red);">Failed to reach AI backend.</span>';
    }
    msgs.scrollTop = msgs.scrollHeight;
  }

  function copySeedToClipboard(seedId) {
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;
    const text = '## ' + seed.title + '\\n\\n' + (seed.intent || seed.description) + '\\n\\nStatus: ' + seed.status + '\\nCreated: ' + (seed.created_at || 'today');
    navigator.clipboard.writeText(text).then(() => toast('Seed copied to clipboard!', 'success')).catch(() => toast('Copy failed', 'error'));
  }

  function downloadSeedMarkdown(seedId) {
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;
    const md = '# ' + seed.title + '\\n\\n**Status:** ' + seed.status + '  \\n**Created:** ' + (seed.created_at || 'today') + '\\n\\n---\\n\\n' + (seed.intent || seed.description);
    const blob = new Blob([md], {type: 'text/markdown'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (seed.title || 'seed').substring(0, 40).replace(/[^a-zA-Z0-9]/g, '_') + '.md';
    a.click();
    toast('Seed downloaded as markdown.', 'success');
  }"""

if old_close_focus in content:
    content = content.replace(old_close_focus, new_close_focus_plus_helpers, 1)
    print("3. Tab switching, transcript viewer, discuss chat, and export helpers added.")
else:
    print("WARNING: closeFocusPanel not found!")

# ─────────────────────────────────────────────────────────────
# 4. Clear search input on page load to prevent autofill
# ─────────────────────────────────────────────────────────────

old_page_init = """    await loadGarden();
    await refreshStats();"""

new_page_init = """    // Clear any browser autofill on search inputs
    const gardenSearch = $('garden-search');
    if (gardenSearch) gardenSearch.value = '';
    
    await loadGarden();
    await refreshStats();"""

# Only replace the first occurrence (the page init one)
if old_page_init in content:
    content = content.replace(old_page_init, new_page_init, 1)
    print("4. Search input cleared on page load.")
else:
    print("WARNING: Page init block not found!")

with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)

print("\n=== Dashboard patch complete ===")
