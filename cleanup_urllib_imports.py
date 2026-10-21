with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "r", encoding="utf-8") as f:
    content = f.read()

# Let's count occurrences of "import urllib.request"
print("Before cleanup, occurrences of 'import urllib.request':", content.count("import urllib.request"))

# Replace indented "import urllib.request" lines
# We will do this line-by-line so we don't affect the top-level import
lines = content.splitlines()
cleaned_lines = []
removed_count = 0
for idx, line in enumerate(lines):
    # If it is an indented import urllib.request statement, skip it
    if line.strip() == "import urllib.request" and line.startswith(" "):
        removed_count += 1
        continue
    cleaned_lines.append(line)

new_content = "\n".join(cleaned_lines)
print(f"Removed {removed_count} local import lines.")
print("After cleanup, occurrences of 'import urllib.request':", new_content.count("import urllib.request"))

with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("Cleanup complete.")
