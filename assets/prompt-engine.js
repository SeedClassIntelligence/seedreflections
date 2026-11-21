// ── UNIFIED PROMPT ENGINE CONSOLE LOGIC ──
var wizCurrentStep = 1;
var selectedPromptType = 'recovery'; // recovery, system, new_thread, snippet
var selectedSnippetNum = 1;
var selectedPlatform = 'ChatGPT';
var selectedLength = 'short';

function selectPromptType(type) {
  selectedPromptType = type;

  // Highlight card
  document.querySelectorAll('.wiz-card').forEach(function(c){
    c.classList.toggle('active', c.id === 'card-type-' + type);
    c.setAttribute('aria-pressed', c.classList.contains('active') ? 'true' : 'false');
  });

  // Show snippets subgrid if snippet mode is selected
  var subgrid = document.getElementById('snippets-subgrid');
  subgrid.style.display = (type === 'snippet') ? 'grid' : 'none';

  // Update footer button name
  var nextBtn = document.getElementById('btn-wiz-next');
  if (type === 'snippet') {
    nextBtn.textContent = 'Next: Choose Snippet ➔';
  } else {
    nextBtn.textContent = 'Next: Platform Details ➔';
  }
}

function selectSnippetCard(num) {
  selectedSnippetNum = num;
  document.querySelectorAll('.snippet-select-card').forEach(function(c){
    c.classList.toggle('active', c.id === 'scard-snip-' + num);
    c.setAttribute('aria-pressed', c.classList.contains('active') ? 'true' : 'false');
  });
}

function selectPlatformVal(plat) {
  selectedPlatform = plat;
}

function selectLengthVal(len) {
  selectedLength = len;
  var note = document.getElementById('wchunking-note');
  note.style.display = (len === 'long' || len === 'xlarge') ? 'flex' : 'none';
}

function switchWizPanel(step) {
  document.querySelectorAll('.wiz-step').forEach(function(p){ p.classList.remove('active'); });
  document.getElementById('wiz-step-' + step).classList.add('active');

  // Update indicators
  document.getElementById('wiz-step-indicator').textContent = 'Step ' + step + ' of 4';
  document.getElementById('wiz-progress-fill').style.width = (step * 25) + '%';

  // Update buttons
  var prevBtn = document.getElementById('btn-wiz-prev');
  var nextBtn = document.getElementById('btn-wiz-next');

  prevBtn.style.visibility = (step === 1) ? 'hidden' : 'visible';

  if (step === 4) {
    nextBtn.textContent = 'Reset Engine ↺';
  } else if (step === 3) {
    nextBtn.textContent = 'Generate Custom Prompt ✨';
  } else if (step === 1) {
    nextBtn.textContent = (selectedPromptType === 'snippet') ? 'Next: Choose Snippet ➔' : 'Next: Platform Details ➔';
  } else {
    nextBtn.textContent = (selectedPromptType === 'system') ? 'Generate Instructions ✨' : 'Next: Setup Focus ➔';
  }
}

function nextWizStep() {
  if (wizCurrentStep === 4) {
    // Reset wizard
    wizCurrentStep = 1;
    switchWizPanel(1);
    return;
  }

  // Routing skips logic based on mode
  if (wizCurrentStep === 1) {
    // If Pre-made snippet, skip step 2 & 3 and go straight to step 4 (pre-made)
    if (selectedPromptType === 'snippet') {
      wizCurrentStep = 4;
      compileWizardPrompt();
      switchWizPanel(4);
      return;
    }

    // Hide length options if not in recovery mode
    document.getElementById('wiz-length-block').style.display = (selectedPromptType === 'recovery') ? 'block' : 'none';

    wizCurrentStep = 2;
    switchWizPanel(2);
  } else if (wizCurrentStep === 2) {
    // If System Prompt, skip step 3 and go straight to step 4
    if (selectedPromptType === 'system') {
      wizCurrentStep = 4;
      compileWizardPrompt();
      switchWizPanel(4);
      return;
    }

    // Hide focus checklist if new thread starter
    document.getElementById('wiz-focus-block').style.display = (selectedPromptType === 'new_thread') ? 'none' : 'block';

    wizCurrentStep = 3;
    switchWizPanel(3);
  } else if (wizCurrentStep === 3) {
    wizCurrentStep = 4;
    compileWizardPrompt();
    switchWizPanel(4);
  }
}

