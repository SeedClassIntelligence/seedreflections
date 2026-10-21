"""
extract_seeds.py — SRT-1 Seed Reflection
Local (offline) seed extraction from conversation transcripts.
No API call required. Uses keyword matching and pattern analysis.

This is the offline alternative to the LLM-powered reflection.
It's fast and free, but less accurate than the Claude-powered version.

Input:  plain text conversation transcript
Output: {
    seeds:          list of {idea, status, location, keywords}
    abandoned:      list of {idea, reason, recovery_suggestion}
    drift_points:   list of {from_topic, to_topic, trigger, location}
    active_seed:    {idea, progress} or None
    completed:      list of {idea, evidence}
    recommendations: list of {seed, priority, reason}
    seed_signature: {type, timestamp, counts}
    stats:          {total_seeds, abandoned_count, completed_count, drift_count, message_count}
}

Usage:
    python extract_seeds.py transcript.txt
    python extract_seeds.py transcript.txt --output report.json
    echo "User: I want to build..." | python extract_seeds.py -
"""

import re
import sys
import json
import argparse
import hashlib
from datetime import datetime, timezone
from collections import Counter


# ── KEYWORD PATTERNS ────────────────────────────────────────────────────────

# Patterns that signal a new idea or task being planted
SEED_PATTERNS = [
    r"\bi want to\b",
    r"\bi'd like to\b",
    r"\blet's\s+(?:build|create|make|write|design|implement|add|start)\b",
    r"\bcan you\s+(?:help|build|create|make|write|design)\b",
    r"\bi'm\s+(?:working on|building|creating|trying to)\b",
    r"\bmy\s+(?:idea|project|plan|goal|task)\b",
    r"\bwe\s+(?:should|need to|could|might)\b",
    r"\bwhat if\b",
    r"\bwe could\b",
    r"\blet me\s+(?:try|build|start|create)\b",
    r"\bmy\s+app\b",
    r"\bmy\s+website\b",
    r"\bmy\s+business\b",
    r"\bi\s+(?:need|want)\s+(?:a|an|to)\b",
]

# Patterns that signal completion or resolution
COMPLETION_PATTERNS = [
    r"\b(?:done|finished|completed|ready|working)\b",
    r"\bthat works\b",
    r"\bperfect\b",
    r"\bthank you\b",
    r"\bthanks\b",
    r"\bgreat\b",
    r"\bawesome\b",
    r"\bthis is exactly\b",
    r"\bjust what i needed\b",
    r"\bsolve[sd]?\b.*\bproblem\b",
]

# Patterns that signal the conversation drifted
DRIFT_PATTERNS = [
    r"\bactually\b",
    r"\bwait\b",
    r"\bnever mind\b",
    r"\bforget that\b",
    r"\blet's\s+(?:switch|change|try|do)\s+(?:something|a different|another)\b",
    r"\bon a different\b",
    r"\bwhile we're at it\b",
    r"\balso\b.*\bwhile\b",
    r"\boh\b.*\bby the way\b",
    r"\bsidetrack\b",
    r"\boff topic\b",
    r"\bquick question\b",
    r"\bone more thing\b",
    r"\bspeaking of\b",
]

# Patterns that signal abandonment
ABANDON_PATTERNS = [
    r"\blet's move on\b",
    r"\bwe can\s+(?:skip|ignore|leave)\b",
    r"\bdon't worry about\b",
    r"\bmaybe later\b",
    r"\bwe'll come back to\b",
    r"\bthat's fine for now\b",
    r"\bfor now\b",
    r"\bwe'll revisit\b",
    r"\bset aside\b",
    r"\btable that\b",
]

# Topic extraction: nouns and noun phrases that indicate what was being worked on
TOPIC_WORDS = [
    "api", "app", "application", "website", "database", "feature", "function",
    "component", "page", "form", "button", "modal", "dashboard", "login",
    "authentication", "payment", "email", "notification", "test", "bug",
    "error", "performance", "design", "style", "layout", "route", "endpoint",
    "model", "schema", "query", "migration", "deployment", "server", "client",
    "frontend", "backend", "mobile", "ui", "ux", "workflow", "script", "tool",
    "plugin", "extension", "integration", "report", "analysis", "data",
    "chart", "graph", "export", "import", "upload", "download", "search",
    "filter", "sort", "pagination", "cache", "security", "config", "settings",
    "profile", "user", "admin", "role", "permission", "webhook", "sdk",
    "documentation", "readme", "tests", "build", "deploy", "pipeline",
]


