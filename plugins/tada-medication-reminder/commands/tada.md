---
description: Show today's TaDa doses, or log one Taken/Skipped from the Mac
argument-hint: "[take|skip|undo] <medication> [--at HH:MM|prn]"
allowed-tools: Bash(python3:*)
---

Use the TaDa companion CLI at `${CLAUDE_PLUGIN_ROOT}/scripts/tada.py` to read or update today's per-dose medication state.

Run it with the user's arguments (default to `status` when none are given) and show the result:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tada.py" $ARGUMENTS
```

Subcommands:
- `status` — today's doses and their status (✓ taken · ✗ skipped · ○ pending).
- `take <med>` / `skip <med>` — log the **earliest pending** dose of that medication (named by display name or `id`); add `--at HH:MM` to target a specific dose, or `--at prn` for an as-needed dose. The write sets `source: "plugin"`; the iOS app mirrors it into Apple Health.
- `undo <med>` — reset that medication's most recently logged dose back to pending.

After running, summarize what changed — or why nothing did (today's `state.json` not published yet, an ambiguous name, or no pending dose). Only report what the CLI actually output; never invent doses or statuses.
