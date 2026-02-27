#!/usr/bin/env python3
"""
Claude Code → iPhone Push Notification Bridge

Intercepts PermissionRequest and Notification events from Claude Code
and forwards them as push notifications to your iPhone via ntfy.sh.

Free, zero-dependency, stdlib-only.

SETUP (takes ~2 minutes):
  1. iPhone: Install ntfy app → https://apps.apple.com/us/app/ntfy/id1625396347
  2. iPhone: Subscribe to your topic (e.g. "claude-matt-2026-secret42")
  3. This Mac: Add hooks to ~/.claude/settings.json (see NOTIFY_IPHONE_SETUP.md)
  4. This Mac: Set CLAUDE_NTFY_TOPIC in the hook command (see setup guide)

WHAT FIRES NOTIFICATIONS:
  - PermissionRequest  → Claude wants to run a tool and needs your OK
  - Notification/permission_prompt → Permission dialog notification
  - Notification/idle_prompt       → Claude is waiting for you
"""

import json
import os
import sys
import urllib.error
import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────
NTFY_SERVER = os.environ.get("CLAUDE_NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC  = os.environ.get("CLAUDE_NTFY_TOPIC", "").strip()
TIMEOUT_SEC = 4


# ── Helpers ───────────────────────────────────────────────────────────────────
def _trunc(text: str, max_len: int = 200) -> str:
    return text if len(text) <= max_len else text[:max_len - 3] + "…"


def _tool_input_preview(tool_input: object) -> str:
    """Turn tool_input into a readable one-liner."""
    if not isinstance(tool_input, dict):
        return _trunc(str(tool_input), 160)
    # Bash: show the command
    if "command" in tool_input:
        return _trunc(tool_input["command"], 160)
    # Write/Edit: show file path
    if "file_path" in tool_input:
        return tool_input["file_path"]
    # Read: show path
    if "path" in tool_input:
        return tool_input["path"]
    # Generic: first two key=value pairs
    pairs = [f"{k}={str(v)[:60]}" for k, v in list(tool_input.items())[:2]]
    return _trunc(", ".join(pairs), 160)


# ── Notification builder ───────────────────────────────────────────────────────
def build_notification(data: dict) -> tuple[str, str, str, str]:
    """
    Returns (title, message, ntfy_priority, ntfy_tags).

    ntfy priorities: min | low | default | high | urgent
    ntfy tags: https://docs.ntfy.sh/emojis/
    """
    event = data.get("hook_event_name", "")

    # ── PermissionRequest ─────────────────────────────────────────────────────
    if event == "PermissionRequest":
        tool    = data.get("tool_name", "unknown")
        preview = _tool_input_preview(data.get("tool_input", {}))
        title   = "Claude needs permission"
        message = f"{tool}: {preview}"
        return title, message, "high", "rotating_light,lock"

    # ── Notification ──────────────────────────────────────────────────────────
    if event == "Notification":
        notif_type  = data.get("notification_type", "")
        raw_msg     = data.get("message", "Claude Code notification")
        title_field = data.get("title", "")

        if notif_type == "permission_prompt":
            title = title_field or "Permission needed"
            return title, _trunc(raw_msg), "high", "rotating_light,iphone"

        if notif_type == "idle_prompt":
            title = title_field or "Claude is waiting"
            return title, _trunc(raw_msg), "default", "zzz"

        if notif_type == "auth_success":
            title = title_field or "Auth success"
            return title, _trunc(raw_msg), "low", "white_check_mark"

        if notif_type == "elicitation_dialog":
            title = title_field or "Claude has a question"
            return title, _trunc(raw_msg), "high", "speech_balloon"

        # Catch-all notification
        title = title_field or "Claude Code"
        return title, _trunc(raw_msg), "default", "bell"

    # ── Catch-all ─────────────────────────────────────────────────────────────
    fallback_msg = data.get("message", json.dumps(data)[:120])
    return f"Claude Code: {event}", _trunc(fallback_msg), "default", "robot"


# ── Sender ────────────────────────────────────────────────────────────────────
def send_notification(title: str, message: str, priority: str, tags: str) -> bool:
    if not NTFY_TOPIC:
        print(
            "[notify_iphone] CLAUDE_NTFY_TOPIC not set — no notification sent.\n"
            "  Set it in the hook command: CLAUDE_NTFY_TOPIC=your-topic python3 ...",
            file=sys.stderr,
        )
        return False

    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"

    try:
        req = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            headers={
                "Title":        title,
                "Priority":     priority,
                "Tags":         tags,
                "Content-Type": "text/plain; charset=utf-8",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            ok = resp.status == 200
            if not ok:
                print(f"[notify_iphone] ntfy returned HTTP {resp.status}", file=sys.stderr)
            return ok

    except urllib.error.URLError as e:
        print(f"[notify_iphone] Network error: {e}", file=sys.stderr)
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[notify_iphone] Unexpected error: {e}", file=sys.stderr)
        return False


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    try:
        raw = sys.stdin.read()
        data: dict = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"[notify_iphone] JSON parse error: {exc}", file=sys.stderr)
        sys.exit(0)  # non-blocking: don't break Claude Code

    title, message, priority, tags = build_notification(data)
    send_notification(title, message, priority, tags)
    sys.exit(0)  # always exit 0 — never block Claude Code


if __name__ == "__main__":
    main()