# ── MESSAGE PARSER ───────────────────────────────────────────────────────────

def parse_transcript(transcript: str) -> list[dict]:
    """Parse a plain text transcript into messages."""
    messages = []
    current_role = None
    current_lines = []

    role_re = re.compile(
        r"^(user|human|assistant|ai|claude|chatgpt|gpt|you|me)\s*:\s*(.*)",
        re.IGNORECASE,
    )

    for line in transcript.splitlines():
        m = role_re.match(line.strip())
        if m:
            # Save previous message
            if current_role and current_lines:
                messages.append({
                    "role": _normalize_role(current_role),
                    "content": "\n".join(current_lines).strip(),
                })
            current_role = m.group(1)
            current_lines = [m.group(2)] if m.group(2).strip() else []
        elif current_role:
            current_lines.append(line)

    if current_role and current_lines:
        messages.append({
            "role": _normalize_role(current_role),
            "content": "\n".join(current_lines).strip(),
        })

    # If no role markers found, treat the whole thing as one block
    if not messages and transcript.strip():
        messages.append({"role": "user", "content": transcript.strip()})

    return [m for m in messages if m["content"]]


def _normalize_role(role: str) -> str:
    role = role.lower().strip()
    if role in ("user", "human", "you", "me"):
        return "user"
    return "assistant"


# ── KEYWORD EXTRACTION ───────────────────────────────────────────────────────

def extract_keywords(text: str) -> list[str]:
    """Extract relevant topic keywords from text."""
    text_lower = text.lower()
    found = []
    for word in TOPIC_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", text_lower):
            found.append(word)
    return found


def matches_any(text: str, patterns: list[str]) -> bool:
    text_lower = text.lower()
    for p in patterns:
        if re.search(p, text_lower):
            return True
    return False


def find_first_match(text: str, patterns: list[str]) -> str | None:
    text_lower = text.lower()
    for p in patterns:
        m = re.search(p, text_lower)
        if m:
            return m.group(0)
    return None


# ── SEED EXTRACTION ──────────────────────────────────────────────────────────

