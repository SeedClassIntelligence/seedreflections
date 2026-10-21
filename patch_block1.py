with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

found = False
# Locate Block 1 inside reflect_selected endpoint
# It has "for c in selected_convs:" earlier (around line 810) and then:
# "for s in extracted_seeds:" (around line 895) and new_seed dictionary.
# Let's search from line 750 to 900
for i in range(700, 770):
    if i < len(lines):
        if "for s in extracted_seeds:" in lines[i] and "new_seed = {" in lines[i+3]:
            # Find '"source": "conversation_extract"' inside this block
            for j in range(i+4, i+12):
                if '"source": "conversation_extract"' in lines[j]:
                    lines.insert(j+1, '            "source_transcript": transcript,\n')
                    found = True
                    break
            if found:
                break

if found:
    with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("Block 1 updated successfully via line search.")
else:
    print("WARNING: Block 1 target not found via line search!")
