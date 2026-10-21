import json
import os

seeds_file = r"c:\Users\SEEDN\Downloads\seed-reflection-isolated\seeds.json"

sample_seeds = [
    {
        "seed_id": "seed_0701_RPG_fit",
        "intent": "Create a fitness app that turns daily steps and workouts into RPG quests with item drops, leveling, and guild battles.",
        "source": "conversation_extract",
        "status": "growing",
        "growth": 45,
        "created_at": "2026-07-01T10:00:00Z",
        "completed_at": None,
        "is_cryptographically_signed": True,
        "trust_state": {
            "signature": "sig_9a7c3b2f81d5",
            "verification": "verified",
            "lineage": "present"
        },
        "verification_result": {
            "certificate_url": "http://127.0.0.1:7484/certificates/cert_RPG_fit",
            "signed_at": "2026-07-02T12:00:00Z"
        }
    },
    {
        "seed_id": "seed_0703_meal_plan",
        "intent": "Build a meal planner that automatically adjusts ingredient lists based on custom macronutrient goals and pantry inventory scanned via camera.",
        "source": "web",
        "status": "planted",
        "growth": 0,
        "created_at": "2026-07-03T15:30:00Z",
        "completed_at": None,
        "is_cryptographically_signed": False,
        "trust_state": {
            "signature": "unsigned",
            "verification": "unverified",
            "lineage": "missing"
        }
    },
    {
        "seed_id": "seed_0615_travel_local",
        "intent": "Generate non-touristy travel itineraries emphasizing local hosts, small family-owned restaurants, and public transit navigation guides.",
        "source": "conversation_extract",
        "status": "bloomed",
        "growth": 100,
        "created_at": "2026-06-15T09:00:00Z",
        "completed_at": "2026-06-20T17:00:00Z",
        "is_cryptographically_signed": True,
        "trust_state": {
            "signature": "sig_c11d88a4f0b2",
            "verification": "verified",
            "lineage": "present"
        },
        "verification_result": {
            "certificate_url": "http://127.0.0.1:7484/certificates/cert_travel_local",
            "signed_at": "2026-06-20T17:05:00Z"
        }
    },
    {
        "seed_id": "seed_0510_key_layout",
        "intent": "A simple utility to compile ergonomic keyboard layout mappings into firmware files directly from a visual keymap editor.",
        "source": "conversation_extract",
        "status": "wilted",
        "growth": 15,
        "created_at": "2026-05-10T14:00:00Z",
        "completed_at": None,
        "is_cryptographically_signed": False,
        "trust_state": {
            "signature": "unsigned",
            "verification": "unverified",
            "lineage": "missing"
        },
        "recovery_suggestions": [
            "Simplify layout mapping to support only standard QWERTY/DVORAK key maps first.",
            "Use web-serial API to flash layouts directly from Chrome rather than compiling raw C code."
        ]
    }
]

with open(seeds_file, "w", encoding="utf-8") as f:
    json.dump(sample_seeds, f, indent=2)

print("Sample data populated inside seeds.json database successfully.")
