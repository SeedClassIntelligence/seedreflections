import os
import shutil

src_dir = r"C:\Users\SEEDN\Downloads\SRT1 CODING\srt1_platform\pwa"
dest_dir = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated"

print("--- Copying missing HTML pages ---")

if os.path.exists(src_dir):
    copied_files = []
    for filename in os.listdir(src_dir):
        if filename.endswith(".html") and filename != "index.html" and filename != "auth.html" and filename != "comparison.html":
            src_file = os.path.join(src_dir, filename)
            dest_file = os.path.join(dest_dir, filename)
            
            # Copy file
            shutil.copy2(src_file, dest_file)
            copied_files.append(filename)
            
    print("Successfully copied files:", copied_files)
else:
    print(f"Source directory {src_dir} not found!")
