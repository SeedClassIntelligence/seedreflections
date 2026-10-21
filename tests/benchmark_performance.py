import time
import random
import sys
import os
import hashlib

# Adjust path to import server helpers
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

def generate_mock_data():
    print("Generating large-scale mock database...")
    db = {
        "projects": [
            {
                "project_id": "bench_project",
                "name": "Benchmark Project",
                "purpose": "Evaluate performance parameters under pressure and scale database traversal",
                "description": "A performance diagnostic workspace designed specifically for scale testing."
            }
        ],
        "seeds": [],
        "decisions": [],
        "conflicts": [],
        "relationships": []
    }

    # 1. 1000 seeds
    for i in range(1000):
        seed_id = f"seed_bench_{i}"
        intent = f"Implement scalability test check seed target index {i} database performance write lock"
        if i % 10 == 0:
            intent += " charter purpose parameter" # add match words
        
        # Some are signed
        is_signed = (i % 5 == 0)
        trust_state = {}
        if is_signed:
            core = f"Bench Seed {i}|{intent}|"
            digest = hashlib.sha256(core.encode("utf-8")).hexdigest()
            trust_state = {
                "signature": f"sig_bench_{i}",
                "digest": digest,
                "verification": "verified"
            }
        
        db["seeds"].append({
            "seed_id": seed_id,
            "project_id": "bench_project",
            "title": f"Bench Seed {i}",
            "intent": intent,
            "status": random.choice(["planted", "growing", "bloomed", "wilted"]),
            "continuity_status": "Active",
            "is_cryptographically_signed": is_signed,
            "trust_state": trust_state,
            "created_at": "2026-07-19T00:00:00Z",
            "child_seeds": [],
            "parent_seed_id": None,
            "related_seeds": []
        })

    # 2. 500 decisions
    for i in range(500):
        dec_id = f"dec_bench_{i}"
        # Links random seeds
        related = [f"seed_bench_{random.randint(0, 999)}" for _ in range(random.randint(1, 3))]
        db["decisions"].append({
            "decision_id": dec_id,
            "project_id": "bench_project",
            "decision_statement": f"Architectural scalability baseline decision check {i}",
            "status": "Accepted",
            "decision_type": "Architecture",
            "related_seeds": related
        })

    # 3. 2000 relationships
    relationship_types = list(server.RELATIONSHIP_REGISTRY.keys())
    for i in range(2000):
        rel_id = f"rel_bench_{i}"
        src = f"seed_bench_{random.randint(0, 999)}"
        tgt = f"seed_bench_{random.randint(0, 999)}"
        while src == tgt:
            tgt = f"seed_bench_{random.randint(0, 999)}"
        
        rel_type = random.choice(relationship_types)
        
        db["relationships"].append({
            "relationship_id": rel_id,
            "source_seed_id": src,
            "target_seed_id": tgt,
            "relationship_type": rel_type,
            "approval_status": "Approved",
            "proposed_by": "ai"
        })

    # Apply parent/child linkages based on approved relationships
    print("Rebuilding mock relationship references...")
    server.rebuild_relationship_references(db)
    return db

def benchmark_lost_seeds(db):
    print("\nRunning Lost Seeds engine benchmarks...")
    start = time.perf_counter()
    
    # Simulates server lost seeds calculation logic for all seeds
    lost_list = []
    # Build maps for instant access
    seed_ids = {s["seed_id"] for s in db["seeds"]}
    descendants_map = {s["seed_id"]: [] for s in db["seeds"]}
    for r in db["relationships"]:
        if r.get("approval_status") == "Approved":
            src = r["source_seed_id"]
            if src in descendants_map:
                descendants_map[src].append(r["target_seed_id"])

    decision_references_map = {s["seed_id"]: 0 for s in db["seeds"]}
    for d in db["decisions"]:
        for sid in d.get("related_seeds", []):
            if sid in decision_references_map:
                decision_references_map[sid] += 1

    for s in db["seeds"]:
        sid = s["seed_id"]
        # Protective Signals
        has_descendants = len(descendants_map[sid]) > 0
        has_decisions = decision_references_map[sid] > 0
        has_versions = len(s.get("versions", [])) > 0
        
        # absent from transcript (mock check)
        is_absent = True
        
        # Calculate Weighted Lost Seed Score
        score = 0.0
        # 1. No descendants (weight 0.25)
        score += 0.25 if not has_descendants else 0.0
        # 2. No decisions (weight 0.20)
        score += 0.20 if not has_decisions else 0.0
        # 3. No versions (weight 0.15)
        score += 0.15 if not has_versions else 0.0
        # 4. Absent from transcripts (weight 0.25)
        score += 0.25 if is_absent else 0.0
        # 5. Elapsed age (weight 0.15)
        score += 0.15

        classification = "Possible"
        if score >= 0.8:
            classification = "High Confidence Candidate"
        elif score >= 0.6:
            classification = "Likely Candidate"
            
        lost_list.append({
            "seed_id": sid,
            "score": round(score, 3),
            "classification": classification
        })
        
    duration = time.perf_counter() - start
    print(f"Lost Seeds Calculation complete for {len(db['seeds'])} seeds.")
    print(f"Time Taken: {duration:.5f} seconds ({duration * 1000:.2f} ms)")
    return duration

