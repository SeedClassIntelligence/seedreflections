with open(r'c:\Users\SEEDN\Downloads\seed-reflection-isolated\consumer-dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Modify renderSeedCard actions section (around line 1322)
target_actions = """          ${s.is_cryptographically_signed ? `
          <div style="font-size:11px; background:#0f172a; padding:8px 12px; border-radius:6px; border:1px solid #1e293b; color:#10b981; font-family:monospace; margin-bottom:8px;">
            <div style="display:flex; align-items:center; gap:6px;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
              <strong>Verified & Secured by Seed Reflections Authority</strong>
            </div>
          </div>
          ` : `
          <div style="margin-bottom:8px; display:flex; justify-content:flex-end;">
            <button class="btn-ghost-sm" style="color:var(--accent-purple); border-color:var(--accent-purple); display:inline-flex; align-items:center; gap:4px;" onclick="event.stopPropagation(); startSeedSigning('${s.id || s.seed_id}')">✍️ Sign Seed</button>
          </div>
          `}"""

replacement_actions = """          <div style="margin-top:12px; margin-bottom:12px; display:flex; justify-content:flex-end; gap:8px;">
            <button class="btn-ghost-sm" style="color:var(--accent-blue); border-color:var(--accent-blue); display:inline-flex; align-items:center; gap:4px;" onclick="event.stopPropagation(); openHandoffModal('${s.id || s.seed_id}', '${esc(s.title)}')">🚀 Handoff</button>
            ${s.is_cryptographically_signed ? '' : `
              <button class="btn-ghost-sm" style="color:var(--accent-purple); border-color:var(--accent-purple); display:inline-flex; align-items:center; gap:4px;" onclick="event.stopPropagation(); startSeedSigning('${s.id || s.seed_id}')">✍️ Sign Seed</button>
            `}
          </div>

          ${s.is_cryptographically_signed ? `
          <div style="font-size:11px; background:#0f172a; padding:8px 12px; border-radius:6px; border:1px solid #1e293b; color:#10b981; font-family:monospace; margin-bottom:8px;">
            <div style="display:flex; align-items:center; gap:6px;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
              <strong>Verified & Secured by Seed Reflections Authority</strong>
            </div>
          </div>
          ` : ''}"""

if target_actions in content:
    content = content.replace(target_actions, replacement_actions, 1)
    print("Action buttons patched inside renderSeedCard.")
else:
    # Try alternate indentation match
    print("Warning: Action buttons block target not found, trying regex...")
    content = re.sub(r'\$\{s\.is_cryptographically_signed\s*\?.*?\s*\}\s*\}', replacement_actions, content, flags=re.DOTALL)

# 2. Add LLM Configuration Card in Settings Tab (around line 950)
target_settings = """      <!-- Account -->
      <div class="card" style="grid-column: 1 / -1;">"""

replacement_settings = """      <!-- LLM Configuration -->
      <div class="card" style="grid-column: 1 / -1;">
        <div class="card-head"><h3>🤖 LLM Provider Configuration</h3></div>
        <div class="card-content">
          <p style="font-size:13px; color:var(--text-secondary); line-height:1.65; margin-bottom:14px;">Select the backend LLM engine to power the Reflection Extraction protocol and conversation seed analysis.</p>
          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:16px; margin-bottom:16px;">
            <div class="form-group">
              <label style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px; font-weight:600;">ACTIVE LLM PROVIDER</label>
              <select id="llm-provider" onchange="toggleProviderFields()" style="width:100%; padding:10px; background:var(--bg-surface); border:1px solid var(--border); border-radius:6px; color:var(--text-primary); font-family:inherit;">
                <option value="ollama">Ollama (Local / Open Source)</option>
                <option value="gemini">Google Gemini (API Key)</option>
                <option value="openai">OpenAI (API Key)</option>
                <option value="anthropic">Anthropic Claude (API Key)</option>
              </select>
            </div>
            <div id="llm-api-url-group" class="form-group">
              <label style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px; font-weight:600;">ENDPOINT URL</label>
              <input type="text" id="llm-api-url" placeholder="http://127.0.0.1:11434" style="width:100%; padding:10px; background:var(--bg-surface); border:1px solid var(--border); border-radius:6px; color:var(--text-primary); font-family:inherit;" />
            </div>
            <div id="llm-model-group" class="form-group">
              <label style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px; font-weight:600;">MODEL NAME</label>
              <input type="text" id="llm-model" placeholder="llama3" style="width:100%; padding:10px; background:var(--bg-surface); border:1px solid var(--border); border-radius:6px; color:var(--text-primary); font-family:inherit;" />
            </div>
            <div id="llm-api-key-group" class="form-group" style="display:none;">
              <label style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px; font-weight:600;">API KEY</label>
              <input type="password" id="llm-api-key" placeholder="Enter API key..." style="width:100%; padding:10px; background:var(--bg-surface); border:1px solid var(--border); border-radius:6px; color:var(--text-primary); font-family:inherit;" />
            </div>
          </div>
          <button class="btn purple-grad" onclick="saveLLMSettings()">Save LLM Config</button>
        </div>
      </div>

      <!-- Account -->
      <div class="card" style="grid-column: 1 / -1;">"""

if target_settings in content:
    content = content.replace(target_settings, replacement_settings, 1)
    print("LLM config card inserted in settings tab.")
else:
    print("Error: Settings target not found.")

# 3. Add Handoff Modal at the end of the body (before toast container at line 969)
target_modal = """<div class="toast" id="toast"></div>"""

replacement_modal = """<!-- Handoff Modal -->
<div id="handoff-modal" class="modal-overlay" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:9999; background:rgba(0,0,0,0.8); align-items:center; justify-content:center;">
  <div class="modal-content" style="max-width:700px; width: 100%; background:var(--bg-card); padding:24px; border-radius:12px; border:1px solid var(--border);">
    <div class="modal-header" style="display:flex; justify-content:space-between; margin-bottom:12px; border-bottom:1px solid var(--border); padding-bottom:8px;">
      <h3 style="font-size:18px;font-weight:700">🚀 Code Assistant Handoff</h3>
      <button class="btn-ghost-sm" onclick="document.getElementById('handoff-modal').style.display='none'">✕</button>
    </div>
    <div style="font-size:12px; color:var(--text-muted); margin-bottom:16px;">
      Generate a clean Markdown context boot payload containing your seed intent and cryptographic signatures to feed directly into your coding assistant.
    </div>
    <input type="hidden" id="handoff-seed-id" />
    <input type="hidden" id="handoff-seed-title" />
    
    <div style="display:flex; gap:12px; align-items:center; margin-bottom:16px;">
      <label style="font-size:13px; font-weight:600; color:var(--text-secondary);">Target Coding Tool:</label>
      <select id="handoff-target" onchange="updateHandoffPayload()" style="padding:6px 12px; background:var(--bg-surface); border:1px solid var(--border); border-radius:6px; color:var(--text-primary); font-family:inherit;">
        <option value="claudecode">Claude Code / CLI</option>
        <option value="gemini">Google Gemini / Antigravity</option>
        <option value="generic">Generic LLM / ChatGPT</option>
      </select>
    </div>

    <textarea id="handoff-payload-box" readonly style="width:100%; height:250px; padding:12px; background:var(--bg-surface); border:1px solid var(--border); border-radius:8px; color:var(--text-primary); font-family:'JetBrains Mono', monospace; font-size:12px; resize:none; margin-bottom:16px;"></textarea>
    
    <div style="display: flex; justify-content: flex-end; gap: 12px;">
      <button class="btn-ghost" onclick="document.getElementById('handoff-modal').style.display='none'">Cancel</button>
      <button class="btn-ghost" onclick="copyHandoffText()" style="color:var(--blue); border-color:var(--blue);">📋 Copy Payload</button>
      <button class="btn purple-grad" onclick="downloadHandoffFile()">⬇ Download Context File (.md)</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>"""

if target_modal in content:
    content = content.replace(target_modal, replacement_modal, 1)
    print("Handoff modal markup added.")
else:
    print("Error: Toast markup target not found.")

# 4. Add JavaScript handlers inside script block
# Let's add them right before load() call (which is at line 1098/init code)
target_js = """    $('btn-logout').onclick = () => { SeedReflectionsPlatform.logout(); location.href = 'auth.html'; };
  }

  load();"""

replacement_js = """    $('btn-logout').onclick = () => { SeedReflectionsPlatform.logout(); location.href = 'auth.html'; };
    
    // Load LLM configuration settings on page load
    loadLLMSettings();
  }

  // ── LLM SETTINGS UTILITIES ───────────────────────────────────────────
  function toggleProviderFields() {
    const provider = $('llm-provider').value;
    const urlGroup = $('llm-api-url-group');
    const keyGroup = $('llm-api-key-group');
    const modelGroup = $('llm-model-group');
    
    if (provider === 'ollama') {
      urlGroup.style.display = 'block';
      keyGroup.style.display = 'none';
      modelGroup.style.display = 'block';
      $('llm-api-url').placeholder = 'http://127.0.0.1:11434';
      $('llm-model').placeholder = 'llama3';
    } else if (provider === 'gemini') {
      urlGroup.style.display = 'none';
      keyGroup.style.display = 'block';
      modelGroup.style.display = 'block';
      $('llm-model').placeholder = 'gemini-2.5-flash';
    } else {
      urlGroup.style.display = 'none';
      keyGroup.style.display = 'block';
      modelGroup.style.display = 'block';
      $('llm-model').placeholder = provider === 'openai' ? 'gpt-4o-mini' : 'claude-3-5-sonnet';
    }
  }

  async function loadLLMSettings() {
    try {
      const resp = await SeedReflectionsPlatform.apiRequest('/settings');
      if (resp.ok) {
        const cfg = await resp.json();
        $('llm-provider').value = cfg.llm_provider || 'ollama';
        $('llm-api-url').value = cfg.llm_api_url || '';
        $('llm-model').value = cfg.llm_model || '';
        $('llm-api-key').value = cfg.llm_api_key || '';
        toggleProviderFields();
      }
    } catch (e) {
      console.error("Failed to load LLM config:", e);
    }
  }

  async function saveLLMSettings() {
    try {
      const body = {
        llm_provider: $('llm-provider').value,
        llm_api_url: $('llm-api-url').value,
        llm_model: $('llm-model').value,
        llm_api_key: $('llm-api-key').value
      };
      const resp = await SeedReflectionsPlatform.apiRequest('/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: body
      });
      if (resp.ok) {
        toast('🤖 LLM Configuration successfully saved!', 'success');
      } else {
        toast('Failed to save LLM configuration', 'error');
      }
    } catch (e) {
      toast('Failed to save LLM configuration', 'error');
    }
  }

  // ── CODE ASSISTANT HANDOFF UTILITIES ─────────────────────────────────
  async function openHandoffModal(seedId, seedTitle) {
    $('handoff-seed-id').value = seedId;
    $('handoff-seed-title').value = seedTitle;
    $('handoff-modal').style.display = 'flex';
    updateHandoffPayload();
  }

  function updateHandoffPayload() {
    const seedId = $('handoff-seed-id').value;
    const seedTitle = $('handoff-seed-title').value;
    const assistant = $('handoff-target').value;
    
    // Find matching seed in cache
    const seed = gardenSeedsCache.find(s => s.id === seedId) || {};
    const intent = seed.intent || seed.description || seedTitle;
    const sig = seed.trust_state ? seed.trust_state.signature : 'unsigned';
    
    let instructions = '';
    if (assistant === 'claudecode') {
      instructions = `## Claude Code CLI Activation\\n\\nInitialize this task inside your Claude Code CLI session using:\\n\\n\`\`\`bash\\n# 1. Initialize seed workcell\\nclaude "Begin implementation of Seed reflections project task ${seedId}: '${intent}'"\\n\`\`\``;
    } else if (assistant === 'gemini') {
      instructions = `## Gemini Developer Assistant Boot\\n\\nProvide the following markdown context block to Gemini to start implementation:\\n\\n> \\"Please implement the feature described in this context block. Ensure matching the seed intentions.\\"`;
    } else {
      instructions = `## LLM Assistant Context Initialization\\n\\nPaste this block into your ChatGPT or custom LLM assistant prompt to initialize coding.`;
    }

    const payload = `# SEED HANDOFF CONTEXT BLOCK
========================================
[SEED_ID]   : ${seedId}
[TITLE]     : ${seedTitle}
[SIGNATURE] : ${sig}
[STATUS]    : ${seed.status || 'planted'}
[CREATED]   : ${seed.created_at || new Date().toISOString()}

## Intent / Requirement Description
${intent}

----------------------------------------
${instructions}

## Operational Alignment Rules
1. Maintain architectural boundary lines of the standalone project.
2. Focus strictly on intent compliance.
3. Once completed, request human validation before closing context.
`;
    
    $('handoff-payload-box').value = payload;
  }

  function copyHandoffText() {
    const box = $('handoff-payload-box');
    box.select();
    document.execCommand('copy');
    toast('📋 Context payload copied to clipboard!', 'success');
  }

  function downloadHandoffFile() {
    const payload = $('handoff-payload-box').value;
    const title = $('handoff-seed-title').value.replace(/[^a-z0-9_-]/gi, '_').toLowerCase();
    const blob = new Blob([payload], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `seed_handoff_${title}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast('⬇ Downloaded seed handoff context file.', 'success');
  }

  load();"""

if target_js in content:
    content = content.replace(target_js, replacement_js, 1)
    print("JavaScript handlers patched inside consumer-dashboard.html.")
else:
    print("Error: JS target not found.")

with open(r'c:\Users\SEEDN\Downloads\seed-reflection-isolated\consumer-dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Finished patching consumer-dashboard.html.")
