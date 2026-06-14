# Dardes Marketplace

A personal Claude Code plugin marketplace.

## Install

```bash
/plugin marketplace add agnislav-o/claude-marketplace
/plugin install medication-reminder@dardes
```

Replace `agnislav-o/claude-marketplace` with the actual remote once pushed.

## Plugins

| Plugin | Description |
| --- | --- |
| [medication-reminder](plugins/medication-reminder) | SessionStart hook that checks Apple HealthKit and nudges you if today's meds aren't logged — priority-aware, ADHD-friendly. |

## Repo layout

```
.
├── .claude-plugin/
│   └── marketplace.json       # marketplace manifest (discovered by Claude Code)
└── plugins/
    └── <plugin-name>/
        ├── .claude-plugin/
        │   └── plugin.json    # plugin manifest
        ├── hooks/             # hook configs (hooks.json)
        ├── commands/          # slash commands (optional)
        ├── skills/            # skills (optional)
        └── ...                # plugin-specific code
```

## Adding a new plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json`.
2. Add its source entry to `.claude-plugin/marketplace.json`.
3. Commit and push.
