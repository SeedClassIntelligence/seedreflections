import os

root_dir = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated"
server_path = os.path.join(root_dir, "server.py")

with open(server_path, "r", encoding="utf-8") as f:
    lines = f.read().splitlines()

# Find the line:         if path == "/sdk/seed-signature-widget.js":
target_idx = -1
for i, line in enumerate(lines):
    if 'if path == "/sdk/seed-signature-widget.js":' in line:
        target_idx = i
        break

if target_idx != -1:
    # Insert js_code = """ right after it
    lines.insert(target_idx + 1, '            js_code = """')
    print("Inserted js_code = \"\"\" successfully!")

with open(server_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print("Server patched.")
