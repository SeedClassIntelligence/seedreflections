import json
import os

seeds_path = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\seeds.json"
sample_ids = {"seed_0701_RPG_fit", "seed_0703_meal_plan", "seed_0615_travel_local", "seed_0510_key_layout"}

if os.path.exists(seeds_path):
    with open(seeds_path, "r", encoding="utf-8") as f:
        try:
            seeds = json.load(f)
        except Exception:
            seeds = []
            
    before_len = len(seeds)
    # Filter out sample seeds
    cleaned_seeds = [s for s in seeds if s.get("seed_id") not in sample_ids]
    after_len = len(cleaned_seeds)
    
    with open(seeds_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_seeds, f, indent=2)
        
    print(f"Cleaned seeds database. Removed {before_len - after_len} sample seeds. Remaining: {after_len}")
else:
    print("seeds.json not found.")
