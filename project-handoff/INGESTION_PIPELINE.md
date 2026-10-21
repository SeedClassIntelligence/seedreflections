# Ingestion Pipeline Specification

The ingestion pipeline parses conversation exports in bulk.

### Formats Supported
1. **ChatGPT Export (`conversations.json`)**: Contains hierarchical `mapping` objects. It tracks nodes, messages, authors, and transcript details.
2. **Claude Export (`conversations.json`)**: List of conversation arrays containing a `chat_messages` flat log.
3. **Generic Export**: Standard list structure containing `role`/`sender` and `content`/`text` pairs.

### Ingestion Flow
* **File Upload**: `POST /api/v1/upload_export` receives the file via multi-part upload, saving it to `uploads/temp_export.json`.
* **Summary Extraction**: The server reads the file and returns a list of conversation records (title, depth, dates, and preview snippet).
* **Staging and Selection**: The user selects specific conversations they want to reflect on.
* **Batch Processing**: The selected IDs are processed by `POST /api/v1/reflect_selected`, passing the conversation texts to the Extraction Engine.
