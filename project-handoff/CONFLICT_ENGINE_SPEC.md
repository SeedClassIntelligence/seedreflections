# Conflict Engine Spec

A conflict represents a direct contradiction in intent, rules, or requirements between two seeds within the same project.

### Conflict Schema
* `conflict_id`: UUID
* `project_id`: Project scope.
* `subject`: Short title.
* `seed_a`: First Seed ID.
* `seed_b`: Second Seed ID.
* `statement_a`: Statement of Seed A.
* `statement_b`: Statement of Seed B.
* `severity`: `Low`, `Medium`, `High`.
* `status`: `Unresolved`, `A Controls`, `B Controls`, `Both Apply`, `Merge`, `Reject A`, `Reject B`.
* `resolution_date`: ISO timestamp.