function prevWizStep() {
  if (wizCurrentStep === 4) {
    if (selectedPromptType === 'snippet') {
      wizCurrentStep = 1;
      switchWizPanel(1);
      return;
    }
    if (selectedPromptType === 'system') {
      wizCurrentStep = 2;
      switchWizPanel(2);
      return;
    }
    wizCurrentStep = 3;
    switchWizPanel(3);
  } else if (wizCurrentStep === 3) {
    wizCurrentStep = 2;
    switchWizPanel(2);
  } else if (wizCurrentStep === 2) {
    wizCurrentStep = 1;
    switchWizPanel(1);
  }
}

function compileWizardPrompt() {
  var outputEl = document.getElementById('wiz-console-output');
  var sigEl = document.getElementById('wiz-console-title');
  var guideEl = document.getElementById('wiz-usage-guidelines');

  if (selectedPromptType === 'snippet') {
    var snip = PREMADE_SNIPPETS[selectedSnippetNum.toString()];
    var text = snip ? snip.text.replace(/\\n/g, '\n') : '';

    sigEl.textContent = 'SCIA v4.0 Pre-made Snippet';
    outputEl.textContent = text + '\n\n---SIGNATURE---\nType: Seed Reflections-PREMADE-SNIPPET-' + selectedSnippetNum + '\nProtocol: Seed Reflections (SCIA v4.0)\n---END SIGNATURE---';

    guideEl.innerHTML = `
      <li>Copy the snippet prompt.</li>
      <li>Open your target AI platform (ChatGPT, Claude, or Gemini).</li>
      <li>Paste this snippet to trigger prompt-level seed awareness instantly.</li>
    `;
    return;
  }

  if (selectedPromptType === 'system') {
    // Generate permanent custom system instructions
    var platKey = selectedPlatform.toLowerCase();
    if (platKey.indexOf('chatgpt') >= 0) platKey = 'chatgpt';
    else if (platKey.indexOf('claude') >= 0) platKey = 'claude';
    else if (platKey.indexOf('gemini') >= 0) platKey = 'gemini';
    else platKey = 'universal';

    var sysText = SYSTEM_INSTRUCTION_TEMPLATES[platKey] || SYSTEM_INSTRUCTION_TEMPLATES.universal;
    var sysGuideText = SYSTEM_GUIDE_TEXTS[platKey] || SYSTEM_GUIDE_TEXTS.universal;

    sigEl.textContent = 'SCIA Custom System Instructions (' + selectedPlatform + ')';
    outputEl.textContent = sysText;

    guideEl.innerHTML = `
      <li>Copy the instructions block above.</li>
      <li>${sysGuideText}</li>
      <li>All future conversations with this model will inherit seed-awareness automatically.</li>
    `;
    return;
  }

  if (selectedPromptType === 'new_thread') {
    // Generate thread starter
    var intent = document.getElementById('wiz-intent').value.trim();
    var starter = buildNewThreadPrompt(intent, selectedPlatform);

    sigEl.textContent = 'SCIA New Thread Starter (' + selectedPlatform + ')';
    outputEl.textContent = starter;

    guideEl.innerHTML = `
      <li>Copy the thread starter text.</li>
      <li>Paste it as the first prompt in a new conversation with your AI assistant.</li>
      <li>This initializes the context bounds for your new idea, preventing drift.</li>
    `;
    return;
  }

  if (selectedPromptType === 'recovery') {
    // Recovery prompt builder
    var intent = document.getElementById('wiz-intent').value.trim();

    // Focus areas
    const focuses = [];
    if (document.getElementById('wfocus-stuck').checked)     focuses.push('stuck');
    if (document.getElementById('wfocus-code').checked)      focuses.push('code');
    if (document.getElementById('wfocus-ideas').checked)     focuses.push('ideas');
    if (document.getElementById('wfocus-next').checked)      focuses.push('next');
    if (document.getElementById('wfocus-drift').checked)     focuses.push('drift');
    if (document.getElementById('wfocus-decisions').checked) focuses.push('decisions');

    var recPrompt = buildPrompt(intent, selectedPlatform, selectedLength, focuses);
    var recSig = buildSignature(selectedPlatform, selectedLength, focuses);

    sigEl.textContent = 'SCIA Recovery Prompt (' + selectedPlatform + ')';
    outputEl.textContent = recPrompt + '\n\n---GENERATOR-SIGNATURE---\n' + recSig + '\n---END---';

    guideEl.innerHTML = `
      <li>Copy the full prompt.</li>
      <li>Open your target AI chat window.</li>
      <li>Paste the prompt first, then paste your conversation logs directly after it.</li>
    `;
  }
}

