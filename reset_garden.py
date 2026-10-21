import os
import json
import shutil

seeds_path = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\seeds.json"
uploads_dir = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\uploads"
transcripts_dir = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\transcripts"

print("--- Resetting Garden Database and Workspace ---")

# 1. Reset seeds.json to empty array
try:
    with open(seeds_path, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)
    print("OK: seeds.json reset to empty database [].")
except Exception as e:
    print(f"Error resetting seeds.json: {e}")

# 2. Clear uploads directory
if os.path.exists(uploads_dir):
    try:
        for filename in os.listdir(uploads_dir):
            file_path = os.path.join(uploads_dir, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        print("OK: uploads/ directory cleared.")
    except Exception as e:
        print(f"Error clearing uploads/: {e}")
else:
    print("uploads/ directory does not exist.")

# 3. Clear transcripts directory
if os.path.exists(transcripts_dir):
    try:
        for filename in os.listdir(transcripts_dir):
            file_path = os.path.join(transcripts_dir, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        print("OK: transcripts/ directory cleared.")
    except Exception as e:
        print(f"Error clearing transcripts/: {e}")
else:
    print("transcripts/ directory does not exist.")

print("--- Reset complete. System is now at a pristine 0-seed state. ---")