def benchmark_neighborhood_traversal(db):
    print("\nRunning Lineage Neighborhood Graph traversal benchmarks...")
    start = time.perf_counter()

    # Query neighborhood traversal centered around seed_bench_500 up to 3 hops
    center_id = "seed_bench_500"
    visited_nodes = {center_id}
    visited_edges = set()
    queue = [(center_id, 0)] # (node_id, hop_count)

    # Build index maps for faster retrieval
    edges_from_src = {}
    edges_from_tgt = {}
    for r in db["relationships"]:
        src = r["source_seed_id"]
        tgt = r["target_seed_id"]
        edges_from_src.setdefault(src, []).append(r)
        edges_from_tgt.setdefault(tgt, []).append(r)

    while queue:
        curr, hop = queue.pop(0)
        if hop >= 3:
            continue
        
        # Explore outgoing
        for r in edges_from_src.get(curr, []):
            edge_id = r["relationship_id"]
            if edge_id not in visited_edges:
                visited_edges.add(edge_id)
                tgt = r["target_seed_id"]
                if tgt not in visited_nodes:
                    visited_nodes.add(tgt)
                    queue.append((tgt, hop + 1))
        
        # Explore incoming
        for r in edges_from_tgt.get(curr, []):
            edge_id = r["relationship_id"]
            if edge_id not in visited_edges:
                visited_edges.add(edge_id)
                src = r["source_seed_id"]
                if src not in visited_nodes:
                    visited_nodes.add(src)
                    queue.append((src, hop + 1))

    duration = time.perf_counter() - start
    print(f"3-Hop Lineage Neighborhood traversal centered around {center_id} complete.")
    print(f"Discovered {len(visited_nodes)} nodes and {len(visited_edges)} relationship links.")
    print(f"Time Taken: {duration:.5f} seconds ({duration * 1000:.2f} ms)")
    return duration

def benchmark_intent_drift(db):
    print("\nRunning Intent Drift lexical overlap benchmarks...")
    start = time.perf_counter()

    project = db["projects"][0]
    charter_text = f"{project.get('purpose', '')} {project.get('description', '')}".lower()
    charter_words = {w.strip('.,?!()[]') for w in charter_text.split() if len(w) > 4}

    # Deterministic lexical overlap checking for all seeds
    uncovered_seeds = []
    matched_term_counts = {}
    
    for s in db["seeds"]:
        intent_text = s.get("intent", "").lower()
        intent_words = {w.strip('.,?!()[]') for w in intent_text.split() if len(w) > 4}
        overlap = charter_words.intersection(intent_words)
        
        for term in overlap:
            matched_term_counts[term] = matched_term_counts.get(term, 0) + 1

    duration = time.perf_counter() - start
    print(f"Lexical Charter Overlap checks complete for {len(db['seeds'])} seeds.")
    print(f"Time Taken: {duration:.5f} seconds ({duration * 1000:.2f} ms)")
    return duration

if __name__ == "__main__":
    print("=" * 60)
    print("SEED REFLECTION PERFORMANCE & TRAVERSAL BENCHMARK")
    print("=" * 60)
    db = generate_mock_data()
    t1 = benchmark_lost_seeds(db)
    t2 = benchmark_neighborhood_traversal(db)
    t3 = benchmark_intent_drift(db)
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Database Size: 1,000 Seeds | 500 Decisions | 2,000 Relationships")
    print(f"Lost Seeds Evaluation: {t1*1000:.2f} ms")
    print(f"Neighborhood Traversal: {t2*1000:.2f} ms")
    print(f"Intent Charter Drift Overlaps: {t3*1000:.2f} ms")
    print("=" * 60)
