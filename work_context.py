"""Assemble the project context for working on one idea, and say exactly what was left out.

The context is the idea, the part of its source conversation around where it came from,
related decisions, open questions raised in the same conversation, and work already saved
for the idea. Nothing is cut silently: when messages do not fit, the context names the range
that is included and the count that is not, and the assistant can read the rest with
read_conversation.
"""

TOTAL_BUDGET = 18000
SOURCE_BUDGET = 11000
MESSAGE_CAP = 1500


def _clip(text, limit):
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[:limit] + "…"


def _source_window(messages, anchor_index):
    """Pick a window of consecutive messages around the anchor that fits the budget."""
    chosen, used = {anchor_index}, min(len(messages[anchor_index].get("content") or ""), MESSAGE_CAP)
    low = high = anchor_index
    while True:
        grew = False
        for index in (low - 1, high + 1):
            if 0 <= index < len(messages) and index not in chosen:
                cost = min(len(messages[index].get("content") or ""), MESSAGE_CAP)
                if used + cost <= SOURCE_BUDGET:
                    chosen.add(index); used += cost; grew = True
                    low, high = min(chosen), max(chosen)
        if not grew:
            return sorted(chosen)


def assemble(stores, workspace, seed):
    """Return (context_text, report). `stores` is the same read-only view the assistant uses."""
    lines = ["IDEA",
             f"title: {_clip(seed.get('title') or seed.get('intent'), 200)}",
             f"intent: {_clip(seed.get('intent') or seed.get('summary'), 600)}",
             f"status: {seed.get('status') or 'unknown'}",
             f"next action: {_clip(seed.get('next_action'), 300)}"]
    report = {"idea": seed.get("title") or seed.get("intent") or "this idea", "source": None,
              "decisions": 0, "questions": 0, "artifacts": 0, "notice": None}
    conversation_id = seed.get("source_conversation_id")
    found = stores.get_conversation(conversation_id) if conversation_id else None
    if found and found.get("messages"):
        messages = found["messages"]; title = found["conversation"].get("title") or "Untitled"
        anchor = next((i for i, m in enumerate(messages) if m.get("id") == seed.get("source_message_id")), 0)
        window = _source_window(messages, anchor)
        shortened = sum(1 for i in window if len(messages[i].get("content") or "") > MESSAGE_CAP)
        lines += ["", f"SOURCE CONVERSATION: {title}"]
        for i in window:
            marker = "  <- where this idea came from" if i == anchor else ""
            lines.append(f"[message {messages[i].get('ordinal', i)}] {messages[i].get('role')}: {_clip(messages[i].get('content'), MESSAGE_CAP)}{marker}")
        first, last = messages[window[0]].get("ordinal", window[0]), messages[window[-1]].get("ordinal", window[-1])
        left_out = len(messages) - len(window)
        report["source"] = {"conversation_id": conversation_id, "title": title, "included": len(window),
                            "total": len(messages), "first": first, "last": last, "shortened": shortened}
        if left_out or shortened:
            parts = []
            if left_out:
                parts.append(f"{left_out} of {len(messages)} messages are not included (messages {first} to {last} are shown); read others with read_conversation")
            if shortened:
                parts.append(f"{shortened} long message(s) were shortened")
            report["notice"] = "; ".join(parts) + "."
            lines.append(f"NOTE: {report['notice']}")
    elif conversation_id:
        report["notice"] = "The source conversation could not be found, so no source text is included."
        lines += ["", f"NOTE: {report['notice']}"]
    else:
        report["notice"] = "This idea has no linked source conversation."
        lines += ["", f"NOTE: {report['notice']}"]

    decisions = [d for d in workspace.get("decisions", [])
                 if d.get("source_conversation_id") == conversation_id
                 or (seed.get("project_id") and d.get("project_id") == seed.get("project_id"))][:8]
    if decisions:
        lines += ["", "DECISIONS ALREADY MADE"] + [f"- {_clip(d.get('statement'), 200)} (why: {_clip(d.get('rationale'), 200)})" for d in decisions]
    report["decisions"] = len(decisions)

    questions = [c for c in stores.list_candidates(status="pending", limit=60)
                 if c.get("conversation_id") == conversation_id and c.get("kind") == "question"][:5] if conversation_id else []
    if questions:
        lines += ["", "OPEN QUESTIONS RAISED IN THE SAME CONVERSATION (not yet reviewed)"] + [f"- {_clip(q.get('title'), 200)}" for q in questions]
    report["questions"] = len(questions)

    saved = [a for a in workspace.get("artifacts", []) if seed.get("seed_id") in (a.get("seed_ids") or [])][:5]
    if saved:
        lines += ["", "WORK ALREADY SAVED FOR THIS IDEA"] + [f"- {_clip(a.get('title'), 120)} ({a.get('type')}, {a.get('status')}, id: {a.get('artifact_id')})" for a in saved]
    report["artifacts"] = len(saved)

    text = "\n".join(lines)
    if len(text) > TOTAL_BUDGET:
        text = text[:TOTAL_BUDGET] + "\nNOTE: the context was cut here to fit."
        report["notice"] = (report["notice"] + " " if report["notice"] else "") + "The context was cut at its size limit."
    return text, report
