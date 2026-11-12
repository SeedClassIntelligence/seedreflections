"""One call shape for every model provider the platform supports.

Plain chat completion only. Tool use is handled one level up (workspace_agent) in a
provider-independent way, so the same loop works on Ollama, OpenAI-compatible
endpoints, Anthropic and Gemini. This module never logs or returns a key, and error
messages never include the request URL or the provider's response body.
"""
import json
import urllib.error
import urllib.request


class ModelCallError(Exception):
    """A provider call failed. The message is safe to show to the user."""


def _post(url, payload, headers, timeout):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise ModelCallError(f"The model provider returned HTTP {error.code}.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ModelCallError("The model provider could not be reached.") from None
    except ValueError:
        raise ModelCallError("The model provider returned an unreadable response.") from None


def _merge_same_role(messages):
    merged = []
    for message in messages:
        if merged and merged[-1]["role"] == message["role"]:
            merged[-1]["content"] += "\n\n" + message["content"]
        else:
            merged.append({"role": message["role"], "content": message["content"]})
    return merged


def _openai_url(api_url):
    url = (api_url or "https://api.openai.com").rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions" if url.endswith("/v1") else url + "/v1/chat/completions"


def complete(provider, api_url, api_key, model, messages, timeout=90, max_tokens=1200):
    """Return {"text", "prompt_tokens", "completion_tokens"} for one completion."""
    provider = (provider or "ollama").lower()
    if not model:
        raise ModelCallError("No model is selected.")
    if provider == "ollama":
        base = (api_url or "http://127.0.0.1:11434").rstrip("/")
        data = _post(base + "/api/chat", {"model": model, "messages": messages, "stream": False, "format": "json"},
                     {}, timeout)
        return {"text": str((data.get("message") or {}).get("content") or ""),
                "prompt_tokens": int(data.get("prompt_eval_count") or 0),
                "completion_tokens": int(data.get("eval_count") or 0)}
    if not api_key:
        raise ModelCallError("No API key is configured for this provider.")
    if provider == "anthropic":
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = _merge_same_role([m for m in messages if m["role"] != "system"])
        base = (api_url or "https://api.anthropic.com").rstrip("/")
        data = _post(base + "/v1/messages",
                     {"model": model, "max_tokens": max_tokens, "system": system, "messages": turns},
                     {"x-api-key": api_key, "anthropic-version": "2023-06-01"}, timeout)
        text = "".join(block.get("text", "") for block in data.get("content") or [] if block.get("type") == "text")
        usage = data.get("usage") or {}
        return {"text": text, "prompt_tokens": int(usage.get("input_tokens") or 0),
                "completion_tokens": int(usage.get("output_tokens") or 0)}
    if provider in {"gemini", "google"}:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = _merge_same_role([m for m in messages if m["role"] != "system"])
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in turns]
        base = (api_url or "https://generativelanguage.googleapis.com").rstrip("/")
        data = _post(f"{base}/v1beta/models/{model}:generateContent",
                     {"system_instruction": {"parts": [{"text": system}]}, "contents": contents,
                      "generationConfig": {"maxOutputTokens": max_tokens, "responseMimeType": "application/json"}},
                     {"x-goog-api-key": api_key}, timeout)
        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
        usage = data.get("usageMetadata") or {}
        return {"text": "".join(p.get("text", "") for p in parts),
                "prompt_tokens": int(usage.get("promptTokenCount") or 0),
                "completion_tokens": int(usage.get("candidatesTokenCount") or 0)}
    data = _post(_openai_url(api_url), {"model": model, "messages": messages, "max_tokens": max_tokens},
                 {"Authorization": f"Bearer {api_key}"}, timeout)
    choice = (data.get("choices") or [{}])[0]
    usage = data.get("usage") or {}
    return {"text": str((choice.get("message") or {}).get("content") or ""),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0)}
