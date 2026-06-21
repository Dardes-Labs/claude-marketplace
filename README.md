# Dardes Labs — Claude Code Marketplace

Claude Code plugins from **[Dardes Labs](https://github.com/Dardes-Labs)**, and a window into the apps we build.

## Install

```bash
/plugin marketplace add Dardes-Labs/claude-marketplace
/plugin install medication-reminder@dardes
```

## Plugins

| Plugin | Description |
| --- | --- |
| [medication-reminder](plugins/medication-reminder) | Companion plugin for **TaDa**, our per-dose medication-adherence iOS app. Reads per-dose adherence from a shared iCloud `state.json`, nudges you about doses you haven't logged, and marks a dose Taken/Skipped from the Mac — kept in sync with Apple Health by the app. ADHD-friendly. *(plugin id `medication-reminder`, rename to `tada` pending.)* |

## Apps from Dardes Labs

- **TaDa** — per-dose medication adherence for people who forget. An iOS app backed by Apple Health, plus the companion Mac plugin above. *In development.*

_More to come._

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

## Adding a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json`.
2. Add its source entry to `.claude-plugin/marketplace.json`.
3. Commit and push.
