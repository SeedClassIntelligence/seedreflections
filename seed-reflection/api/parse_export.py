"""
parse_export.py — SRT-1 Seed Reflection
Parses ChatGPT and Claude conversation exports into a normalized format.

Input:  path to a .json or .zip file
Output: list of conversation dicts, each with:
        - id:           str
        - title:        str
        - date:         str (ISO 8601)
        - platform:     str ("ChatGPT" | "Claude" | "Unknown")
        - message_count: int
        - preview:      str (first 200 chars of first user message)
        - messages:     list of {role: str, content: str}
        - transcript:   str (plain text, "User: ...\n\nAssistant: ...")

Usage:
    python parse_export.py conversations.json
    python parse_export.py chatgpt_export.zip
    python parse_export.py export.json --output parsed.json
"""

import json
import sys
import os
import zipfile
import argparse
from datetime import datetime, timezone


def parse_file(path: str) -> list[dict]:
    """Parse a ChatGPT or Claude export file. Returns list of conversations."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    if path.endswith(".zip"):
        return _parse_zip(path)
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return parse_data(data)


def _parse_zip(path: str) -> list[dict]:
    """Extract conversations.json from a ChatGPT zip export and parse it."""
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        # ChatGPT zip contains conversations.json at root or in a subdirectory
        target = None
        for name in names:
            if name.endswith("conversations.json"):
                target = name
                break
        if not target:
            raise ValueError(
                f"Could not find conversations.json in zip. Files found: {names[:10]}"
            )
        with zf.open(target) as f:
            data = json.load(f)
    return parse_data(data)


def parse_data(data) -> list[dict]:
    """Auto-detect format and parse conversation data."""
    if isinstance(data, list):
        if not data:
            return []
        first = data[0]
        # ChatGPT format: has "mapping" key
        if isinstance(first, dict) and "mapping" in first:
            return [_parse_chatgpt_conv(c) for c in data]
        # Claude format: has "chat_messages" or "messages" key
        if isinstance(first, dict) and (
            "chat_messages" in first or "messages" in first
        ):
            return [_parse_claude_conv(c) for c in data]
        # Unknown array format — try both parsers
        results = []
        for item in data:
            if "mapping" in item:
                results.append(_parse_chatgpt_conv(item))
            elif "chat_messages" in item or "messages" in item:
                results.append(_parse_claude_conv(item))
            else:
                results.append(_parse_unknown(item))
        return results

    if isinstance(data, dict):
        if "mapping" in data:
            return [_parse_chatgpt_conv(data)]
        if "chat_messages" in data or "messages" in data:
            return [_parse_claude_conv(data)]

    raise ValueError("Unrecognized export format. Expected ChatGPT or Claude JSON.")


def _parse_chatgpt_conv(c: dict) -> dict:
    """Parse a single ChatGPT conversation object."""
    mapping = c.get("mapping", {})
    messages = []

    def walk(node_id):
        node = mapping.get(node_id)
        if not node:
            return
        msg = node.get("message")
        if msg:
            author_role = msg.get("author", {}).get("role", "")
            if author_role not in ("system", "tool"):
                content_obj = msg.get("content", {})
                parts = content_obj.get("parts", [])
                text = "".join(p for p in parts if isinstance(p, str)).strip()
                if text:
                    messages.append({"role": author_role, "content": text})
        for child_id in node.get("children", []):
            walk(child_id)

    # Find root node (no parent)
    root_id = None
    for node_id, node in mapping.items():
        if not node.get("parent"):
            root_id = node_id
            break
    if root_id:
        walk(root_id)

    # Determine date
    date_str = ""
    ts = c.get("create_time") or c.get("update_time")
    if ts:
        try:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            date_str = dt.isoformat()
        except (ValueError, OSError):
            date_str = ""

    return _build_conv(
        conv_id=c.get("id", ""),
        title=c.get("title", "Untitled"),
        date=date_str,
        platform="ChatGPT",
        messages=messages,
    )


def _parse_claude_conv(c: dict) -> dict:
    """Parse a single Claude conversation object."""
    raw_messages = c.get("chat_messages") or c.get("messages") or []
    messages = []

    for m in raw_messages:
        role = m.get("sender") or m.get("role") or "user"
        # Normalize role names
        if role in ("human",):
            role = "user"
        elif role in ("ai", "model"):
            role = "assistant"

        # Content can be a string or a list of content blocks
        content = m.get("text", "") or m.get("content", "")
        if isinstance(content, list):
            # List of content blocks: [{type: "text", text: "..."}]
            content = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict)
            )
        content = str(content).strip()
        if content:
            messages.append({"role": role, "content": content})

    # Date
    date_str = ""
    raw_date = c.get("created_at") or c.get("updated_at") or ""
    if raw_date:
        try:
            # Claude uses ISO 8601 strings
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            date_str = dt.isoformat()
        except (ValueError, AttributeError):
            date_str = str(raw_date)

    return _build_conv(
        conv_id=c.get("uuid") or c.get("id") or "",
        title=c.get("name") or c.get("title") or "Untitled",
        date=date_str,
        platform="Claude",
        messages=messages,
    )


def _parse_unknown(c: dict) -> dict:
    """Fallback parser for unknown formats."""
    return _build_conv(
        conv_id=str(c.get("id", id(c))),
        title=str(c.get("title", "Unknown conversation")),
        date="",
        platform="Unknown",
        messages=[],
    )


def _build_conv(conv_id: str, title: str, date: str, platform: str, messages: list) -> dict:
    """Build the normalized conversation dict."""
    # Build transcript
    transcript_lines = []
    for m in messages:
        role_label = "Assistant" if m["role"] == "assistant" else "User"
        transcript_lines.append(f"{role_label}: {m['content']}")
    transcript = "\n\n".join(transcript_lines)

    # First user message preview
    preview = ""
    for m in messages:
        if m["role"] != "assistant":
            preview = m["content"][:200]
            break

    return {
        "id": conv_id or f"conv_{abs(hash(title))}",
        "title": title.strip() or "Untitled",
        "date": date,
        "platform": platform,
        "message_count": len(messages),
        "preview": preview,
        "messages": messages,
        "transcript": transcript,
    }


def print_summary(conversations: list[dict]) -> None:
    """Print a human-readable summary to stdout."""
    print(f"\n{'='*60}")
    print(f"  Parsed {len(conversations)} conversation(s)")
    print(f"{'='*60}")

    platforms = {}
    total_messages = 0
    for c in conversations:
        p = c["platform"]
        platforms[p] = platforms.get(p, 0) + 1
        total_messages += c["message_count"]

    print(f"  Total messages : {total_messages:,}")
    for p, count in platforms.items():
        print(f"  {p:12} : {count} conversation(s)")
    print()

    for i, c in enumerate(conversations[:10], 1):
        date_display = c["date"][:10] if c["date"] else "—"
        print(f"  {i:2}. [{date_display}] {c['title'][:55]}")
        if c["preview"]:
            preview = c["preview"][:80].replace("\n", " ")
            print(f"       \"{preview}\"")

    if len(conversations) > 10:
        print(f"  … and {len(conversations) - 10} more")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Parse ChatGPT or Claude conversation exports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Path to .json or .zip export file")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Write parsed JSON to this file (default: print summary to stdout)"
    )
    parser.add_argument(
        "--format", choices=["json", "summary"], default="summary",
        help="Output format (default: summary)"
    )
    args = parser.parse_args()

    try:
        conversations = parse_file(args.input)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(conversations, f, indent=2, ensure_ascii=False)
        print(f"Wrote {len(conversations)} conversations to {args.output}")
    elif args.format == "json":
        print(json.dumps(conversations, indent=2, ensure_ascii=False))
    else:
        print_summary(conversations)


if __name__ == "__main__":
    main()
