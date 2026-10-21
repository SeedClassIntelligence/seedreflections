# Source Provenance Model

Every recovered seed must be traceable to its original transcript evidence.

### Fields
* **`source_platform`**: Tells whether the seed was mined from ChatGPT, Claude, or local chat.
* **`source_transcript_id`**: The UUID of the conversation history.
* **`source_thread_title`**: The title of the conversation.
* **`source_excerpt`**: The exact wording spoken by the creator.
* **`source_message_id`**: The specific turn identifier.
* **`source_timestamp`**: Timestamp of the original statement.
* **`imported_file_ref`**: Filename of the conversation zip/json export from which the seed was recovered.