function copyWizardOutputPrompt() {
  const text = document.getElementById('wiz-console-output').textContent;
  navigator.clipboard.writeText(text).then(function() {
    const btn = document.getElementById('btn-wiz-copy');
    const orig = btn.textContent;
    btn.textContent = '✓ Copied!';
    setTimeout(function() { btn.textContent = orig; }, 2000);
  });
}
const SYSTEM_INSTRUCTION_TEMPLATES = {
  chatgpt: `You are a Seed Reflection assistant running under the SCIA v4.0 architecture.
Your goal is to maintain absolute context continuity and help the user track their intentions.

1. CORE INTENT: Identify and remember the user's primary goal introduced at the start of the chat.
2. DRIFT MONITORING: If the conversation shifts focus, explicitly mention that the topic is drifting, and suggest how to return to the original seed.
3. SIGNATURE STAMP: When the user requests a handoff or session summary, or at the end of key milestones, append this block:
---SEED-SIGNATURE---
Type: Seed Reflections-SYSTEM-RECORD
Intent-Preserved: [Yes/No/Partial]
Drift-Score: [0-100, where 0 is perfect alignment]
Next-Seed: [Actionable next step]
---END-SIGNATURE---`,

  claude: `You are a Seed Reflection specialist running under the SCIA v4.0 architecture.
Help the user track intentions, monitor conversation drift, and verify goals using your XML thinking blocks.

1. CORE INTENT: Extract the user's primary intent from their opening message and log it inside a silent planning block.
2. DRIFT MONITORING: Call out when discussions veers into unrelated technical debugging or tangents.
3. SIGNATURE STAMP: Append the standard Seed Reflections signature stamp at the end of key summaries:
---SEED-SIGNATURE---
Type: Seed Reflections-SYSTEM-RECORD
Intent-Preserved: [Yes/No/Partial]
Drift-Score: [0-100]
Next-Seed: [Actionable next step]
---END-SIGNATURE---`,

  gemini: `You are a Seed Reflection assistant running under the SCIA v4.0 architecture.
Help the user track their intentions, monitor conversation drift, and output a structured [SEED-SIG] block.

Focus on the user's original intentions. If they drift, alert them.
At the end of summaries, output this signature block:
---SEED-SIGNATURE---
Type: Seed Reflections-SYSTEM-RECORD
Intent-Preserved: [Yes/No/Partial]
Drift-Score: [0-100]
Next-Seed: [Actionable next step]
---END-SIGNATURE---`,

  universal: `You are a Seed Reflection assistant running under the SCIA v4.0 architecture.
Help the user track their intentions, monitor conversation drift, and output a structured [SEED-SIG] block containing: Intent-Preserved status, Drift-Score, and Next-Seed when summarizing or when requested.`
};

const SYSTEM_GUIDE_TEXTS = {
  chatgpt: `Copy the instructions. Paste them inside ChatGPT's <strong>"How would you like ChatGPT to respond?"</strong> input field under Custom Instructions settings.`,
  claude: `Copy the instructions. Paste them inside the <strong>"System Prompt"</strong> field of your Claude Custom Project configuration to apply it to all chats in the project.`,
  gemini: `Copy the instructions. Paste them into the <strong>"System Prompt"</strong> text block when creating or editing your custom Gemini Gem.`,
  universal: `Copy the instructions. Paste them as a system prompt parameter or initial pre-prompt instructions in your custom LLM client/endpoint interface.`
};

