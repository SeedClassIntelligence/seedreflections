# Data Migration Specification

The data migration utility handles schema upgrades.

### Inbound format (Legacy)
```json
[
  { "seed_id": "seed_1", "status": "planted", "intent": "Text" }
]
```

### Target format (Structured)
```json
{
  "seeds": [
    { "seed_id": "seed_1", "status": "planted", "intent": "Text", "evidence_status": "Explicitly Stated", "authority_status": "Detected", "continuity_status": "Active" }
  ],
  "projects": [],
  "sources": [],
  "decisions": [],
  "conflicts": []
}
```
