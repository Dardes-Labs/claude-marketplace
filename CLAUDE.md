# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo overview

This is **Dardes Labs' public Claude Code plugin marketplace** (`Dardes-Labs/claude-marketplace`). It hosts the plugins Dardes Labs publishes under `plugins/<name>/`, advertised via `.claude-plugin/marketplace.json` at the repo root, and doubles as a promotional surface for Dardes Labs apps.

To add a plugin: create `plugins/<name>/.claude-plugin/plugin.json`, then add a source entry to `.claude-plugin/marketplace.json`. Each plugin is independently versioned and self-contained — never share code across `plugins/<a>/` and `plugins/<b>/`.

The marketplace `name` is `dardes` (so installs read `<plugin>@dardes`); the owner is Dardes Labs.

## Plugins here

- **tada-medication-reminder** — the companion macOS plugin for **TaDa**, Dardes Labs' per-dose medication-adherence iOS app. The plugin is **config-less and app-dependent**: it reads a per-dose `state.json` that the TaDa iOS app syncs to iCloud Drive, and **never touches HealthKit**. Without the app it is inert. Its own README documents how it works (SessionStart notifier + a `/tada` log command).
  - **TaDa's product and design spec live in a separate repo** — `Dardes-Labs/tada-ios` (private). This marketplace carries only the installable companion plugin; don't reconstruct TaDa's architecture here — reference that repo.

## Conventions

No build, test, or lint step. Keep `.claude-plugin/marketplace.json` valid (it's the manifest Claude Code reads) and each plugin's `plugin.json` accurate. Machine-local files (`.claude/settings.local.json`, `.serena/`) stay untracked.
