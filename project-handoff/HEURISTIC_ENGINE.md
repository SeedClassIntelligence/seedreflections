# Heuristic Engine Spec

If no LLM API key is configured, or if requests fail due to network/rate-limiting errors, the backend triggers the **Heuristic Fallback Engine** to extract seeds deterministically.

### Extraction Logic
* Scans the text using regex expressions targeting strong intent markers:
  * Requirements: `(?i)(?:must|should|need to|have to|plan to)\s+([A-Z][^.?!]{10,120})`
  * Architecture/Tech Decisions: `(?i)(?:use|implement|deploy|configure|choose)\s+([A-Z][^.?!]{10,120})`
* Excludes duplicate sentences and trims formatting.
* Evaluates confidence scores based on sentence length and match keywords.
