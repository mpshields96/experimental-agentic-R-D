# iPhone Push Notifications for Claude Code

Sends a push notification to your iPhone every time Claude Code shows a
permission dialog — so you can see what it's asking while you're away from
your Mac.

**Zero cost. Zero accounts. Zero dependencies.** Uses [ntfy.sh](https://ntfy.sh) —
a free, open-source pub/sub notification service.

---

## Step 1 — iPhone: Install ntfy

App Store → **ntfy** by Philipp Heckel
→ https://apps.apple.com/us/app/ntfy/id1625396347

---

## Step 2 — Choose a secret topic name

Pick something unique + private, e.g. `claude-matt-2026-zx7q`

> Anyone who knows this string can send you notifications.
> Keep it secret — treat it like a password.

---

## Step 3 — iPhone: Subscribe to your topic

In the ntfy app:
1. Tap **+** (Subscribe to topic)
2. Enter your topic name (e.g. `claude-matt-2026-zx7q`)
3. Server: `https://ntfy.sh` (default)
4. Enable notifications when iOS asks

---

## Step 4 — Mac: Add hooks to ~/.claude/settings.json

Open `~/.claude/settings.json` (create it if it doesn't exist) and add or
merge the `hooks` block below.

**Replace `YOUR_TOPIC_HERE` with your topic from Step 2.**

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "CLAUDE_NTFY_TOPIC=YOUR_TOPIC_HERE python3 ~/ClaudeCode/agentic-rd-sandbox/scripts/notify_iphone.py",
            "async": true,
            "timeout": 8
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt|idle_prompt|elicitation_dialog",
        "hooks": [
          {
            "type": "command",
            "command": "CLAUDE_NTFY_TOPIC=YOUR_TOPIC_HERE python3 ~/ClaudeCode/agentic-rd-sandbox/scripts/notify_iphone.py",
            "async": true,
            "timeout": 8
          }
        ]
      }
    ]
  }
}
```

> **If settings.json already has a `hooks` key**, merge the new events into
> the existing object — don't replace the whole file.

> **Tip:** You can also add hooks interactively via `/hooks` inside Claude Code
> instead of editing the JSON file directly.

---

## Step 5 — Test it

In a Claude Code session, ask Claude to do something that needs permission
(e.g. run a Bash command). Your iPhone should buzz within ~2 seconds.

To test without Claude, run this in Terminal:

```bash
echo '{"hook_event_name":"PermissionRequest","tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/test"},"session_id":"test","transcript_path":"","cwd":"/tmp","permission_mode":"default"}' \
  | CLAUDE_NTFY_TOPIC=YOUR_TOPIC_HERE python3 ~/ClaudeCode/agentic-rd-sandbox/scripts/notify_iphone.py
```

You should get a "🔔 Claude needs permission — Bash: rm -rf /tmp/test" notification.

---

## What triggers notifications

| Event | When | Priority |
|---|---|---|
| `PermissionRequest` | Claude Code shows a permission dialog | 🔴 High |
| `Notification/permission_prompt` | Same, via notification channel | 🔴 High |
| `Notification/idle_prompt` | Claude is waiting for your input | 🟡 Default |
| `Notification/elicitation_dialog` | Claude has a question for you | 🔴 High |

---

## Troubleshooting

**No notification received**
- Check your topic name matches exactly in the hook command and iOS app
- Run the test command from Step 5 to isolate hook vs. network issues
- iOS: make sure ntfy has notification permission (Settings → ntfy → Notifications)

**"CLAUDE_NTFY_TOPIC not set"** in Claude Code verbose mode
- The env var isn't reaching the hook. Make sure it's inline: `CLAUDE_NTFY_TOPIC=xxx python3 ...`

**Hook not firing**
- Claude Code captures hooks at startup — restart the session after editing settings.json
- Check `/hooks` in Claude Code to confirm the hooks appear

**ntfy.sh rate limits**
- Free tier: 250 messages/day per topic (more than enough for normal use)
- Self-host ntfy for unlimited: https://docs.ntfy.sh/install/

---

## Privacy note

- Your notification messages pass through ntfy.sh servers
- Don't put secrets in bash commands you're approving — they'll appear in the notification body
- For sensitive environments, self-host ntfy or use a VPN
