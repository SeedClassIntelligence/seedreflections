# Lineage Engine Specification

Seeds are dynamic; they evolve, split, merge, or conflict. The relationship records govern these changes.

### Relationship Structure
Relationships must be stored as records:
* `relationship_id`: UUID
* `source_seed_id`: ID of the initiating seed.
* `target_seed_id`: ID of the related seed.
* `type`: One of:
  * `Originated From`, `Evolved Into`, `Refined By`, `Renamed As`, `Split Into`, `Merged With`, `Replaced By`, `Conflicts With`, `Restored From`
* `evidence`: Explanatory text excerpt.
* `created_at`: Timestamp.
