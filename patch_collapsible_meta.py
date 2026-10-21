with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

# Locate openFocusPanel replacement block
old_open_focus_panel = """  function openFocusPanel(seedId) {
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
  }"""

new_open_focus_panel = """  function openFocusPanel(seedId) {
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
      <div class="seed-meta-panel" id="active-seed-meta-panel" style="margin-bottom:24px; padding:20px; background:var(--bg-card); border:1px solid var(--border); border-radius:12px; display:flex; flex-direction:column; gap:16px; text-align:left; animation: fadeIn 0.2s ease-out; position:relative;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge ${badgeClass}">${seed.status}</span>
            <span style="font-size:11px; color:var(--text-dim);">Created ${seed.created_at ? seed.created_at.split('T')[0] : 'today'}</span>
          </div>
          <button class="btn-ghost-sm" id="btn-toggle-meta-collapse" onclick="toggleMetaPanelCollapse()" style="font-size:11.5px; padding:4px 10px;">▲ Collapse Details</button>
        </div>

        <div id="meta-expandable-content" style="display:flex; flex-direction:column; gap:16px;">
          <div>
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

  function toggleMetaPanelCollapse() {
    const content = $('meta-expandable-content');
    const btn = $('btn-toggle-meta-collapse');
    const panel = $('active-seed-meta-panel');
    
    if (content.style.display === 'none') {
      content.style.display = 'flex';
      btn.textContent = '▲ Collapse Details';
      panel.style.padding = '20px';
      panel.style.gap = '16px';
      panel.style.marginBottom = '24px';
    } else {
      content.style.display = 'none';
      btn.textContent = '▼ Expand Details';
      panel.style.padding = '10px 16px';
      panel.style.gap = '0';
      panel.style.marginBottom = '12px';
    }
  }"""

if old_open_focus_panel in content:
    content = content.replace(old_open_focus_panel, new_open_focus_panel, 1)
    print("openFocusPanel replaced successfully.")
else:
    print("WARNING: openFocusPanel block not found!")

with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patch complete.")