def extract_seeds(transcript: str) -> dict:
    """
    Main function. Extract seeds, drift points, and recommendations
    from a conversation transcript.
    """
    messages = parse_transcript(transcript)
    if not messages:
        return _empty_result()

    seeds_raw = []
    drift_points = []
    completed_signals = []

    user_messages = [m for m in messages if m["role"] == "user"]
    assistant_messages = [m for m in messages if m["role"] == "assistant"]

    # ── PASS 1: Find seed-planting moments in user messages ──────────────────
    for i, msg in enumerate(user_messages):
        content = msg["content"]
        if matches_any(content, SEED_PATTERNS):
            keywords = extract_keywords(content)
            # Extract the core idea: first sentence or first 120 chars
            first_sentence = re.split(r"[.!?]\s", content)[0].strip()
            idea = first_sentence[:120] if first_sentence else content[:120]
            seeds_raw.append({
                "idea": idea,
                "keywords": keywords,
                "message_index": i,
                "content": content,
                "status": "unknown",
            })

    # ── PASS 2: Detect drift points ───────────────────────────────────────────
    for i, msg in enumerate(user_messages):
        if matches_any(msg["content"], DRIFT_PATTERNS):
            trigger = find_first_match(msg["content"], DRIFT_PATTERNS) or "topic shift"
            from_topic = _summarize_topic(user_messages, max(0, i - 1))
            to_topic = _summarize_topic(user_messages, i)
            if from_topic != to_topic:
                drift_points.append({
                    "from_topic": from_topic,
                    "to_topic": to_topic,
                    "trigger": trigger,
                    "message_index": i,
                })

    # ── PASS 3: Classify seed status ─────────────────────────────────────────
    # Look at messages after each seed was planted to determine if it was resolved
    for seed in seeds_raw:
        idx = seed["message_index"]
        subsequent_user = user_messages[idx + 1:]
        subsequent_assistant = assistant_messages[min(idx, len(assistant_messages) - 1):]

        # Check for abandonment signals
        abandoned = False
        for msg in subsequent_user[:3]:
            if matches_any(msg["content"], ABANDON_PATTERNS):
                abandoned = True
                break

        # Check for completion signals
        completed = False
        for msg in subsequent_user[:5]:
            if matches_any(msg["content"], COMPLETION_PATTERNS):
                completed = True
                break
        if not completed:
            for msg in subsequent_assistant[:3]:
                content_lower = msg["content"].lower()
                if any(w in content_lower for w in ["here's the complete", "here is the complete", "final version", "done!", "completed"]):
                    completed = True
                    break

        if completed:
            seed["status"] = "completed"
        elif abandoned:
            seed["status"] = "abandoned"
        elif idx >= len(user_messages) - 2:
            seed["status"] = "active"  # recent, likely still active
        else:
            seed["status"] = "abandoned"  # old and not completed

    # ── PASS 4: Identify the most recent active seed ──────────────────────────
    active_seed = None
    for seed in reversed(seeds_raw):
        if seed["status"] in ("active", "unknown"):
            active_seed = {"idea": seed["idea"], "progress": "In progress", "keywords": seed["keywords"]}
            break

    # ── PASS 5: Build structured output ──────────────────────────────────────
    completed_seeds = []
    abandoned_seeds = []

    for seed in seeds_raw:
        if seed["status"] == "completed":
            completed_seeds.append({
                "idea": seed["idea"],
                "evidence": "Completion signals detected in subsequent messages.",
                "keywords": seed["keywords"],
            })
        elif seed["status"] in ("abandoned", "unknown"):
            # Try to infer why it was abandoned
            reason = _infer_abandonment_reason(seed, drift_points, seeds_raw)
            recovery = _generate_recovery_suggestion(seed)
            abandoned_seeds.append({
                "idea": seed["idea"],
                "reason": reason,
                "recovery_suggestion": recovery,
                "keywords": seed["keywords"],
            })

    # ── PASS 6: Generate recommendations ─────────────────────────────────────
    recommendations = _generate_recommendations(abandoned_seeds, drift_points)

    # ── SEED SIGNATURE ────────────────────────────────────────────────────────
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    content_hash = hashlib.sha256(transcript.encode()).hexdigest()[:16]

    result = {
        "seeds": [{"idea": s["idea"], "status": s["status"], "keywords": s["keywords"]} for s in seeds_raw],
        "abandoned": abandoned_seeds,
        "completed": completed_seeds,
        "drift_points": drift_points,
        "active_seed": active_seed,
        "recommendations": recommendations,
        "seed_signature": {
            "type": "SCIA-LOCAL-EXTRACT",
            "timestamp": timestamp,
            "content_hash": content_hash,
            "seeds_found": len(seeds_raw),
            "abandoned_count": len(abandoned_seeds),
            "completed_count": len(completed_seeds),
            "drift_count": len(drift_points),
            "method": "local-keyword-extraction",
            "version": "1.0",
        },
        "stats": {
            "total_seeds": len(seeds_raw),
            "abandoned_count": len(abandoned_seeds),
            "completed_count": len(completed_seeds),
            "drift_count": len(drift_points),
            "message_count": len(messages),
            "user_message_count": len(user_messages),
        },
    }
    return result


def _summarize_topic(messages: list[dict], idx: int) -> str:
    """Get a short topic summary from a message."""
    if idx >= len(messages):
        return "unknown"
    content = messages[idx]["content"]
    keywords = extract_keywords(content)
    if keywords:
        return ", ".join(keywords[:3])
    # Fallback: first 5 meaningful words
    words = [w for w in content.lower().split() if len(w) > 3][:5]
    return " ".join(words) or "unknown"


def _infer_abandonment_reason(seed: dict, drift_points: list, all_seeds: list) -> str:
    """Try to infer why a seed was abandoned."""
    idx = seed["message_index"]
    # Check if a drift happened shortly after
    for dp in drift_points:
        if abs(dp["message_index"] - idx) <= 2:
            return f'Conversation drifted toward "{dp["to_topic"]}" after this seed was planted.'
    # Check if another seed was planted right after
    later_seeds = [s for s in all_seeds if s["message_index"] > idx and s["message_index"] <= idx + 3]
    if later_seeds:
        return f'A new idea displaced this one: "{later_seeds[0]["idea"][:60]}…"'
    # Generic
    return "The conversation moved on without completing this idea."


def _generate_recovery_suggestion(seed: dict) -> str:
    """Generate a restart prompt for an abandoned seed."""
    idea = seed["idea"]
    keywords = seed.get("keywords", [])
    topic = keywords[0] if keywords else "this"
    return (
        f'To restart: "Let\'s continue working on {topic}. '
        f'The original goal was: {idea[:80]}. '
        f'Where should we pick this up?"'
    )


