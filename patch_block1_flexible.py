with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

found = False
for i in range(700, 760):
    if i < len(lines):
        if "for s in extracted_seeds:" in lines[i]:
            # Scan ahead up to 10 lines for new_seed
            for j in range(i+1, i+10):
                if "new_seed = {" in lines[j]:
                    # Find '"source": "conversation_extract"' inside this block
                    for k in range(j+1, j+10):
                        if '"source": "conversation_extract"' in lines[k]:
                            lines.insert(k+1, '                "source_transcript": transcript,\n')
                            found = True
                            break
                if found:
                    break
        if found:
            break

if found:
    with open(r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\server.py", "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("Block 1 updated successfully via flexible line search.")
else:
    print("WARNING: Block 1 target not found via flexible line search!")