// 7 Universal Snippets Data
const PREMADE_SNIPPETS = {
  "1": {
    desc: "Use this snippet at the very start of a chat session to state your project goals, setting up strict contextual borders so the model doesn't drift.",
    text: `🌱 SEED PLANT — SCIA v4.0\n\nMy intent for this conversation:\n[YOUR GOAL HERE]\n\nKey constraints: [any limits]\nSuccess looks like: [what done means]\n\nPlease confirm you've received this seed and repeat it back before we begin.`
  },
  "2": {
    desc: "Scan the current conversation history to find ideas, feature requests, or details that were discussed but abandoned.",
    text: `🔍 SEED RECOVERY — SCIA v4.0\n\nReview this conversation and identify:\n1. Every idea I mentioned but didn't complete\n2. Every project I started but abandoned\n3. Every question I raised but never answered\n\nFor each, give me: what it was, why it matters, and the single next action to pick it up.`
  },
  "3": {
    desc: "Mid-conversation audit: Ask the AI to compare the current direction of the conversation against the original seed goal.",
    text: `📊 COHERENCE CHECK — SCIA v4.0\n\nOriginal goal: [paste your opening message]\n\nAre we still working toward that goal?\nWhat have we drifted from?\nWhat should we do next to get back on track?`
  },
  "4": {
    desc: "Generate a markdown planning bundle of the session, ready to paste into a new chat session to maintain continuity.",
    text: `📋 SESSION HANDOFF — SCIA v4.0\n\nGenerate a handoff summary I can paste into a new conversation:\n1. My original goal\n2. What we accomplished\n3. What's still unfinished\n4. The exact next step\n5. Any important context a new session needs`
  },
  "5": {
    desc: "Lists all abandoned seeds from the conversation history and ranks them based on complexity vs impact.",
    text: `🎯 PRIORITY RECOVERY — SCIA v4.0\n\nFrom this conversation, list every abandoned idea.\nScore each on:\n- Impact (1-10): how much does completing this matter?\n- Effort (1-10): how hard is it?\n- Urgency (high/medium/low)\n\nSort by Impact/Effort ratio. Tell me what to do first.`
  },
  "6": {
    desc: "Instruct the AI to generate a signature block verification receipt at the end of its response.",
    text: `✍️ PROVENANCE STAMP REQUEST — SCIA v4.0\n\nPlease end your response with a Provenance Stamp block:\n\n[SEED-SIG]\nContent-Hash: {first 8 chars of SHA-256 of response}\nIntent-Preserved: {yes/partial/no}\nDrift-Score: {0-100, where 0 = perfect alignment}\nNext-Seed: {the logical next question or action}\n[/SEED-SIG]`
  },
  "7": {
    desc: "Bootstraps a fresh seed structure containing milestones, dependencies, and success criteria based on your project description.",
    text: `🚀 PROJECT BOOTSTRAP — SCIA v4.0\n\nIdea: [YOUR IDEA]\n\nHelp me structure this as a Seed Reflections project:\n1. Core intent (one sentence)\n2. Top 5 seeds (specific, actionable tasks)\n3. Dependencies between seeds\n4. What to build first and why\n5. Success criteria for the whole project`
  }
};

function toggleFocusStyle(labelId, chk) {
  var el = document.getElementById(labelId);
  if (el) el.classList.toggle('checked', chk.checked);
}

