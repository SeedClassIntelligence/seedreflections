# Provider Adapters

The extraction pipeline integrates with four distinct model backends:

1. **Ollama**:
   * Endpoint: `/api/generate` or `/api/chat`
   * Schema: Standard local model inference JSON.
2. **Google Gemini**:
   * API Version: `v1beta`
   * Method: `generateContent` JSON schema.
3. **Together AI**:
   * Endpoint: `https://api.together.xyz/v1/chat/completions`
   * Schema: OpenAI-compatible payload.
4. **OpenAI**:
   * Endpoint: `https://api.openai.com/v1/chat/completions`
   * Schema: Chat completion JSON.

### Configuration
Model parameters and API keys are stored securely inside `config.json` and can be updated on the fly via the settings panel.
