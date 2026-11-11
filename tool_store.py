"""Workspace tool catalog and connection-state boundary.

This module intentionally separates supported tools from configured and
connected tools. Provider secrets remain in the deployment secret manager;
user credentials remain encrypted through secret_store.
"""
from __future__ import annotations

import os

from secret_store import credential_status, delete_credential


CATALOG = (
    {
        "id": "files",
        "name": "Files & conversation exports",
        "category": "built_in",
        "description": "Import JSON archives, documents, PDFs, text, spreadsheets, and authorized local folders.",
        "capabilities": ["read_user_selected_files", "preserve_sources"],
    },
    {
        "id": "web",
        "name": "Web sources",
        "category": "built_in",
        "description": "Add public research while preserving its original address and retrieval context.",
        "capabilities": ["read_public_sources", "preserve_sources"],
    },
    {
        "id": "gmail",
        "name": "Gmail",
        "category": "external",
        "description": "Find selected email context and attach it to the project where the work continues.",
        "auth": "oauth2",
        "provider": "google",
        "capabilities": ["search_mail", "read_selected_mail"],
        "write_requires_confirmation": True,
    },
    {
        "id": "google_drive",
        "name": "Google Drive",
        "category": "external",
        "description": "Use Drive, Docs, Sheets, and Slides as governed project sources.",
        "auth": "oauth2",
        "provider": "google",
        "capabilities": ["search_files", "read_selected_files"],
        "write_requires_confirmation": True,
    },
    {
        "id": "google_calendar",
        "name": "Google Calendar",
        "category": "external",
        "description": "Use selected schedules and events as project context.",
        "auth": "oauth2",
        "provider": "google",
        "capabilities": ["read_calendars", "read_events"],
        "write_requires_confirmation": True,
    },
)


def _provider_configured(tool):
    if tool.get("category") == "built_in":
        return True
    provider = tool.get("provider")
    if provider == "google":
        return bool(os.environ.get("SEED_REFLECTIONS_GOOGLE_CLIENT_ID", "").strip() and
                    os.environ.get("SEED_REFLECTIONS_GOOGLE_CLIENT_SECRET", "").strip())
    return False


def _credential_provider(tool_id):
    return f"tool:{tool_id}"


def list_tools(workspace_id):
    result = []
    for definition in CATALOG:
        item = dict(definition)
        if item["category"] == "built_in":
            item.update({"state": "ready", "provider_configured": True, "connected": True})
        else:
            configured = _provider_configured(item)
            status = credential_status(workspace_id, _credential_provider(item["id"]))
            connected = bool(status.get("credential_configured"))
            state = "connected" if connected else ("authorization_required" if configured else "configuration_required")
            item.update({"state": state, "provider_configured": configured, "connected": connected})
            if connected:
                item["connected_at"] = status.get("created_at")
                item["last_used_at"] = status.get("last_used_at")
        result.append(item)
    return result


def get_tool(tool_id):
    return next((dict(item) for item in CATALOG if item["id"] == tool_id), None)


def disconnect_tool(workspace_id, tool_id):
    tool = get_tool(tool_id)
    if not tool or tool.get("category") == "built_in":
        raise KeyError("External tool not found")
    delete_credential(workspace_id, _credential_provider(tool_id))
    return {"id": tool_id, "state": "authorization_required" if _provider_configured(tool) else "configuration_required", "connected": False}