function buildPrompt(intent, platform, length, focuses) {
  const lines = [];
  const isXL  = length === 'xlarge';
  const isLong = length === 'long' || length === 'xlarge';

  lines.push('You are a senior Seed Reflection Analyst running under the Seed Reflections Protocol (SCIA v4.0).');
  lines.push('Your objective is to perform a deep semantic audit on the conversation log appended below and compile a high-fidelity Seed Reflection Report.');
  lines.push('');

  if (intent) {
    lines.push('## 🎯 Primary User Intent Seed');
    lines.push('The primary objective the user set out to achieve in this session:');
    lines.push('"' + intent + '"');
    lines.push('');
    lines.push('All analysis of drift, alignment, and recovery priorities must be calculated relative to this intent.');
    lines.push('');
  }

  lines.push('## 📐 Session Context');
  lines.push('- Ingestion Source: Public conversation log');
  lines.push('- Target Platform: ' + platform);
  lines.push('- Conversation Length: ' + { short: 'Short (under 10K tokens)', medium: 'Medium (10K–50K tokens)', long: 'Long (50K–200K tokens)', xlarge: 'Very Long (500K+ tokens)' }[length]);
  lines.push('');

  if (isXL) {
    lines.push('## 🌊 Large-Scale Context Partitioning (Chunking Strategy)');
    lines.push('Because this conversation is extremely long, you must use a rolling multi-pass audit strategy:');
    lines.push('1. PASS 1 (Seed Discovery Skim): Scan the entire text. Tag the exact message indexes where new goals, features, or questions are introduced.');
    lines.push('2. PASS 2 (Deep Semantic Crawl): For each tagged milestone, crawl the surrounding turns to analyze developers decisions, friction points, and code modules.');
    lines.push('3. PASS 3 (Synthesis): Consolidate findings, calculate the exact coherence metric, and generate recovery prompts.');
    lines.push('');
  }

  lines.push('## 📋 Analysis Protocols & Formatting Rules');
  lines.push('Your output report must adhere to the following strict markdown layout. Do not include introductory chatter.');
  lines.push('');

  // Section 1: Seed Catalog
  lines.push('### 1. 🌱 SEED CATALOG');
  lines.push('Identify every goal, project, task, feature, or plan introduced in this chat.');
  lines.push('Render this as a Markdown table with the columns:');
  lines.push('| Seed ID | Description (Max 15 words) | Status (ACTIVE / COMPLETED / ABANDONED / DRIFTING) | Location (Start/Mid/End) | Relevance to Primary Intent (HIGH/MED/LOW) |');
  lines.push('');
  lines.push('Use the following criteria for Status:');
  lines.push('- ACTIVE: The seed was actively developed and remains in focus at the end of the session.');
  lines.push('- COMPLETED: The task or feature was fully built, verified, and concluded.');
  lines.push('- ABANDONED: The seed was proposed but dropped or bypassed without progress.');
  lines.push('- DRIFTING: Work was started on the seed, but the conversation shifted before completion.');
  lines.push('');

  // Section 2: Stuck points
  if (focuses.includes('stuck')) {
    lines.push('### 2. 🧱 friction & stuck analysis');
    lines.push('For every moment work stalled or failed:');
    lines.push('- Root Cause: Categorize the bottleneck (e.g., Code syntax limits, ambiguous prompt requirements, context shifts, tool failure, or technical blocker).');
    lines.push('- Technical Impact: What was blocked or broken?');
    lines.push('- Unblocking Command: Suggest a single, clear instruction to solve or bypass this block.');
    lines.push('');
  }

  // Section 3: Code inventory
  if (focuses.includes('code')) {
    lines.push('### 3. 💾 code & content inventory');
    lines.push('List all code modules, scripts, files, or documents built or discussed:');
    lines.push('- Completed Assets: List names and paths of functional code snippets.');
    lines.push('- Incomplete Code: List code that was started but remains unfinished (note exactly what functions or lines are missing).');
    lines.push('- Planned but Unwritten: List files or directories discussed but never created.');
    lines.push('');
  }

  // Section 4: Drift analysis
  if (focuses.includes('drift')) {
    lines.push('### 4. 🌊 drift & coherence analysis');
    lines.push('Calculate the exact Coherence Score (0-100%) against the Primary Intent Seed using this formula:');
    lines.push('Coherence = (AlignTurns / TotalTurns) * 100 [Subtract 15 points per major drift occurrence].');
    lines.push('');
    lines.push('Describe the drift journey arc:');
    lines.push('- Trigger: What message or prompt caused the focus to shift?');
    lines.push('- Tangent: What did the conversation focus on instead?');
    lines.push('- Recovery status: Did the conversation ever return to the primary seed?');
    lines.push('');
  }

  // Section 5: Decisions
  if (focuses.includes('decisions')) {
    lines.push('### 5. ⚖️ architectural decisions log');
    lines.push('List every design pattern, technical choice, or architectural decision made:');
    lines.push('- Decision: What pattern or library was selected?');
    lines.push('- Alternatives Considered: What else was suggested?');
    lines.push('- Rationale: Why was this specific path chosen?');
    lines.push('');
  }

  // Section 6: Next Steps & Recovery Envelopes
  lines.push('### 6. 🍂 recovery envelopes & next steps');
  lines.push('Provide a priority list of 3 actionable next steps to recover abandoned seeds.');
  lines.push('For each next step, output a "RECOVERY ENVELOPE" block (formatted as a copyable markdown quote block):');
  lines.push('```');
  lines.push('[RECOVERY-PROMPT]');
  lines.push('You are resuming a previous session. Here is our context state:');
  lines.push('Goal: [1-sentence goal]');
  lines.push('Current Code State: [summarize built modules]');
  lines.push('Blocked At: [summarize current blocker]');
  lines.push('Next Task: [specific instruction to run]');
  lines.push('[/RECOVERY-PROMPT]');
  lines.push('```');
  lines.push('');

  lines.push('## Required SCIA Verification Block');
  lines.push('At the end of your report, append this exact verification signature (replace bracketed variables with metrics):');
  lines.push('');
  lines.push('---SEED-SIGNATURE---');
  lines.push('Type: Seed Reflections-CUSTOM-RECOVERY-REPORT');
  lines.push('Platform: ' + platform);
  lines.push('Total-Seeds-Found: [number]');
  lines.push('Coherence-Score: [0-100]%');
  lines.push('Drift-Points-Logged: [number]');
  lines.push('---END-SIGNATURE---');
  lines.push('');
  lines.push('---');
  lines.push('[PASTE YOUR CONVERSATION TRANSCRIPT LOG BELOW THIS LINE]');
  lines.push('');

  return lines.join('\n');
}

