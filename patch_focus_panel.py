"""
Replace openFocusPanel function using line-based approach.
"""

with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find the start of openFocusPanel
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if "  function openFocusPanel(seedId) {" in line and "// ── FOCUS DETAILS" in lines[i-1]:
        start_idx = i - 1  # Include the comment
    if start_idx and i > start_idx and "  function closeFocusPanel()" in line:
        end_idx = i
        break

if start_idx is None or end_idx is None:
    # Try alternate search
    for i, line in enumerate(lines):
        if "  function openFocusPanel(seedId) {" in line and start_idx is None:
            start_idx = i
        if start_idx and i > start_idx and "  function closeFocusPanel()" in line:
            end_idx = i
            break

if start_idx is not None and end_idx is not None:
    print(f"Found openFocusPanel at lines {start_idx+1}-{end_idx}")
    
    new_fn = '''  // ── FOCUS DETAILS PANEL UTILITIES ────────────────────────────
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
      <div class="focus-tabs">
        <button class="focus-tab active" onclick="switchFocusTab('overview', this)">📋 Overview</button>
        <button class="focus-tab" onclick="switchFocusTab('discuss', this)">💬 Discuss</button>
        <button class="focus-tab" onclick="switchFocusTab('actions', this)">⚡ Actions</button>
      </div>

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

        ${hasTranscript ? \\`
          <div>
            <button class="btn-ghost-sm" style="width:100%; justify-content:center; gap:6px;" onclick="loadTranscriptViewer('${seed.source_transcript_id}')" id="btn-load-transcript">
              📜 View Original Conversation
            </button>
            <div id="transcript-viewer-container" style="display:none; margin-top:12px;">
              <div class="transcript-viewer" id="transcript-viewer-content">Loading...</div>
            </div>
          </div>
        \\` : \\`
          <div style="font-size:11.5px; color:var(--text-dim); padding:12px; background:var(--bg-deep); border-radius:6px; text-align:center;">
            No source transcript attached to this seed.
          </div>
        \\`}
      </div>

      <div class="focus-tab-content" id="focus-tab-discuss" style="padding:16px; flex:1; display:none; flex-direction:column; height: calc(100vh - 180px);">
        <div style="margin-bottom:10px;">
          <p style="font-size:11.5px; color:var(--text-dim); line-height:1.4;">
            Chat about this seed. ${hasTranscript ? 'The AI has the full original conversation for context.' : ''}
          </p>
        </div>
        <div class="focus-discuss-messages" id="focus-discuss-messages">
          <div class="discuss-msg assistant">
            👋 Ready to discuss: <strong>${esc(seed.title.substring(0, 60))}</strong>.
            ${hasTranscript ? "I have the original conversation loaded. Ask me anything about it!" : "What would you like to explore?"}
          </div>
        </div>
        <div class="focus-discuss-input-area">
          <textarea class="focus-discuss-input" id="focus-discuss-input" placeholder="Ask about this seed..." rows="1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendFocusDiscuss();}"></textarea>
          <button class="btn purple-grad" style="padding:8px 14px; font-size:12px; border-radius:6px;" onclick="sendFocusDiscuss()">Send</button>
        </div>
      </div>

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
          <p style="font-size:10.5px; color:var(--text-dim); line-height:1.4;">Creates a structured markdown envelope to share with external AI code assistants.</p>
        </div>

        <div style="display:flex; flex-direction:column; gap:10px; padding:16px; background:rgba(255,255,255,0.02); border:1px solid var(--border); border-radius:10px;">
          <h4 style="font-size:12px; font-weight:800; color:var(--text-secondary);">🔐 Provenance & Trust</h4>
          ${seed.is_cryptographically_signed ? \\`
            <div style="font-size:11px; background:#0f172a; padding:10px 12px; border-radius:6px; border:1px solid #1e293b; color:#10b981; font-family:monospace;">
              <strong>Verified & Secured</strong><br>
              <span style="font-size:9.5px; color:var(--text-dim);">Sig: ${esc(seed.trust_state?.signature)}</span>
            </div>
          \\` : \\`
            <button class="btn-ghost-sm" style="color:var(--accent-purple); border-color:var(--accent-purple); width:100%; justify-content:center;" onclick="startFocusSigning('${seed.id}')">✍️ Sign This Seed</button>
          \\`}
        </div>
      </div>
    `;

    focusDiscussMessages = [];
    $('focus-panel').classList.add('active');
  }

'''
    # Fix the escaped backticks - in the rebuild_dashboard.py context, these are inside a Python string
    # that gets written as JS. The \\` should just be backtick
    new_fn = new_fn.replace('\\`', '`')
    
    new_lines = [line + '\n' for line in new_fn.split('\n')]
    lines = lines[:start_idx] + new_lines + lines[end_idx:]
    
    with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("openFocusPanel replaced successfully.")
else:
    print(f"FAILED: start_idx={start_idx}, end_idx={end_idx}")