def _generate_recommendations(abandoned: list, drift_points: list) -> list:
    """Generate top recovery recommendations, prioritized."""
    recommendations = []
    for i, seed in enumerate(abandoned[:5]):
        priority = "High" if i < 2 else ("Medium" if i < 4 else "Low")
        recommendations.append({
            "seed": seed["idea"],
            "priority": priority,
            "reason": f"Abandoned mid-conversation. {seed['reason']}",
            "recovery": seed["recovery_suggestion"],
        })
    return recommendations


def _empty_result() -> dict:
    return {
        "seeds": [], "abandoned": [], "completed": [],
        "drift_points": [], "active_seed": None, "recommendations": [],
        "seed_signature": {
            "type": "SCIA-LOCAL-EXTRACT",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "seeds_found": 0, "abandoned_count": 0,
            "completed_count": 0, "drift_count": 0,
            "method": "local-keyword-extraction", "version": "1.0",
        },
        "stats": {"total_seeds": 0, "abandoned_count": 0, "completed_count": 0, "drift_count": 0, "message_count": 0, "user_message_count": 0},
    }


# ── REPORT FORMATTER ─────────────────────────────────────────────────────────

def format_report(result: dict) -> str:
    """Format extraction result as a human-readable markdown report."""
    lines = []
    sig = result["seed_signature"]
    stats = result["stats"]

    lines.append("# Seed Reflection Report (Local Extraction)")
    lines.append(f"> Generated {sig['timestamp']}")
    lines.append(f"> Method: Local keyword extraction (no API call)")
    lines.append("")

    lines.append("## 📊 Session Summary")
    lines.append(f"- **Total seeds found:** {stats['total_seeds']}")
    lines.append(f"- **Completed:** {stats['completed_count']}")
    lines.append(f"- **Abandoned:** {stats['abandoned_count']}")
    lines.append(f"- **Drift points:** {stats['drift_count']}")
    lines.append(f"- **Messages analyzed:** {stats['message_count']}")
    lines.append("")

    if result["active_seed"]:
        lines.append("## 🌱 Active Seed")
        lines.append(f"**{result['active_seed']['idea']}**")
        lines.append("")

    if result["completed"]:
        lines.append("## 🌿 Completed Seeds")
        for s in result["completed"]:
            lines.append(f"- {s['idea']}")
        lines.append("")

    if result["abandoned"]:
        lines.append("## 🍂 Abandoned Seeds")
        for s in result["abandoned"]:
            lines.append(f"**{s['idea']}**")
            lines.append(f"> *Reason: {s['reason']}*")
            lines.append(f"> Recovery: {s['recovery_suggestion']}")
            lines.append("")

    if result["drift_points"]:
        lines.append("## 🌊 Drift Points")
        for dp in result["drift_points"]:
            lines.append(f"- From **{dp['from_topic']}** → to **{dp['to_topic']}** (trigger: \"{dp['trigger']}\")")
        lines.append("")

    if result["recommendations"]:
        lines.append("## 🎯 Recovery Recommendations")
        for i, r in enumerate(result["recommendations"], 1):
            lines.append(f"**{i}. [{r['priority']}] {r['seed']}**")
            lines.append(f"   {r['recovery']}")
            lines.append("")

    lines.append("---")
    lines.append(f"```\n---SEED-SIGNATURE---")
    lines.append(f"Type:        {sig['type']}")
    lines.append(f"Timestamp:   {sig['timestamp']}")
    lines.append(f"Seeds Found: {sig['seeds_found']}")
    lines.append(f"Abandoned:   {sig['abandoned_count']}")
    lines.append(f"Method:      {sig['method']}")
    lines.append(f"---END-SIGNATURE---\n```")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract seeds from a conversation transcript (offline, no API).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Path to transcript file, or - for stdin")
    parser.add_argument("--output", "-o", default=None, help="Write JSON output to file")
    parser.add_argument("--format", choices=["json", "report"], default="report", help="Output format")
    args = parser.parse_args()

    if args.input == "-":
        transcript = sys.stdin.read()
    else:
        if not os.path.exists(args.input):
            print(f"Error: file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        with open(args.input, "r", encoding="utf-8") as f:
            transcript = f.read()

    result = extract_seeds(transcript)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Wrote results to {args.output}")
    elif args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_report(result))


if __name__ == "__main__":
    main()