function buildNewThreadPrompt(intent, platform) {
  var lines = [];
  lines.push('=== Seed Reflections PROTOCOL ACTIVATED ===');
  lines.push('');
  lines.push('I want this conversation to follow the Seed Reflections (SCIA v4.0) protocol to keep our progress focused, prevent topic drift, and track active milestones.');
  lines.push('');
  lines.push('1. 🎯 PRIMARY SEED (MAIN GOAL):');
  lines.push('"' + (intent || '[ YOUR GOAL HERE ]') + '"');
  lines.push('');
  lines.push('2. 📋 CORE OPERATING RULES:');
  lines.push('• DRIFT DETECTION: Monitor topic drift. If we drift off-topic, explicitly output: "Drift detected — refocus?" and prompt me to either refocus or explicitly branch the seed.');
  lines.push('• PROGRESS CHECKPOINTS: Every 4-5 exchanges, output a brief checklist marking accomplished milestones toward the seed.');
  lines.push('• SEED EXTRACTION: Capture any new ideas or feature requests that arise as "[SEED FOUND: Description]" but do not pursue them unless I explicitly request a scope branch.');
  lines.push('• ARCHITECTURAL INTEGRITY: Ensure all code proposed is robust, adheres to modular standards, and features clean separation of concerns.');
  lines.push('');

  if (platform === 'Claude') {
    lines.push('3. 🔮 CLAUDE OPTIMIZATION:');
    lines.push('Leverage your internal XML thinking blocks to audit user requests against the primary seed before outputting responses. Note drift indicators inside your thinking blocks.');
  } else if (platform === 'ChatGPT') {
    lines.push('3. 💬 CHATGPT OPTIMIZATION:');
    lines.push('Prioritize clean structure, structured markdown logs, and clear bullet points for checkpoints.');
  } else if (platform === 'Gemini') {
    lines.push('3. ♊ GEMINI OPTIMIZATION:');
    lines.push('Acknowledge personal productivity context. Help me stay productive by keeping explanations focused and concise.');
  }
  lines.push('');

  lines.push('4. 📊 REQUIRED SESSION SUMMARY (REFLECT):');
  lines.push('When I state "reflect" or "end session", output a Seed Reflections Report containing:');
  lines.push('  • ACCOMPLISHED: Detailed list of what was fully built or solved.');
  lines.push('  • PENDING: Unfinished tasks or pending features.');
  lines.push('  • NEW SEEDS: Captured tangents/ideas.');
  lines.push('  • NEXT ACTIONS: Actionable priority steps to resume work.');
  lines.push('');
  lines.push('Please acknowledge this protocol with: "🌱 Seed locked: [your 1-sentence summary of my goal]" and then let\'s begin.');
  lines.push('');
  lines.push('===');

  return lines.join('\n');
}

function buildSignature(platform, length, focuses) {
  const now     = new Date().toISOString();
  const focuStr = focuses.length > 0 ? focuses.join(', ') : 'none selected';
  const sid     = 'Seed Reflections-GEN-' + now.replace(/[-:.TZ]/g, '').slice(0, 14);
  return [
    'Signature-ID : ' + sid,
    'Generated-At : ' + now,
    'Generator    : Seed Reflection Prompt Generator v1.0',
    'Platform     : ' + platform,
    'Length-Class : ' + length,
    'Focus-Areas  : ' + focuStr,
    'Protocol     : Seed Reflections (Seed Reflections Architecture)',
  ].join('\n');
}

// Load the one public prompt builder into either the standalone page or dashboard.
async function loadPromptBuilder() {
  const host = document.getElementById('prompt-builder-host');
  if (!host || host.dataset.loaded === 'true') return;
  try {
    const response = await fetch('assets/prompt-builder.html');
    if (!response.ok) throw new Error('Prompt builder could not be loaded.');
    host.innerHTML = await response.text();
    host.querySelectorAll('.wiz-card, .snippet-select-card').forEach(function(card) {
      card.setAttribute('role', 'button');
      card.tabIndex = 0;
      card.setAttribute('aria-pressed', card.classList.contains('active') ? 'true' : 'false');
      card.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          card.click();
        }
      });
    });
    host.dataset.loaded = 'true';
  } catch (error) {
    host.textContent = 'The prompt builder could not be loaded. Refresh this page to try again.';
  }
}
loadPromptBuilder();
