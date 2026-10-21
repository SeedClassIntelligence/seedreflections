with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace CSS for garden filters to wrap instead of scroll
old_filters_css = """    .garden-filters {
      display: flex;
      gap: 6px;
      overflow-x: auto;
      padding-bottom: 4px;
    }"""

new_filters_css = """    .garden-filters {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding-bottom: 4px;
    }"""

if old_filters_css in content:
    content = content.replace(old_filters_css, new_filters_css, 1)
    print("1. CSS garden-filters updated to flex-wrap.")
else:
    print("WARNING: CSS garden-filters block not found!")

# 2. Replace reflect response card template in sendChatInput
old_reflect_card = """        if (resp.ok) {
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
          `;"""

new_reflect_card = """        if (resp.ok) {
          const seeds = data.seeds || [];
          loadEl.innerHTML = `
            <div class="msg-label">Seed Reflections</div>
            <div class="msg-bubble">
              <strong>${esc(data.answer)}</strong><br>
              <span style="font-size:12px; color:var(--text-muted); display:block; margin-top:6px;">
                All extracted sparks have been successfully planted in your Garden library sidebar on the left! Click on them in the library list to view details, plan operations, or chat directly about the original conversation context.
              </span>
            </div>
          `;"""

if old_reflect_card in content:
    content = content.replace(old_reflect_card, new_reflect_card, 1)
    print("2. sendChatInput reflect response template updated (removed list modal).")
else:
    print("WARNING: sendChatInput reflect response card template not found!")

# 3. Replace reflect response card template in importSelectedStagingWorkspace
old_staging_card = """      if (resp.ok) {
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
        `;"""

new_staging_card = """      if (resp.ok) {
        const seeds = data.seeds || [];
        loadEl.innerHTML = `
          <div class="msg-label">Seed Reflections</div>
          <div class="msg-bubble">
            <strong>${esc(data.answer)}</strong><br>
            <span style="font-size:12px; color:var(--text-muted); display:block; margin-top:6px;">
              All extracted sparks have been successfully planted in your Garden library sidebar on the left! Click on them in the library list to view details, plan operations, or chat directly about the original conversation context.
            </span>
          </div>
        `;"""

if old_staging_card in content:
    content = content.replace(old_staging_card, new_staging_card, 1)
    print("3. importSelectedStagingWorkspace response template updated (removed list modal).")
else:
    print("WARNING: importSelectedStagingWorkspace response card template not found!")

with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patching of rebuild_dashboard.py complete.")
