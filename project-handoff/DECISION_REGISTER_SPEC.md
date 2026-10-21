# Decision Register Spec

Decisions establish what rules, naming, or architecture will control the project scope.

### Decision Record
* `decision_id`: UUID
* `project_id`: Project association.
* `decision_statement`: Clear text statement.
* `decision_type`: Naming, Architecture, Scope, Authority, Product, Pricing, etc.
* `source_conversation`: Conversation title/id.
* `source_excerpt`: Supporting statement.
* `date`: ISO timestamp.
* `decision_maker`: Author attribution.
* `related_seeds`: List of associated seed IDs.
