import os

srt1_files = [
    "constellation.html",
    "observatory.html",
    "srt1-core.html",
    "health.html",
    "mobile.html",
    "workspace-demo.html"
]

base_dir = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated"

print("--- Removing SRT-1 pages from standalone directory ---")
for f in srt1_files:
    file_path = os.path.join(base_dir, f)
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"Removed: {f}")
    else:
        print(f"Not found: {f}")

print("Clean-up complete. Standalone directory is isolated to Seed Reflections.")
