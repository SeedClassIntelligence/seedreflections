import re

file_path = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\rebuild_dashboard.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Fix emailSeed line:
old_email = """  function emailSeed(seedId) {
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;
    const subject = "Seed Reflection Spark: " + seed.title;
    const body = `Seed Intent:\\n${seed.intent || seed.description}\\n\\nProvenance Verification Signature:\\n${seed.trust_state ? seed.trust_state.signature : 'unsigned'}\\n\\nGenerated via Seed Reflections.`;
    window.location.href = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }"""

# Wait! Let's check what is currently in rebuild_dashboard.py:
# From view_file, it was:
# 1402:   function emailSeed(seedId) {
# 1403:     const seed = gardenSeedsCache.find(s => s.id === seedId);
# 1404:     if (!seed) return;
# 1405:     const subject = "Seed Reflection Spark: " + seed.title;
# 1406:     const body = `Seed Intent:
#           ${seed.intent || seed.description}
#           ...

# Yes, because Python parsed \n in the string, it wrote literal newlines into rebuild_dashboard.py too!
# Let's write a regex or a simple find/replace for emailSeed:
pattern_email = r'function emailSeed\(seedId\) \{.*?window\.location\.href = `mailto:\?subject=\$\{encodeURIComponent\(subject\)\}&body=\$\{encodeURIComponent\(body\)\}`;.*?\}'
# Let's replace the emailSeed function in the html_content:
new_email_js = """  function emailSeed(seedId) {
    const seed = gardenSeedsCache.find(s => s.id === seedId);
    if (!seed) return;
    const subject = "Seed Reflection Spark: " + seed.title;
    const body = `Seed Intent:\\\\n${seed.intent || seed.description}\\\\n\\\\nProvenance Verification Signature:\\\\n${seed.trust_state ? seed.trust_state.signature : 'unsigned'}\\\\n\\\\nGenerated via Seed Reflections.`;
    window.location.href = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }"""

# Let's replace the SNIPPETS prompt:
old_snippet = 'prompt: "Before we begin, here\'s where I left off in our last session:\\n\\n[Paste your last reflection summary here]\\n\\nPlease acknowledge what I was working on and help me continue from exactly that point."'
new_snippet = 'prompt: "Before we begin, here\'s where I left off in our last session:\\\\n\\\\n[Paste your last reflection summary here]\\\\n\\\\nPlease acknowledge what I was working on and help me continue from exactly that point."'

# Let's replace instructions in openFocusHandoff too:
# instructions = `## Claude Code CLI Activation\n\nInitialize this task...`
# Should be:
# instructions = `## Claude Code CLI Activation\\\\n\\\\nInitialize this task...`
old_handoff_js = """    let instructions = '';
    if (assistant === 'claudecode') {
      instructions = `## Claude Code CLI Activation\\n\\nInitialize this task inside your Claude Code CLI session using:\\n\\n\`\`\`bash\\n# 1. Initialize seed workcell\\nclaude "Begin implementation of Seed reflections project task ${seedId}: '${intent}'"\\n\`\`\``;
    } else if (assistant === 'gemini') {
      instructions = `## Gemini Developer Assistant Boot\\n\\nProvide the following markdown context block to Gemini to start implementation:\\n\\n> \"Please implement the feature described in this context block. Ensure matching the seed intentions.\"`;
    } else {
      instructions = `## LLM Assistant Context Initialization\\n\\nPaste this block into your ChatGPT or custom LLM assistant prompt to initialize coding.`;
    }"""

new_handoff_js = """    let instructions = '';
    if (assistant === 'claudecode') {
      instructions = `## Claude Code CLI Activation\\\\n\\\\nInitialize this task inside your Claude Code CLI session using:\\\\n\\\\n\`\`\`bash\\\\n# 1. Initialize seed workcell\\\\nclaude "Begin implementation of Seed reflections project task \${seedId}: '\${intent}'"\\\\n\`\`\``;
    } else if (assistant === 'gemini') {
      instructions = `## Gemini Developer Assistant Boot\\\\n\\\\nProvide the following markdown context block to Gemini to start implementation:\\\\n\\\\n> \\"Please implement the feature described in this context block. Ensure matching the seed intentions.\\"`;
    } else {
      instructions = `## LLM Assistant Context Initialization\\\\n\\\\nPaste this block into your ChatGPT or custom LLM assistant prompt to initialize coding.`;
    }"""

content = re.sub(r'function emailSeed\(seedId\) \{.*?window\.location\.href\s*=\s*`mailto:\?subject=\$\{encodeURIComponent\(subject\)\}&body=\$\{encodeURIComponent\(body\)\}`;.*?\}', new_email_js, content, flags=re.DOTALL)
content = content.replace(old_snippet, new_snippet)
content = content.replace(old_handoff_js, new_handoff_js)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("rebuild_dashboard.py repaired with proper double backslashes for newlines.")
