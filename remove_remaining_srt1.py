import os

files_to_remove = [
    "documentation.html",
    "contact.html",
    "dashboard.html"
]

base_dir = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated"

print("--- Removing remaining SRT-1 files ---")
for f in files_to_remove:
    file_path = os.path.join(base_dir, f)
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"Removed: {f}")
    else:
        print(f"Not found: {f}")

print("Clean-up complete.")
